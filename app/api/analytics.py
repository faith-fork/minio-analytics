from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import get_current_user
from app.database.database import transaction

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _dict(row) -> dict:
    return dict(row) if row is not None else {}


def _window_start(days: int) -> str:
    today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    return (today_ist - timedelta(days=days - 1)).isoformat()


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
                   r.growth_bytes_per_day, r.days_to_full, r.error_text
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
    _: dict = Depends(get_current_user),
) -> dict:
    """Return one cluster's latest snapshot and daily capacity time series."""
    start = _window_start(days)
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
                   growth_bytes_per_day, days_to_full, error_text
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
                   growth_bytes_per_day, days_to_full, error_text
            FROM cluster_daily_metrics
            WHERE cluster_id = ? AND snapshot_date >= ?
            ORDER BY snapshot_date
            """,
            (cluster_id, start),
        ).fetchall()

    return {
        "cluster": _dict(cluster),
        "latest": _dict(latest) if latest else None,
        "days": days,
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
    attribution: str = Query(default="current", pattern="^(current|historical)$"),
    _: dict = Depends(get_current_user),
) -> dict:
    """Return tenant usage using current ownership or snapshot-time ownership."""
    start = _window_start(days)
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
                    WHERE m.snapshot_date >= ?
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
                (tenant_id, start),
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
                                AND COUNT(object_count) = COUNT(*)
                           THEN SUM(object_count)
                           ELSE NULL
                       END AS object_count,
                       SUM(CASE WHEN metrics_available = 0 THEN 1 ELSE 0 END)
                           AS unavailable_bucket_metrics
                FROM bucket_daily_metrics
                WHERE tenant_id_at_snapshot = ? AND snapshot_date >= ?
                GROUP BY snapshot_date
                ORDER BY snapshot_date
                """,
                (tenant_id, start),
            ).fetchall()
            attribution_description = "tenant_id_at_snapshot"

    return {
        "tenant": _dict(tenant),
        "days": days,
        "attribution": attribution,
        "attribution_description": attribution_description,
        "series": [_dict(row) for row in rows],
    }


@router.get("/buckets/{bucket_id}")
def bucket_analytics(
    bucket_id: int,
    days: int = Query(default=30, ge=1, le=3650),
    _: dict = Depends(get_current_user),
) -> dict:
    """Return bucket usage history, preserving snapshot-time tenant attribution."""
    start = _window_start(days)
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
            WHERE m.bucket_id = ? AND m.snapshot_date >= ?
            ORDER BY m.snapshot_date
            """,
            (bucket_id, start),
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

    return {"bucket": _dict(bucket), "days": days, "series": series}


@router.get("/collection-health")
def collection_health(
    limit: int = Query(default=20, ge=1, le=200),
    _: dict = Depends(get_current_user),
) -> dict:
    """Return collection status counts and the most recent collection runs."""
    with transaction() as connection:
        counts = connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM collection_runs
            GROUP BY status
            """
        ).fetchall()
        rows = connection.execute(
            """
            SELECT r.id, r.run_id, r.snapshot_date, r.location_id,
                   l.name AS location_name, r.cluster_id, c.name AS cluster_name,
                   r.started_at, r.finished_at, r.status, r.attempt,
                   r.metrics_collected, r.error_text, r.details_json
            FROM collection_runs r
            LEFT JOIN locations l ON l.id = r.location_id
            LEFT JOIN clusters c ON c.id = r.cluster_id
            ORDER BY r.started_at DESC, r.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    items = []
    for row in rows:
        item = _dict(row)
        try:
            item["details"] = json.loads(item.pop("details_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["details"] = None
            item.pop("details_json", None)
        items.append(item)

    return {
        "status_counts": {row["status"]: row["count"] for row in counts},
        "recent_runs": items,
        "count": len(items),
    }
