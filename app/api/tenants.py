from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user, require_admin
from app.database.database import transaction

router = APIRouter(tags=["tenant and bucket management"])


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=1000)


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=1000)
    is_active: Optional[bool] = None


class BucketAssignment(BaseModel):
    tenant_id: Optional[int] = Field(ge=1)
    note: Optional[str] = Field(default=None, max_length=1000)


def _tenant_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "bucket_count": row["bucket_count"] if "bucket_count" in row.keys() else None,
    }


@router.get("/api/tenants")
def list_tenants(
    include_inactive: bool = Query(default=False),
    _: dict = Depends(get_current_user),
) -> dict:
    sql = """
        SELECT t.id, t.name, t.description, t.is_active, t.created_at, t.updated_at,
               COUNT(b.id) AS bucket_count
        FROM tenants t
        LEFT JOIN buckets b ON b.tenant_id = t.id
    """
    params: tuple = ()
    if not include_inactive:
        sql += " WHERE t.is_active = 1"
    sql += " GROUP BY t.id ORDER BY t.name COLLATE NOCASE"
    with transaction() as connection:
        rows = connection.execute(sql, params).fetchall()
    return {"items": [_tenant_dict(row) for row in rows], "count": len(rows)}


@router.post("/api/tenants", status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate,
    user: dict = Depends(require_admin),
) -> dict:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Tenant name cannot be blank")
    try:
        with transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO tenants (name, description) VALUES (?, ?)",
                (name, payload.description.strip() if payload.description else None),
            )
            row = connection.execute(
                """
                SELECT id, name, description, is_active, created_at, updated_at,
                       0 AS bucket_count
                FROM tenants WHERE id = ?
                """,
                (cursor.lastrowid,),
            ).fetchone()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A tenant with this name already exists") from exc
    return _tenant_dict(row)


@router.patch("/api/tenants/{tenant_id}")
def update_tenant(
    tenant_id: int,
    payload: TenantUpdate,
    user: dict = Depends(require_admin),
) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="No tenant fields supplied")
    if "name" in changes:
        if changes["name"] is None:
            raise HTTPException(status_code=422, detail="Tenant name cannot be null")
        changes["name"] = changes["name"].strip()
        if not changes["name"]:
            raise HTTPException(status_code=422, detail="Tenant name cannot be blank")
    if "is_active" in changes and changes["is_active"] is None:
        raise HTTPException(status_code=422, detail="is_active cannot be null")
    if "description" in changes and changes["description"] is not None:
        changes["description"] = changes["description"].strip() or None

    with transaction() as connection:
        current = connection.execute(
            "SELECT id FROM tenants WHERE id = ?", (tenant_id,)
        ).fetchone()
        if current is None:
            raise HTTPException(status_code=404, detail="Tenant not found")

        if changes.get("is_active") is False:
            assigned = connection.execute(
                "SELECT COUNT(*) FROM buckets WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()[0]
            if assigned:
                raise HTTPException(
                    status_code=409,
                    detail=f"Cannot deactivate tenant while {assigned} bucket(s) remain assigned; unassign them first",
                )

        assignments = [f"{column} = ?" for column in changes]
        values = list(changes.values())
        assignments.append("updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')")
        values.append(tenant_id)
        try:
            connection.execute(
                f"UPDATE tenants SET {', '.join(assignments)} WHERE id = ?", values
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="A tenant with this name already exists") from exc

        row = connection.execute(
            """
            SELECT t.id, t.name, t.description, t.is_active, t.created_at, t.updated_at,
                   (SELECT COUNT(*) FROM buckets b WHERE b.tenant_id = t.id) AS bucket_count
            FROM tenants t WHERE t.id = ?
            """,
            (tenant_id,),
        ).fetchone()
    return _tenant_dict(row)


@router.get("/api/buckets")
def list_buckets(
    cluster_id: Optional[str] = None,
    tenant_id: Optional[int] = Query(default=None, ge=1),
    unassigned: bool = False,
    include_inactive: bool = False,
    _: dict = Depends(get_current_user),
) -> dict:
    if unassigned and tenant_id is not None:
        raise HTTPException(status_code=422, detail="Use either unassigned or tenant_id, not both")

    sql = """
        SELECT b.id, b.cluster_id, c.name AS cluster_name, l.id AS location_id,
               l.name AS location_name, b.bucket_name, b.tenant_id,
               t.name AS tenant_name, b.first_seen_at, b.last_seen_at,
               b.is_active, b.created_at, b.updated_at
        FROM buckets b
        JOIN clusters c ON c.id = b.cluster_id
        JOIN locations l ON l.id = c.location_id
        LEFT JOIN tenants t ON t.id = b.tenant_id
        WHERE 1 = 1
    """
    params: list = []
    if cluster_id:
        sql += " AND b.cluster_id = ?"
        params.append(cluster_id)
    if tenant_id is not None:
        sql += " AND b.tenant_id = ?"
        params.append(tenant_id)
    if unassigned:
        sql += " AND b.tenant_id IS NULL"
    if not include_inactive:
        sql += " AND b.is_active = 1"
    sql += " ORDER BY l.name, c.name, b.bucket_name"

    with transaction() as connection:
        rows = connection.execute(sql, params).fetchall()
    items = [
        {
            "id": row["id"],
            "cluster_id": row["cluster_id"],
            "cluster_name": row["cluster_name"],
            "location_id": row["location_id"],
            "location_name": row["location_name"],
            "bucket_name": row["bucket_name"],
            "tenant_id": row["tenant_id"],
            "tenant_name": row["tenant_name"],
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "is_active": bool(row["is_active"]),
        }
        for row in rows
    ]
    return {"items": items, "count": len(items)}


@router.put("/api/buckets/{bucket_id}/tenant")
def set_bucket_tenant(
    bucket_id: int,
    payload: BucketAssignment,
    user: dict = Depends(require_admin),
) -> dict:
    with transaction() as connection:
        bucket = connection.execute(
            """
            SELECT id, cluster_id, bucket_name, tenant_id
            FROM buckets WHERE id = ?
            """,
            (bucket_id,),
        ).fetchone()
        if bucket is None:
            raise HTTPException(status_code=404, detail="Bucket not found")

        if payload.tenant_id is not None:
            tenant = connection.execute(
                "SELECT id, name FROM tenants WHERE id = ? AND is_active = 1",
                (payload.tenant_id,),
            ).fetchone()
            if tenant is None:
                raise HTTPException(status_code=404, detail="Active tenant not found")
            tenant_name = tenant["name"]
        else:
            tenant_name = None

        if bucket["tenant_id"] == payload.tenant_id:
            return {
                "changed": False,
                "message": "Bucket already has the requested tenant assignment",
                "bucket_id": bucket_id,
                "tenant_id": payload.tenant_id,
                "tenant_name": tenant_name,
            }

        connection.execute(
            """
            UPDATE buckets
            SET tenant_id = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ?
            """,
            (payload.tenant_id, bucket_id),
        )
        connection.execute(
            """
            INSERT INTO bucket_tenant_history (bucket_id, tenant_id, changed_at, changed_by, note)
            VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), ?, ?)
            """,
            (
                bucket_id,
                payload.tenant_id,
                user["username"],
                payload.note.strip() if payload.note else None,
            ),
        )

    return {
        "changed": True,
        "bucket_id": bucket_id,
        "cluster_id": bucket["cluster_id"],
        "bucket_name": bucket["bucket_name"],
        "tenant_id": payload.tenant_id,
        "tenant_name": tenant_name,
        "changed_by": user["username"],
    }


class BulkBucketAssignment(BaseModel):
    bucket_ids: list[int] = Field(min_length=1, max_length=500)
    tenant_id: Optional[int] = Field(ge=1)
    note: Optional[str] = Field(default=None, max_length=1000)


@router.put("/api/buckets/bulk-tenant")
def set_buckets_tenant(
    payload: BulkBucketAssignment,
    user: dict = Depends(require_admin),
) -> dict:
    bucket_ids = list(dict.fromkeys(payload.bucket_ids))
    if len(bucket_ids) != len(payload.bucket_ids):
        raise HTTPException(status_code=422, detail="Duplicate bucket IDs are not allowed")

    with transaction() as connection:
        if payload.tenant_id is not None:
            tenant = connection.execute(
                "SELECT id, name FROM tenants WHERE id = ? AND is_active = 1",
                (payload.tenant_id,),
            ).fetchone()
            if tenant is None:
                raise HTTPException(status_code=404, detail="Active tenant not found")
            tenant_name = tenant["name"]
        else:
            tenant_name = None

        placeholders = ",".join("?" for _ in bucket_ids)
        rows = connection.execute(
            f"""
            SELECT id, cluster_id, bucket_name, tenant_id
            FROM buckets
            WHERE id IN ({placeholders}) AND is_active = 1
            """,
            bucket_ids,
        ).fetchall()
        if len(rows) != len(bucket_ids):
            found = {row["id"] for row in rows}
            missing = [bucket_id for bucket_id in bucket_ids if bucket_id not in found]
            raise HTTPException(
                status_code=404,
                detail=f"Active bucket(s) not found: {', '.join(map(str, missing))}",
            )

        changed = []
        unchanged = []
        note = payload.note.strip() if payload.note and payload.note.strip() else None
        for bucket in rows:
            if bucket["tenant_id"] == payload.tenant_id:
                unchanged.append(bucket["id"])
                continue
            connection.execute(
                """
                UPDATE buckets
                SET tenant_id = ?,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ?
                """,
                (payload.tenant_id, bucket["id"]),
            )
            connection.execute(
                """
                INSERT INTO bucket_tenant_history
                    (bucket_id, tenant_id, changed_at, changed_by, note)
                VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), ?, ?)
                """,
                (bucket["id"], payload.tenant_id, user["username"], note),
            )
            changed.append({
                "bucket_id": bucket["id"],
                "cluster_id": bucket["cluster_id"],
                "bucket_name": bucket["bucket_name"],
            })

    return {
        "tenant_id": payload.tenant_id,
        "tenant_name": tenant_name,
        "requested_count": len(bucket_ids),
        "changed_count": len(changed),
        "unchanged_count": len(unchanged),
        "changed": changed,
        "unchanged_bucket_ids": unchanged,
        "changed_by": user["username"],
    }


@router.get("/api/buckets/{bucket_id}/history")
def bucket_assignment_history(
    bucket_id: int,
    _: dict = Depends(get_current_user),
) -> dict:
    with transaction() as connection:
        bucket = connection.execute(
            "SELECT id, cluster_id, bucket_name FROM buckets WHERE id = ?",
            (bucket_id,),
        ).fetchone()
        if bucket is None:
            raise HTTPException(status_code=404, detail="Bucket not found")
        rows = connection.execute(
            """
            SELECT h.id, h.tenant_id, t.name AS tenant_name,
                   h.changed_at, h.changed_by, h.note
            FROM bucket_tenant_history h
            LEFT JOIN tenants t ON t.id = h.tenant_id
            WHERE h.bucket_id = ?
            ORDER BY h.changed_at DESC, h.id DESC
            """,
            (bucket_id,),
        ).fetchall()

    return {
        "bucket": {
            "id": bucket["id"],
            "cluster_id": bucket["cluster_id"],
            "bucket_name": bucket["bucket_name"],
        },
        "items": [
            {
                "id": row["id"],
                "tenant_id": row["tenant_id"],
                "tenant_name": row["tenant_name"],
                "changed_at": row["changed_at"],
                "changed_by": row["changed_by"],
                "note": row["note"],
            }
            for row in rows
        ],
        "count": len(rows),
    }
