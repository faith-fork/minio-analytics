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
            WHERE cluster_id = ? AND snapshot_date BETWEEN ? AND ?
            ORDER BY snapshot_date
            """,
            (cluster_id, start, end),
        ).fetchall()
        bucket_rows = connection.execute(
            """
            SELECT snapshot_date,
                   COUNT(*) AS bucket_metric_rows,
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
            (cluster_id, cluster_id, cluster_id, start, end),
        ).fetchall()
        bucket_by_date = {row["snapshot_date"]: dict(row) for row in bucket_rows}
        rows = [
            {**dict(row),
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
