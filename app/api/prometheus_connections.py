from __future__ import annotations

import json
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.auth.dependencies import require_master_admin
from app.collectors.prometheus_discovery import build_prometheus_url, discover_minio_clusters
from app.collectors.prometheus import PrometheusError
from app.database.database import initialize_database, transaction

router = APIRouter(prefix="/api/master-admin/prometheus-connections", tags=["master administration"])
_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


class DiscoveredClusterBinding(BaseModel):
    cluster_id: str = Field(min_length=1, max_length=128)
    cluster_name: str = Field(min_length=1, max_length=255)
    identity_label_name: Literal["cluster", "site", "environment"] = "cluster"
    identity_label_value: str = Field(min_length=1, max_length=255)


class PrometheusEndpointTestInput(BaseModel):
    protocol: Literal["http", "https"] = "http"
    hostname: str = Field(min_length=1, max_length=253)
    port: int = Field(default=9090, ge=1, le=65535)
    verify_tls: bool = True


class PrometheusConnectionInput(BaseModel):
    connection_id: str = Field(min_length=1, max_length=128)
    location_id: str = Field(min_length=1, max_length=128)
    location_name: str = Field(min_length=1, max_length=255)
    protocol: Literal["http", "https"] = "http"
    hostname: str = Field(min_length=1, max_length=253)
    port: int = Field(default=9090, ge=1, le=65535)
    verify_tls: bool = True
    enabled: bool = True
    clusters: list[DiscoveredClusterBinding] = Field(min_length=1, max_length=100)

    @field_validator("connection_id", "location_id")
    @classmethod
    def validate_identifiers(cls, value: str) -> str:
        if not _ID.fullmatch(value):
            raise ValueError("Use letters, numbers, dot, underscore or hyphen for identifiers")
        return value

    @field_validator("location_name", "hostname")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value


@router.get("")
def list_connections(_: dict = Depends(require_master_admin)) -> dict:
    initialize_database()
    with transaction() as connection:
        rows = connection.execute(
            """
            SELECT pc.connection_id, pc.location_id, l.name AS location_name,
                   pc.protocol, pc.hostname, pc.port, pc.verify_tls, pc.enabled,
                   cpb.cluster_id, c.name AS cluster_name,
                   cpb.identity_label_name, cpb.identity_label_value
            FROM prometheus_connections pc
            JOIN locations l ON l.id = pc.location_id
            LEFT JOIN cluster_prometheus_bindings cpb ON cpb.connection_id = pc.connection_id
            LEFT JOIN clusters c ON c.id = cpb.cluster_id
            ORDER BY l.name, pc.connection_id, c.name
            """
        ).fetchall()

    items: dict[str, dict] = {}
    for row in rows:
        item = items.setdefault(row["connection_id"], {
            "connection_id": row["connection_id"],
            "location_id": row["location_id"],
            "location_name": row["location_name"],
            "protocol": row["protocol"],
            "hostname": row["hostname"],
            "port": row["port"],
            "verify_tls": bool(row["verify_tls"]),
            "enabled": bool(row["enabled"]),
            "clusters": [],
        })
        if row["cluster_id"] is not None:
            item["clusters"].append({
                "cluster_id": row["cluster_id"],
                "cluster_name": row["cluster_name"],
                "identity_label_name": row["identity_label_name"],
                "identity_label_value": row["identity_label_value"],
            })
    return {"items": list(items.values()), "count": len(items)}


@router.post("/test")
def test_connection(payload: PrometheusEndpointTestInput, _: dict = Depends(require_master_admin)) -> dict:
    try:
        endpoint = build_prometheus_url(payload.protocol, payload.hostname, payload.port)
        return discover_minio_clusters(endpoint, verify_tls=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PrometheusError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("", status_code=201)
def save_connection(payload: PrometheusConnectionInput, actor: dict = Depends(require_master_admin)) -> dict:
    initialize_database()
    endpoint = build_prometheus_url(payload.protocol, payload.hostname, payload.port)
    if len({cluster.cluster_id for cluster in payload.clusters}) != len(payload.clusters):
        raise HTTPException(status_code=422, detail="Cluster IDs must be unique in a connection")

    try:
        with transaction() as connection:
            existing_location = connection.execute(
                "SELECT name FROM locations WHERE id=?", (payload.location_id,)
            ).fetchone()
            if existing_location and existing_location["name"] != payload.location_name:
                raise HTTPException(status_code=409, detail="Location ID already exists with a different name")
            connection.execute(
                """INSERT INTO locations(id,name,enabled) VALUES(?,?,1)
                   ON CONFLICT(id) DO NOTHING""",
                (payload.location_id, payload.location_name),
            )
            existing = connection.execute(
                "SELECT location_id FROM prometheus_connections WHERE connection_id=?",
                (payload.connection_id,),
            ).fetchone()
            if existing and existing["location_id"] != payload.location_id:
                raise HTTPException(status_code=409, detail="Connection ID belongs to another location")
            connection.execute(
                """INSERT INTO prometheus_connections
                   (connection_id,location_id,protocol,hostname,port,verify_tls,enabled)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(connection_id) DO UPDATE SET
                   protocol=excluded.protocol, hostname=excluded.hostname,
                   port=excluded.port, verify_tls=excluded.verify_tls,
                   enabled=excluded.enabled,
                   updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""",
                (payload.connection_id, payload.location_id, payload.protocol,
                 payload.hostname, payload.port, 1, int(payload.enabled)),
            )
            for cluster in payload.clusters:
                current = connection.execute(
                    "SELECT location_id FROM clusters WHERE id=?", (cluster.cluster_id,)
                ).fetchone()
                if current and current["location_id"] != payload.location_id:
                    raise HTTPException(status_code=409, detail=f"Cluster {cluster.cluster_id} belongs to another location")
                connection.execute(
                    """INSERT INTO clusters(id,location_id,name,enabled,labels_json)
                       VALUES(?,?,?,1,'{}')
                       ON CONFLICT(id) DO UPDATE SET name=excluded.name""",
                    (cluster.cluster_id, payload.location_id, cluster.cluster_name),
                )
                connection.execute(
                    """INSERT INTO cluster_prometheus_bindings
                       (cluster_id,connection_id,identity_label_name,identity_label_value)
                       VALUES(?,?,?,?)
                       ON CONFLICT(cluster_id) DO UPDATE SET
                       connection_id=excluded.connection_id,
                       identity_label_name=excluded.identity_label_name,
                       identity_label_value=excluded.identity_label_value,
                       updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""",
                    (cluster.cluster_id, payload.connection_id,
                     cluster.identity_label_name, cluster.identity_label_value),
                )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=409, detail="Unable to save Prometheus connection") from exc

    return {"saved": True, "connection_id": payload.connection_id, "endpoint": endpoint,
            "cluster_bindings": len(payload.clusters), "updated_by": actor.get("username")}


@router.patch("/{connection_id}/enabled")
def set_connection_enabled(connection_id: str, enabled: bool, _: dict = Depends(require_master_admin)) -> dict:
    initialize_database()
    with transaction() as connection:
        result = connection.execute(
            """UPDATE prometheus_connections SET enabled=?,
               updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE connection_id=?""",
            (int(enabled), connection_id),
        )
        if result.rowcount != 1:
            raise HTTPException(status_code=404, detail="Prometheus connection not found")
    return {"updated": True, "connection_id": connection_id, "enabled": enabled}


class AddClustersInput(BaseModel):
    clusters: list[DiscoveredClusterBinding] = Field(min_length=1, max_length=100)


@router.post("/{connection_id}/clusters/discover")
def discover_connection_clusters(
    connection_id: str,
    _: dict = Depends(require_master_admin),
) -> dict:
    """Re-discover MinIO identities on an existing endpoint without writes."""
    initialize_database()
    with transaction() as connection:
        endpoint = connection.execute(
            """SELECT pc.location_id, pc.protocol, pc.hostname, pc.port, pc.enabled
               FROM prometheus_connections pc WHERE pc.connection_id=?""",
            (connection_id,),
        ).fetchone()
        if endpoint is None:
            raise HTTPException(status_code=404, detail="Prometheus connection not found")
        if not endpoint["enabled"]:
            raise HTTPException(status_code=409, detail="Enable the Prometheus connection before discovery")
        existing_rows = connection.execute(
            """SELECT cpb.identity_label_name, cpb.identity_label_value,
                      cpb.cluster_id, c.name AS cluster_name, cpb.connection_id
               FROM cluster_prometheus_bindings cpb
               JOIN clusters c ON c.id=cpb.cluster_id
               WHERE c.location_id=?""",
            (endpoint["location_id"],),
        ).fetchall()

    base_url = build_prometheus_url(
        endpoint["protocol"], endpoint["hostname"], endpoint["port"]
    )
    try:
        result = discover_minio_clusters(base_url, verify_tls=True)
    except (ValueError, PrometheusError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    bindings = {
        (row["identity_label_name"], row["identity_label_value"]): {
            "cluster_id": row["cluster_id"],
            "cluster_name": row["cluster_name"],
            "connection_id": row["connection_id"],
        }
        for row in existing_rows
    }
    for item in result["clusters"]:
        existing = bindings.get((item["label_name"], item["label_value"]))
        item["existing_cluster_id"] = existing["cluster_id"] if existing else None
        item["existing_cluster_name"] = existing["cluster_name"] if existing else None
        item["bound_connection_id"] = existing["connection_id"] if existing else None
        item["already_configured"] = bool(
            existing and existing["connection_id"] == connection_id
        )
        item["bound_elsewhere"] = bool(
            existing and existing["connection_id"] != connection_id
        )
    result["connection_id"] = connection_id
    result["location_id"] = endpoint["location_id"]
    result["new_cluster_count"] = sum(
        not item["already_configured"] and not item["bound_elsewhere"]
        for item in result["clusters"]
    )
    return result


@router.post("/{connection_id}/clusters", status_code=201)
def add_connection_clusters(
    connection_id: str,
    payload: AddClustersInput,
    actor: dict = Depends(require_master_admin),
) -> dict:
    """Explicitly approve and bind selected, freshly discovered MinIO clusters."""
    initialize_database()
    with transaction() as connection:
        endpoint = connection.execute(
            """SELECT pc.location_id, pc.protocol, pc.hostname, pc.port, pc.enabled
               FROM prometheus_connections pc WHERE pc.connection_id=?""",
            (connection_id,),
        ).fetchone()
        if endpoint is None:
            raise HTTPException(status_code=404, detail="Prometheus connection not found")
        if not endpoint["enabled"]:
            raise HTTPException(status_code=409, detail="Enable the Prometheus connection before adding clusters")
        location = connection.execute(
            "SELECT name FROM locations WHERE id=?", (endpoint["location_id"],)
        ).fetchone()
        if location is None:
            raise HTTPException(status_code=409, detail="Connection location is missing")

    base_url = build_prometheus_url(
        endpoint["protocol"], endpoint["hostname"], endpoint["port"]
    )
    try:
        discovered = discover_minio_clusters(base_url, verify_tls=True)
    except (ValueError, PrometheusError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    available = {
        (item["label_name"], item["label_value"])
        for item in discovered["clusters"]
    }
    identities = [
        (item.identity_label_name, item.identity_label_value)
        for item in payload.clusters
    ]
    if len(set(identities)) != len(identities):
        raise HTTPException(status_code=422, detail="Selected cluster identities must be unique")
    for item in payload.clusters:
        if (item.identity_label_name, item.identity_label_value) not in available:
            raise HTTPException(
                status_code=409,
                detail=f"Cluster identity is no longer present in Prometheus: {item.identity_label_name}={item.identity_label_value}",
            )

    added: list[dict[str, str]] = []
    with transaction() as connection:
        for item in payload.clusters:
            existing_binding = connection.execute(
                """SELECT cpb.cluster_id, cpb.connection_id, c.name, c.location_id
                   FROM cluster_prometheus_bindings cpb
                   JOIN clusters c ON c.id=cpb.cluster_id
                   WHERE cpb.identity_label_name=? AND cpb.identity_label_value=? AND c.location_id=?""",
                (item.identity_label_name, item.identity_label_value, endpoint["location_id"]),
            ).fetchone()
            if existing_binding:
                if existing_binding["connection_id"] == connection_id:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Cluster {existing_binding['cluster_id']} is already configured on this connection",
                    )
                raise HTTPException(
                    status_code=409,
                    detail=f"Cluster identity is already bound to connection {existing_binding['connection_id']}; existing cluster {existing_binding['cluster_id']} was not changed",
                )

            current = connection.execute(
                "SELECT location_id, name FROM clusters WHERE id=?",
                (item.cluster_id,),
            ).fetchone()
            if current and current["location_id"] != endpoint["location_id"]:
                raise HTTPException(
                    status_code=409,
                    detail=f"Cluster ID {item.cluster_id} already belongs to another location",
                )
            if current:
                cluster_id = item.cluster_id
                # Existing cluster names and historical rows are intentionally preserved.
            else:
                name_owner = connection.execute(
                    "SELECT id FROM clusters WHERE location_id=? AND name=?",
                    (endpoint["location_id"], item.cluster_name),
                ).fetchone()
                if name_owner:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Cluster name already belongs to {name_owner['id']}; use that existing cluster ID",
                    )
                connection.execute(
                    """INSERT INTO clusters(id, location_id, name, enabled, labels_json)
                       VALUES(?,?,?,1,'{}')""",
                    (item.cluster_id, endpoint["location_id"], item.cluster_name),
                )
                cluster_id = item.cluster_id

            connection.execute(
                """INSERT INTO cluster_prometheus_bindings
                   (cluster_id, connection_id, identity_label_name, identity_label_value)
                   VALUES(?,?,?,?)""",
                (cluster_id, connection_id, item.identity_label_name, item.identity_label_value),
            )
            connection.execute(
                """INSERT INTO settings_audit(setting_key, old_value, new_value, changed_by)
                   VALUES(?,?,?,?)""",
                (
                    f"prometheus_connection:{connection_id}:cluster:{cluster_id}",
                    None,
                    json.dumps({
                        "action": "cluster_approved_and_bound",
                        "cluster_id": cluster_id,
                        "cluster_name": current["name"] if current else item.cluster_name,
                        "identity_label_name": item.identity_label_name,
                        "identity_label_value": item.identity_label_value,
                    }, sort_keys=True),
                    actor.get("username", "unknown"),
                ),
            )
            added.append({
                "cluster_id": cluster_id,
                "cluster_name": current["name"] if current else item.cluster_name,
                "identity_label_name": item.identity_label_name,
                "identity_label_value": item.identity_label_value,
            })

    return {
        "added": True,
        "connection_id": connection_id,
        "approved_cluster_count": len(added),
        "clusters": added,
    }
