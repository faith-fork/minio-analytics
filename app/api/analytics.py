from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user, require_admin
from app.database.database import transaction
from app.services.capacity_report import get_consolidated_capacity_report, get_capacity_factors

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _dict(row) -> dict:
    return dict(row) if row is not None else {}


def _date_window(days: int, start_date: date | None, end_date: date | None) -> tuple[str, str]:
    today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    end = end_date or today_ist
    start = start_date or (end - timedelta(days=days - 1))
    if start > end:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    return start.isoformat(), end.isoformat()


@router.get("/overview")
def overview(_: dict = Depends(get_current_user)) -> dict:
    """Fleet summary from each cluster's latest stored daily snapshot."""
    with transaction() as connection:
        cluster_rows = connection.execute(
            """
            WITH ranked AS (
                SELECT m.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY m.cluster_id
                           ORDER BY m.snapshot_date DESC, m.id DESC
                       ) AS rn
                FROM cluster_daily_metrics m
            )
            SELECT r.cluster_id, c.name AS cluster_name,
                   l.id AS location_id, l.name AS location_name,
                   r.snapshot_date, r.snapshot_ts, r.metrics_available,
                   r.raw_total_bytes, r.raw_free_bytes,
                   r.usable_total_bytes, r.usable_free_bytes,
                   r.nodes_online, r.nodes_offline,
                   r.growth_bytes_per_day,
                   CASE WHEN r.days_to_full BETWEEN 0 AND 1825
                        THEN r.days_to_full ELSE NULL END AS days_to_full,
                   r.error_text
            FROM ranked r
            JOIN clusters c ON c.id = r.cluster_id
            JOIN locations l ON l.id = c.location_id
            WHERE r.rn = 1
            ORDER BY l.name, c.name
            """
        ).fetchall()

        inventory = connection.execute(
            """
            SELECT COUNT(*) AS total_buckets,
                   SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active_buckets,
                   SUM(CASE WHEN is_active = 1 AND tenant_id IS NULL THEN 1 ELSE 0 END)
                       AS unassigned_buckets
            FROM buckets
            """
        ).fetchone()
        tenant_count = connection.execute(
            "SELECT COUNT(*) FROM tenants WHERE is_active = 1"
        ).fetchone()[0]
        latest_bucket = connection.execute(
            "SELECT MAX(snapshot_date) FROM bucket_daily_metrics"
        ).fetchone()[0]
        latest_cluster = connection.execute(
            "SELECT MAX(snapshot_date) FROM cluster_daily_metrics"
        ).fetchone()[0]

    available = [r for r in cluster_rows if r["metrics_available"]]
    sum_fields = (
        "raw_total_bytes",
        "raw_free_bytes",
        "usable_total_bytes",
        "usable_free_bytes",
    )
    complete_cluster_coverage = bool(cluster_rows) and len(available) == len(cluster_rows)
    capacity = {
        field: (
            sum(r[field] for r in available)
            if complete_cluster_coverage
            and all(r[field] is not None for r in available)
            else None
        )
        for field in sum_fields
    }

    return {
        "generated_from": "sqlite",
        "latest_cluster_snapshot_date": latest_cluster,
        "latest_bucket_snapshot_date": latest_bucket,
        "clusters": {
            "total": len(cluster_rows),
            "available": len(available),
            "unavailable": len(cluster_rows) - len(available),
        },
        "capacity_bytes": capacity,
        "nodes": {
            "online": (
                sum(r["nodes_online"] for r in available)
                if complete_cluster_coverage
                and all(r["nodes_online"] is not None for r in available)
                else None
            ),
            "offline": (
                sum(r["nodes_offline"] for r in available)
                if complete_cluster_coverage
                and all(r["nodes_offline"] is not None for r in available)
                else None
            ),
        },
        "inventory": {
            "total_buckets": inventory["total_buckets"] or 0,
            "active_buckets": inventory["active_buckets"] or 0,
            "unassigned_buckets": inventory["unassigned_buckets"] or 0,
            "active_tenants": tenant_count,
        },
        "cluster_items": [_dict(r) for r in cluster_rows],
    }


@router.get("/capacity-report")
def consolidated_capacity_report(_: dict = Depends(get_current_user)) -> dict:
    """Return consolidated fleet capacity and a per-cluster breakdown."""
    return get_consolidated_capacity_report()




class CapacityFactorsUpdate(BaseModel):
    dp: float = Field(gt=0, le=100)
    rf: float = Field(gt=0, le=100)
    eff: float = Field(gt=0, le=1)


@router.get("/capacity-factors")
def capacity_factors(_: dict = Depends(get_current_user)) -> dict:
    """Return the fleet-wide capacity planning factors."""
    return {"factors": get_capacity_factors()}


@router.put("/capacity-factors")
def update_capacity_factors(
    payload: CapacityFactorsUpdate,
    actor: dict = Depends(require_admin),
) -> dict:
    """Persist fleet-wide capacity factors and audit each changed value."""
    updates = {
        "capacity_dp": str(payload.dp),
        "capacity_rf": str(payload.rf),
        "capacity_eff": str(payload.eff),
    }
    with transaction() as connection:
        for key, value in updates.items():
            current = connection.execute(
                "SELECT setting_value FROM app_settings WHERE setting_key = ?",
                (key,),
            ).fetchone()
            old_value = current["setting_value"] if current else None
            if old_value == value:
                continue
            connection.execute(
                """INSERT INTO app_settings
                   (setting_key, setting_value, updated_at, updated_by)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(setting_key) DO UPDATE SET
                     setting_value=excluded.setting_value,
                     updated_at=excluded.updated_at,
                     updated_by=excluded.updated_by""",
                (key, value, datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), actor["username"]),
            )
            connection.execute(
                """INSERT INTO settings_audit
                   (setting_key, old_value, new_value, changed_by)
                   VALUES (?, ?, ?, ?)""",
                (key, old_value, value, actor["username"]),
            )
    return {"updated": True, "factors": get_capacity_factors()}


@router.get("/clusters")
def list_cluster_analytics(_: dict = Depends(get_current_user)) -> dict:
    """Return each cluster's latest capacity and health snapshot."""
    with transaction() as connection:
        rows = connection.execute(
            """
            WITH ranked AS (
                SELECT m.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY m.cluster_id
                           ORDER BY m.snapshot_date DESC, m.id DESC
                       ) AS rn
                FROM cluster_daily_metrics m
            )
            SELECT r.cluster_id, c.name AS cluster_name,
                   l.id AS location_id, l.name AS location_name,
                   r.snapshot_date, r.snapshot_ts, r.collected_at,
                   r.metrics_available, r.raw_total_bytes, r.raw_free_bytes,
                   r.usable_total_bytes, r.usable_free_bytes,
                   r.nodes_online, r.nodes_offline,
                   r.growth_bytes_per_day, r.days_to_full, r.error_text
            FROM ranked r
            JOIN clusters c ON c.id = r.cluster_id
            JOIN locations l ON l.id = c.location_id
            WHERE r.rn = 1
            ORDER BY l.name, c.name
            """
        ).fetchall()
    return {"items": [_dict(row) for row in rows], "count": len(rows)}


@router.get("/clusters/{cluster_id}")
def cluster_analytics(
    cluster_id: str,
    days: int = Query(default=30, ge=1, le=3650),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    _: dict = Depends(get_current_user),
) -> dict:
    """Return one cluster's latest snapshot and daily capacity time series."""
    start, end = _date_window(days, start_date, end_date)
    with transaction() as connection:
        cluster = connection.execute(
            """
            SELECT c.id, c.name, l.id AS location_id, l.name AS location_name
            FROM clusters c JOIN locations l ON l.id = c.location_id
            WHERE c.id = ?
            """,
            (cluster_id,),
        ).fetchone()
        if cluster is None:
            raise HTTPException(status_code=404, detail="Cluster not found")

        latest = connection.execute(
            """
            SELECT snapshot_date, snapshot_ts, collected_at, metrics_available,
                   raw_total_bytes, raw_free_bytes, usable_total_bytes,
                   usable_free_bytes, nodes_online, nodes_offline,
                   growth_bytes_per_day,
                   CASE WHEN days_to_full BETWEEN 0 AND 1825
                        THEN days_to_full ELSE NULL END AS days_to_full,
                   error_text
            FROM cluster_daily_metrics
            WHERE cluster_id = ?
            ORDER BY snapshot_date DESC, id DESC LIMIT 1
            """,
            (cluster_id,),
        ).fetchone()
        rows = connection.execute(
            """
            SELECT snapshot_date, snapshot_ts, metrics_available,
                   raw_total_bytes, raw_free_bytes, usable_total_bytes,
                   usable_free_bytes, nodes_online, nodes_offline,
                   growth_bytes_per_day,
                   CASE WHEN days_to_full BETWEEN 0 AND 1825
                        THEN days_to_full ELSE NULL END AS days_to_full,
                   error_text
            FROM cluster_daily_metrics
            WHERE cluster_id = ? AND snapshot_date BETWEEN ? AND ?
            ORDER BY snapshot_date
            """,
            (cluster_id, start, end),
        ).fetchall()
        bucket_rows = connection.execute(
            """
            SELECT snapshot_date,
                   COUNT(*) AS bucket_metric_rows,
                   (SELECT COUNT(*) FROM buckets
                    WHERE cluster_id = ? AND is_active = 1) AS active_bucket_count,
                   SUM(CASE WHEN quota_bytes IS NOT NULL THEN 1 ELSE 0 END)
                       AS quota_bucket_count,
                   CASE
                       WHEN COUNT(*) = (SELECT COUNT(*) FROM buckets
                                        WHERE cluster_id = ? AND is_active = 1)
                            AND SUM(CASE WHEN metrics_available = 1
                                         AND quota_bytes IS NOT NULL THEN 1 ELSE 0 END) = COUNT(*)
                       THEN SUM(quota_bytes) ELSE NULL
                   END AS bucket_quota_bytes,
                   CASE
                       WHEN COUNT(*) = (SELECT COUNT(*) FROM buckets
                                        WHERE cluster_id = ? AND is_active = 1)
                            AND SUM(CASE WHEN metrics_available = 1
                                         AND object_count IS NOT NULL THEN 1 ELSE 0 END) = COUNT(*)
                       THEN SUM(object_count) ELSE NULL
                   END AS bucket_object_count
            FROM bucket_daily_metrics
            WHERE cluster_id = ? AND snapshot_date BETWEEN ? AND ?
            GROUP BY snapshot_date
            """,
            (cluster_id, cluster_id, cluster_id, cluster_id, start, end),
        ).fetchall()
        bucket_by_date = {row["snapshot_date"]: dict(row) for row in bucket_rows}
        rows = [
            {**dict(row),
             "active_bucket_count": bucket_by_date.get(row["snapshot_date"], {}).get("active_bucket_count"),
             "quota_bucket_count": bucket_by_date.get(row["snapshot_date"], {}).get("quota_bucket_count"),
             "bucket_quota_bytes": bucket_by_date.get(row["snapshot_date"], {}).get("bucket_quota_bytes"),
             "bucket_object_count": bucket_by_date.get(row["snapshot_date"], {}).get("bucket_object_count")}
            for row in rows
        ]

    return {
        "cluster": _dict(cluster),
        "latest": _dict(latest) if latest else None,
        "days": days,
        "start_date": start,
        "end_date": end,
        "series": [_dict(row) for row in rows],
    }


@router.get("/tenants")
def tenant_analytics(_: dict = Depends(get_current_user)) -> dict:
    """Summarize latest bucket metrics grouped by each bucket's current tenant."""
    with transaction() as connection:
        rows = connection.execute(
            """
            WITH ranked AS (
                SELECT m.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY m.bucket_id
                           ORDER BY m.snapshot_date DESC, m.id DESC
                       ) AS rn
                FROM bucket_daily_metrics m
            )
            SELECT b.tenant_id,
                   t.name AS tenant_name,
                   COUNT(b.id) AS bucket_count,
                   SUM(CASE WHEN r.metrics_available = 1 THEN 1 ELSE 0 END)
                       AS buckets_with_metrics,
                   CASE
                       WHEN COUNT(r.bucket_id) = COUNT(b.id)
                            AND SUM(CASE WHEN r.metrics_available = 1 THEN 1 ELSE 0 END) = COUNT(b.id)
                            AND COUNT(r.used_bytes) = COUNT(b.id)
                       THEN SUM(r.used_bytes)
                       ELSE NULL
                   END AS used_bytes,
                   CASE
                       WHEN COUNT(r.bucket_id) = COUNT(b.id)
                            AND SUM(CASE WHEN r.metrics_available = 1 THEN 1 ELSE 0 END) = COUNT(b.id)
                            AND COUNT(r.object_count) = COUNT(b.id)
                       THEN SUM(r.object_count)
                       ELSE NULL
                   END AS object_count,
                   MAX(r.snapshot_date) AS latest_snapshot_date
            FROM buckets b
            LEFT JOIN tenants t ON t.id = b.tenant_id
            LEFT JOIN ranked r ON r.bucket_id = b.id AND r.rn = 1
            GROUP BY b.tenant_id, t.name
            ORDER BY CASE WHEN b.tenant_id IS NULL THEN 1 ELSE 0 END,
                     t.name COLLATE NOCASE
            """
        ).fetchall()
    return {
        "items": [_dict(row) for row in rows],
        "count": len(rows),
        "attribution": "current bucket ownership; usage from each bucket's latest stored snapshot",
    }

@router.get("/tenants/{tenant_id}")
def tenant_analytics_detail(
    tenant_id: int,
    days: int = Query(default=30, ge=1, le=3650),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    attribution: str = Query(default="current", pattern="^(current|historical)$"),
    _: dict = Depends(get_current_user),
) -> dict:
    """Return tenant usage using current ownership or snapshot-time ownership."""
    start, end = _date_window(days, start_date, end_date)
    with transaction() as connection:
        tenant = connection.execute(
            "SELECT id, name, description, is_active FROM tenants WHERE id = ?",
            (tenant_id,),
        ).fetchone()
        if tenant is None:
            raise HTTPException(status_code=404, detail="Tenant not found")

        if attribution == "current":
            # Retrospective view: follow today's bucket-to-tenant mapping back
            # through stored snapshots. Require complete bucket coverage for
            # totals so missing bucket-days are not silently undercounted.
            rows = connection.execute(
                """
                WITH owned_buckets AS (
                    SELECT id FROM buckets WHERE tenant_id = ?
                ),
                snapshot_dates AS (
                    SELECT DISTINCT m.snapshot_date
                    FROM bucket_daily_metrics m
                    JOIN owned_buckets b ON b.id = m.bucket_id
                    WHERE m.snapshot_date BETWEEN ? AND ?
                )
                SELECT d.snapshot_date,
                       COUNT(b.id) AS bucket_count,
                       CASE
                           WHEN COUNT(m.bucket_id) = COUNT(b.id)
                                AND SUM(CASE WHEN m.metrics_available = 1
                                             AND m.used_bytes IS NOT NULL
                                             THEN 1 ELSE 0 END) = COUNT(b.id)
                           THEN SUM(m.used_bytes)
                           ELSE NULL
                       END AS used_bytes,
                       CASE
                           WHEN COUNT(m.bucket_id) = COUNT(b.id)
                                AND SUM(CASE WHEN m.metrics_available = 1
                                             AND m.quota_bytes IS NOT NULL
                                             THEN 1 ELSE 0 END) = COUNT(b.id)
                           THEN SUM(m.quota_bytes)
                           ELSE NULL
                       END AS quota_bytes,
                       CASE
                           WHEN COUNT(m.bucket_id) = COUNT(b.id)
                                AND SUM(CASE WHEN m.metrics_available = 1
                                             AND m.object_count IS NOT NULL
                                             THEN 1 ELSE 0 END) = COUNT(b.id)
                           THEN SUM(m.object_count)
                           ELSE NULL
                       END AS object_count,
                       SUM(CASE WHEN m.bucket_id IS NULL
                                      OR m.metrics_available = 0
                                      OR m.used_bytes IS NULL
                                THEN 1 ELSE 0 END) AS unavailable_bucket_metrics
                FROM snapshot_dates d
                CROSS JOIN owned_buckets b
                LEFT JOIN bucket_daily_metrics m
                    ON m.bucket_id = b.id AND m.snapshot_date = d.snapshot_date
                GROUP BY d.snapshot_date
                ORDER BY d.snapshot_date
                """,
                (tenant_id, start, end),
            ).fetchall()
            attribution_description = (
                "current bucket ownership applied retrospectively to stored daily snapshots"
            )
        else:
            rows = connection.execute(
                """
                SELECT snapshot_date,
                       COUNT(DISTINCT bucket_id) AS bucket_count,
                       CASE
                           WHEN SUM(CASE WHEN metrics_available = 1 THEN 1 ELSE 0 END) = COUNT(*)
                                AND COUNT(used_bytes) = COUNT(*)
                           THEN SUM(used_bytes)
                           ELSE NULL
                       END AS used_bytes,
                       CASE
                           WHEN SUM(CASE WHEN metrics_available = 1 THEN 1 ELSE 0 END) = COUNT(*)
                                AND COUNT(quota_bytes) = COUNT(*)
                           THEN SUM(quota_bytes)
                           ELSE NULL
                       END AS quota_bytes,
                       CASE
                           WHEN SUM(CASE WHEN metrics_available = 1 THEN 1 ELSE 0 END) = COUNT(*)
                                AND COUNT(object_count) = COUNT(*)
                           THEN SUM(object_count)
                           ELSE NULL
                       END AS object_count,
                       SUM(CASE WHEN metrics_available = 0 THEN 1 ELSE 0 END)
                           AS unavailable_bucket_metrics
                FROM bucket_daily_metrics
                WHERE tenant_id_at_snapshot = ? AND snapshot_date BETWEEN ? AND ?
                GROUP BY snapshot_date
                ORDER BY snapshot_date
                """,
                (tenant_id, start, end),
            ).fetchall()
            attribution_description = "tenant_id_at_snapshot"

    return {
        "tenant": _dict(tenant),
        "days": days,
        "start_date": start,
        "end_date": end,
        "attribution": attribution,
        "attribution_description": attribution_description,
        "series": [_dict(row) for row in rows],
    }


@router.get("/buckets/{bucket_id}")
def bucket_analytics(
    bucket_id: int,
    days: int = Query(default=30, ge=1, le=3650),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    _: dict = Depends(get_current_user),
) -> dict:
    """Return bucket usage history, preserving snapshot-time tenant attribution."""
    start, end = _date_window(days, start_date, end_date)
    with transaction() as connection:
        bucket = connection.execute(
            """
            SELECT b.id, b.cluster_id, c.name AS cluster_name,
                   b.bucket_name, b.tenant_id AS current_tenant_id,
                   t.name AS current_tenant_name, b.is_active
            FROM buckets b
            JOIN clusters c ON c.id = b.cluster_id
            LEFT JOIN tenants t ON t.id = b.tenant_id
            WHERE b.id = ?
            """,
            (bucket_id,),
        ).fetchone()
        if bucket is None:
            raise HTTPException(status_code=404, detail="Bucket not found")

        rows = connection.execute(
            """
            SELECT m.snapshot_date, m.snapshot_ts, m.collected_at,
                   m.tenant_id_at_snapshot, st.name AS tenant_name_at_snapshot,
                   m.used_bytes, m.quota_bytes, m.object_count,
                   m.version_count, m.delete_marker_count,
                   m.object_size_distribution_json,
                   m.version_count_distribution_json,
                   m.metrics_available, m.error_text
            FROM bucket_daily_metrics m
            LEFT JOIN tenants st ON st.id = m.tenant_id_at_snapshot
            WHERE m.bucket_id = ? AND m.snapshot_date BETWEEN ? AND ?
            ORDER BY m.snapshot_date
            """,
            (bucket_id, start, end),
        ).fetchall()

    series = []
    for row in rows:
        item = _dict(row)
        for field in ("object_size_distribution_json", "version_count_distribution_json"):
            raw = item.pop(field)
            try:
                item[field.removesuffix("_json")] = json.loads(raw or "{}")
            except (TypeError, json.JSONDecodeError):
                item[field.removesuffix("_json")] = None
        series.append(item)

    return {"bucket": _dict(bucket), "days": days, "start_date": start, "end_date": end, "series": series}



@router.get("/object-size-distribution/{scope}/{entity_id}")
def object_size_distribution(
    scope: str,
    entity_id: str,
    attribution: str = Query(default="current", pattern="^(current|historical)$"),
    _: dict = Depends(get_current_user),
) -> dict:
    """Aggregate the latest stored MinIO object-size histogram for an entity."""
    if scope not in {"bucket", "tenant", "cluster"}:
        raise HTTPException(status_code=404, detail="Unknown distribution scope")

    with transaction() as connection:
        if scope == "bucket":
            try:
                bucket_id = int(entity_id)
            except ValueError:
                raise HTTPException(status_code=422, detail="Invalid bucket ID")
            entity = connection.execute(
                "SELECT id, bucket_name AS name FROM buckets WHERE id = ?",
                (bucket_id,),
            ).fetchone()
            if entity is None:
                raise HTTPException(status_code=404, detail="Bucket not found")
            bucket_ids = [bucket_id]
            latest = connection.execute(
                "SELECT MAX(snapshot_date) FROM bucket_daily_metrics WHERE bucket_id = ?",
                (bucket_id,),
            ).fetchone()[0]
        elif scope == "cluster":
            entity = connection.execute(
                "SELECT id, name FROM clusters WHERE id = ?", (entity_id,)
            ).fetchone()
            if entity is None:
                raise HTTPException(status_code=404, detail="Cluster not found")
            bucket_ids = [
                row[0] for row in connection.execute(
                    "SELECT id FROM buckets WHERE cluster_id = ? AND is_active = 1",
                    (entity_id,),
                )
            ]
            latest = connection.execute(
                "SELECT MAX(snapshot_date) FROM bucket_daily_metrics WHERE cluster_id = ?",
                (entity_id,),
            ).fetchone()[0]
        else:
            try:
                tenant_id = int(entity_id)
            except ValueError:
                raise HTTPException(status_code=422, detail="Invalid tenant ID")
            entity = connection.execute(
                "SELECT id, name FROM tenants WHERE id = ?", (tenant_id,)
            ).fetchone()
            if entity is None:
                raise HTTPException(status_code=404, detail="Tenant not found")
            if attribution == "current":
                bucket_ids = [
                    row[0] for row in connection.execute(
                        "SELECT id FROM buckets WHERE tenant_id = ? AND is_active = 1",
                        (tenant_id,),
                    )
                ]
                latest = connection.execute(
                    """SELECT MAX(m.snapshot_date)
                       FROM bucket_daily_metrics m
                       JOIN buckets b ON b.id = m.bucket_id
                       WHERE b.tenant_id = ? AND b.is_active = 1""",
                    (tenant_id,),
                ).fetchone()[0]
            else:
                bucket_ids = [
                    row[0] for row in connection.execute(
                        """SELECT DISTINCT bucket_id FROM bucket_daily_metrics
                           WHERE tenant_id_at_snapshot = ?""",
                        (tenant_id,),
                    )
                ]
                latest = connection.execute(
                    """SELECT MAX(snapshot_date) FROM bucket_daily_metrics
                       WHERE tenant_id_at_snapshot = ?""",
                    (tenant_id,),
                ).fetchone()[0]

        if not bucket_ids or not latest:
            return {
                "scope": scope, "entity": _dict(entity), "attribution": attribution,
                "snapshot_date": latest, "distribution": [], "total_objects": None,
                "buckets_expected": len(bucket_ids), "buckets_available": 0,
                "buckets_missing": len(bucket_ids), "status": "unavailable",
            }

        placeholders = ",".join("?" for _ in bucket_ids)
        rows = connection.execute(
            f"""SELECT bucket_id, object_size_distribution_json,
                       metrics_available, object_count
                FROM bucket_daily_metrics
                WHERE snapshot_date = ? AND bucket_id IN ({placeholders})""",
            [latest, *bucket_ids],
        ).fetchall()

    distributions = []
    available_bucket_ids = set()
    totals: dict[str, int] = {}
    object_totals = []
    for row in rows:
        if not row["metrics_available"]:
            continue
        try:
            item = json.loads(row["object_size_distribution_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            item = {}
        if not isinstance(item, dict) or not item:
            continue
        available_bucket_ids.add(row["bucket_id"])
        for range_name, count in item.items():
            try:
                value = int(count)
            except (TypeError, ValueError):
                continue
            if value < 0:
                continue
            totals[range_name] = totals.get(range_name, 0) + value
        if row["object_count"] is not None:
            object_totals.append(int(row["object_count"]))

    expected = len(bucket_ids)
    available = len(available_bucket_ids)
    complete = available == expected and bool(totals)
    total = sum(totals.values()) if complete else None
    distribution = [
        {
            "range": name,
            "object_count": count,
            "percentage": (count / total * 100) if total else None,
        }
        for name, count in sorted(totals.items(), key=lambda item: item[0])
    ]
    return {
        "scope": scope,
        "entity": _dict(entity),
        "attribution": attribution,
        "snapshot_date": latest,
        "distribution": distribution,
        "total_objects": total,
        "buckets_expected": expected,
        "buckets_available": available,
        "buckets_missing": expected - available,
        "status": "available" if complete else ("partial" if available else "unavailable"),
    }


@router.get("/collection-health")
def collection_health(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=5, le=100),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(success|partial|failed)$"),
    _: dict = Depends(get_current_user),
) -> dict:
    """Return scheduler cadence, collector history and latest infrastructure health."""
    now = datetime.now(timezone.utc)
    now_text = now.isoformat(timespec="seconds").replace("+00:00", "Z")

    with transaction() as connection:
        settings = {
            row["setting_key"]: row["setting_value"]
            for row in connection.execute(
                "SELECT setting_key, setting_value FROM app_settings"
            ).fetchall()
        }
        scheduler_rows = connection.execute(
            "SELECT job_key, last_started_at, last_completed_at, last_status, last_error "
            "FROM scheduler_state"
        ).fetchall()
        scheduler_state = {row["job_key"]: _dict(row) for row in scheduler_rows}

        counts = connection.execute(
            "SELECT status, COUNT(*) AS count FROM collection_runs GROUP BY status"
        ).fetchall()
        if start_date and end_date and start_date > end_date:
            raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
        filters = []
        params: list[object] = []
        if start_date:
            filters.append("r.snapshot_date >= ?")
            params.append(start_date.isoformat())
        if end_date:
            filters.append("r.snapshot_date <= ?")
            params.append(end_date.isoformat())
        if status:
            filters.append("r.status = ?")
            params.append(status)
        where_sql = " WHERE " + " AND ".join(filters) if filters else ""
        filtered_count = connection.execute(
            "SELECT COUNT(*) AS total FROM collection_runs r" + where_sql,
            params,
        ).fetchone()["total"]
        total_pages = max(1, (filtered_count + page_size - 1) // page_size)
        if page > total_pages and filtered_count:
            page = total_pages
        offset = (page - 1) * page_size
        rows = connection.execute(
            """
            SELECT r.id, r.run_id, r.snapshot_date, r.location_id,
                   l.name AS location_name, r.cluster_id, c.name AS cluster_name,
                   r.started_at, r.finished_at, r.status, r.attempt,
                   r.metrics_collected, r.error_text, r.details_json
            FROM collection_runs r
            LEFT JOIN locations l ON l.id = r.location_id
            LEFT JOIN clusters c ON c.id = r.cluster_id
            """ + where_sql + """
            ORDER BY r.started_at DESC, r.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()

        cluster_rows = connection.execute(
            """
            SELECT c.id AS cluster_id, c.name AS cluster_name,
                   l.id AS location_id, l.name AS location_name, c.enabled
            FROM clusters c
            JOIN locations l ON l.id = c.location_id
            ORDER BY l.name, c.name
            """
        ).fetchall()
        latest_daily_rows = connection.execute(
            """
            WITH ranked AS (
                SELECT r.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY r.cluster_id
                           ORDER BY r.started_at DESC, r.id DESC
                       ) AS rn
                FROM collection_runs r
            )
            SELECT r.*, l.name AS location_name, c.name AS cluster_name
            FROM ranked r
            LEFT JOIN locations l ON l.id = r.location_id
            LEFT JOIN clusters c ON c.id = r.cluster_id
            WHERE r.rn = 1
            """
        ).fetchall()
        latest_node_rows = connection.execute(
            """
            WITH ranked AS (
                SELECT h.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY h.cluster_id
                           ORDER BY h.snapshot_ts DESC, h.id DESC
                       ) AS rn
                FROM node_health_runs h
            )
            SELECT h.*, c.name AS cluster_name, l.name AS location_name
            FROM ranked h
            JOIN clusters c ON c.id = h.cluster_id
            JOIN locations l ON l.id = c.location_id
            WHERE h.rn = 1
            """
        ).fetchall()

        node_health = []
        for run in latest_node_rows:
            nodes = connection.execute(
                """
                SELECT COUNT(*) AS node_count,
                       SUM(CASE WHEN node_exporter_up = 1 THEN 1 ELSE 0 END) AS node_exporter_up,
                       SUM(CASE WHEN minio_scrape_up = 1 THEN 1 ELSE 0 END) AS minio_scrape_up,
                       SUM(CASE WHEN node_exporter_up = 0 THEN 1 ELSE 0 END) AS node_exporter_down,
                       SUM(CASE WHEN minio_scrape_up = 0 THEN 1 ELSE 0 END) AS minio_scrape_down
                FROM node_health_metrics WHERE run_id = ?
                """,
                (run["run_id"],),
            ).fetchone()
            drives = connection.execute(
                """
                SELECT COUNT(*) AS drive_count,
                       SUM(CASE WHEN availability_errors > 0 THEN 1 ELSE 0 END) AS availability_error_drives,
                       SUM(CASE WHEN io_errors > 0 THEN 1 ELSE 0 END) AS io_error_drives,
                       SUM(CASE WHEN timeout_errors > 0 THEN 1 ELSE 0 END) AS timeout_error_drives,
                       SUM(CASE WHEN filesystem_readonly = 1 THEN 1 ELSE 0 END) AS readonly_filesystems
                FROM drive_health_metrics WHERE run_id = ?
                """,
                (run["run_id"],),
            ).fetchone()
            try:
                family_errors = json.loads(run["family_errors_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                family_errors = {"_parse_error": "Unable to parse family error details"}
            node_health.append({
                "cluster_id": run["cluster_id"],
                "cluster_name": run["cluster_name"],
                "location_name": run["location_name"],
                "run_id": run["run_id"],
                "snapshot_ts": run["snapshot_ts"],
                "collected_at": run["collected_at"],
                "family_errors": family_errors,
                "counts": {
                    **_dict(nodes),
                    **_dict(drives),
                },
                "status": "partial" if family_errors else "success",
            })

    items = []
    for row in rows:
        item = _dict(row)
        try:
            item["details"] = json.loads(item.pop("details_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["details"] = None
            item.pop("details_json", None)
        items.append(item)

    interval_hours = int(settings.get("node_interval_hours", "4"))
    daily_time = settings.get("daily_collection_time", "00:15")
    node_state = scheduler_state.get("node_health", {})
    daily_state = scheduler_state.get("daily_collection", {})

    def _parse_utc(value: str | None):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None

    node_completed = _parse_utc(node_state.get("last_completed_at"))
    next_node = (node_completed or now) + timedelta(hours=interval_hours)

    hh, mm = (int(part) for part in daily_time.split(":"))
    local_now = now.astimezone(ZoneInfo("Asia/Kolkata"))
    scheduled_today = datetime.combine(
        local_now.date(), datetime.min.time().replace(hour=hh, minute=mm),
        tzinfo=ZoneInfo("Asia/Kolkata"),
    )
    daily_completed = _parse_utc(daily_state.get("last_completed_at"))
    if daily_completed and daily_completed.astimezone(ZoneInfo("Asia/Kolkata")).date() >= local_now.date():
        next_daily = scheduled_today + timedelta(days=1)
    elif local_now <= scheduled_today:
        next_daily = scheduled_today
    else:
        next_daily = local_now + timedelta(seconds=60)

    return {
        "generated_at": now_text,
        "schedule": {
            "timezone": "Asia/Kolkata",
            "node_interval_hours": interval_hours,
            "daily_collection_time": daily_time,
            "scheduler_tick_seconds": 60,
            "jobs": {
                "node_health": {
                    **node_state,
                    "next_expected_at": next_node.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                },
                "daily_collection": {
                    **daily_state,
                    "next_expected_at": next_daily.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                },
            },
        },
        "status_counts": {row["status"]: row["count"] for row in counts},
        "cluster_daily_status": [
            {
                "cluster_id": cluster["cluster_id"],
                "cluster_name": cluster["cluster_name"],
                "location_id": cluster["location_id"],
                "location_name": cluster["location_name"],
                "enabled": bool(cluster["enabled"]),
                "latest_run": next(
                    (_dict(run) for run in latest_daily_rows if run["cluster_id"] == cluster["cluster_id"]),
                    None,
                ),
            }
            for cluster in cluster_rows
        ],
        "node_health": node_health,
        "recent_runs": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": filtered_count,
            "total_pages": total_pages,
            "has_previous": page > 1,
            "has_next": page < total_pages,
        },
        "filters": {
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "status": status,
        },
        "count": len(items),
    }


@router.get("/clusters/{cluster_id}/topology/trends")
def collection_health_trends(
    cluster_id: str,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    _: dict = Depends(get_current_user),
) -> dict:
    """Return historical node and drive telemetry from persisted four-hour samples."""
    today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    end = end_date or today_ist
    start = start_date or (end - timedelta(days=29))
    if start > end:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    ist = ZoneInfo("Asia/Kolkata")
    start_utc = datetime.combine(start, datetime.min.time(), tzinfo=ist).astimezone(timezone.utc)
    end_utc = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=ist).astimezone(timezone.utc)
    start_text = start_utc.isoformat(timespec="seconds").replace("+00:00", "Z")
    end_text = end_utc.isoformat(timespec="seconds").replace("+00:00", "Z")

    with transaction() as connection:
        cluster = connection.execute(
            """SELECT c.id AS cluster_id,c.name AS cluster_name,l.name AS location_name
               FROM clusters c JOIN locations l ON l.id=c.location_id
               WHERE c.id=? AND c.enabled=1""",
            (cluster_id,),
        ).fetchone()
        if cluster is None:
            raise HTTPException(status_code=404, detail="Cluster not found or disabled")
        sql = """
            SELECT r.run_id,r.cluster_id,c.name AS cluster_name,l.name AS location_name,
                   r.snapshot_ts,r.collected_at,r.node_count AS recorded_node_count,
                   r.drive_count AS recorded_drive_count,r.family_errors_json,
                   n.node_count,n.node_exporter_up,n.minio_scrape_up,
                   n.avg_cpu_pct,n.memory_total_bytes,n.memory_used_bytes,
                   n.drives_online,n.drives_offline,
                   d.drive_count AS measured_drive_count,d.availability_error_drives,
                   d.io_error_drives,d.timeout_error_drives,d.availability_errors,
                   d.io_errors,d.timeout_errors,d.filesystem_used_bytes,
                   d.filesystem_total_bytes,d.filesystem_used_pct,
                   d.readonly_filesystems
            FROM node_health_runs r
            JOIN clusters c ON c.id=r.cluster_id
            JOIN locations l ON l.id=c.location_id
            LEFT JOIN (
                SELECT run_id,COUNT(*) AS node_count,
                       SUM(CASE WHEN node_exporter_up=1 THEN 1 ELSE 0 END) AS node_exporter_up,
                       SUM(CASE WHEN minio_scrape_up=1 THEN 1 ELSE 0 END) AS minio_scrape_up,
                       AVG(cpu_utilization_pct) AS avg_cpu_pct,
                       SUM(memory_total_bytes) AS memory_total_bytes,
                       SUM(memory_used_bytes) AS memory_used_bytes,
                       SUM(drives_online) AS drives_online,
                       SUM(drives_offline) AS drives_offline
                FROM node_health_metrics GROUP BY run_id
            ) n ON n.run_id=r.run_id
            LEFT JOIN (
                SELECT run_id,COUNT(*) AS drive_count,
                       SUM(CASE WHEN availability_errors>0 THEN 1 ELSE 0 END) AS availability_error_drives,
                       SUM(CASE WHEN io_errors>0 THEN 1 ELSE 0 END) AS io_error_drives,
                       SUM(CASE WHEN timeout_errors>0 THEN 1 ELSE 0 END) AS timeout_error_drives,
                       SUM(availability_errors) AS availability_errors,
                       SUM(io_errors) AS io_errors,
                       SUM(timeout_errors) AS timeout_errors,
                       SUM(filesystem_used_bytes) AS filesystem_used_bytes,
                       SUM(filesystem_total_bytes) AS filesystem_total_bytes,
                       AVG(filesystem_used_pct) AS filesystem_used_pct,
                       SUM(CASE WHEN filesystem_readonly=1 THEN 1 ELSE 0 END) AS readonly_filesystems
                FROM drive_health_metrics GROUP BY run_id
            ) d ON d.run_id=r.run_id
            WHERE r.snapshot_ts>=? AND r.snapshot_ts<?
        """
        params: list[object] = [start_text, end_text]
        sql += " AND r.cluster_id=?"
        params.append(cluster_id)
        sql += " ORDER BY r.snapshot_ts,r.cluster_id"
        rows = connection.execute(sql, params).fetchall()

    samples = []
    for row in rows:
        item = _dict(row)
        try:
            family_errors = json.loads(item.pop("family_errors_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            family_errors = {"_parse_error": "Unable to parse family error details"}
        node_count = item.get("node_count") or 0
        item["node_exporter_availability_pct"] = (
            item["node_exporter_up"] / node_count * 100
            if node_count and item.get("node_exporter_up") is not None else None
        )
        item["minio_scrape_availability_pct"] = (
            item["minio_scrape_up"] / node_count * 100
            if node_count and item.get("minio_scrape_up") is not None else None
        )
        memory_total = item.get("memory_total_bytes")
        item["memory_used_pct"] = (
            item["memory_used_bytes"] / memory_total * 100
            if memory_total and item.get("memory_used_bytes") is not None else None
        )
        fs_total = item.get("filesystem_total_bytes")
        item["filesystem_weighted_used_pct"] = (
            item["filesystem_used_bytes"] / fs_total * 100
            if fs_total and item.get("filesystem_used_bytes") is not None else None
        )
        item["family_errors"] = family_errors
        samples.append(item)

    return {
        "cluster_id": cluster_id,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "cluster": _dict(cluster),
        "samples": samples,
        "sample_count": len(samples),
    }


@router.get("/clusters/{cluster_id}/topology")
def cluster_topology(cluster_id: str, _: dict = Depends(get_current_user)) -> dict:
    """Return latest high-frequency node/drive health and daily pool topology."""
    with transaction() as connection:
        cluster = connection.execute(
            """SELECT c.id,c.name,l.name AS location_name FROM clusters c
               JOIN locations l ON l.id=c.location_id WHERE c.id=?""",(cluster_id,)
        ).fetchone()
        if cluster is None: raise HTTPException(status_code=404,detail="Cluster not found")
        run=connection.execute(
            "SELECT * FROM topology_daily_runs WHERE cluster_id=? ORDER BY snapshot_date DESC,id DESC LIMIT 1",
            (cluster_id,)
        ).fetchone()
        health=connection.execute(
            "SELECT * FROM node_health_runs WHERE cluster_id=? ORDER BY snapshot_ts DESC,id DESC LIMIT 1",
            (cluster_id,)
        ).fetchone()
        if health:
            nodes=connection.execute("SELECT * FROM node_health_metrics WHERE run_id=? ORDER BY node_name",(health["run_id"],)).fetchall()
            drives=connection.execute("SELECT * FROM drive_health_metrics WHERE run_id=? ORDER BY node_name,drive_path",(health["run_id"],)).fetchall()
            try: health_errors=json.loads(health["family_errors_json"] or "{}")
            except (TypeError,json.JSONDecodeError): health_errors={}
            node_ts=health["snapshot_ts"]; node_collected=health["collected_at"]
        else:
            if run:
                legacy_day=run["snapshot_date"]
                nodes=connection.execute("SELECT * FROM node_daily_metrics WHERE cluster_id=? AND snapshot_date=? ORDER BY node_name",(cluster_id,legacy_day)).fetchall()
                drives=connection.execute("SELECT * FROM drive_daily_metrics WHERE cluster_id=? AND snapshot_date=? ORDER BY node_name,drive_path",(cluster_id,legacy_day)).fetchall()
                node_ts=run["snapshot_ts"]; node_collected=run["collected_at"]
            else:
                nodes=[]; drives=[]; node_ts=None; node_collected=None
            health_errors={}
        if run:
            day=run["snapshot_date"]
            pools=connection.execute("SELECT * FROM pool_daily_metrics WHERE cluster_id=? AND snapshot_date=? ORDER BY pool_id",(cluster_id,day)).fetchall()
            sets=connection.execute("SELECT * FROM erasure_set_daily_metrics WHERE cluster_id=? AND snapshot_date=? ORDER BY pool_id,set_id",(cluster_id,day)).fetchall()
            try: daily_errors=json.loads(run["family_errors_json"] or "{}")
            except (TypeError,json.JSONDecodeError): daily_errors={}
            pool_ts=run["snapshot_ts"]; pool_collected=run["collected_at"]
        else:
            pools=[]; sets=[]; daily_errors={}; pool_ts=None; pool_collected=None
    errors={**daily_errors,**health_errors}
    return {
        "cluster":_dict(cluster),
        "snapshot_date":run["snapshot_date"] if run else None,
        "snapshot_ts":node_ts or pool_ts,
        "collected_at":node_collected or pool_collected,
        "node_snapshot_ts":node_ts,
        "node_collected_at":node_collected,
        "topology_snapshot_ts":pool_ts,
        "topology_collected_at":pool_collected,
        "family_errors":errors,
        "counts":{"nodes":len(nodes),"drives":len(drives),"pools":len(pools),"erasure_sets":len(sets)},
        "nodes":[_dict(r) for r in nodes],
        "drives":[_dict(r) for r in drives],
        "pools":[_dict(r) for r in pools],
        "erasure_sets":[_dict(r) for r in sets],
    }
