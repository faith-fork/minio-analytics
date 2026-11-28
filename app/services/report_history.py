from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.database.database import transaction
from app.services.capacity_report import get_capacity_factors

IST = ZoneInfo("Asia/Kolkata")
MAX_HISTORY_DAYS = 3650


def _bounds(start_date: date | None, end_date: date | None, days: int = 90) -> tuple[str, str]:
    today = datetime.now(IST).date()
    end = end_date or today
    start = start_date or end - timedelta(days=days - 1)
    if start > end:
        raise ValueError("start_date must be on or before end_date")
    if (end - start).days + 1 > MAX_HISTORY_DAYS:
        raise ValueError(f"Historical range cannot exceed {MAX_HISTORY_DAYS} days")
    if end > today:
        raise ValueError("end_date cannot be in the future")
    return start.isoformat(), end.isoformat()


def _days(start: str, end: str) -> list[str]:
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    return [(first + timedelta(days=i)).isoformat() for i in range((last-first).days+1)]


def _series_point(day: str, *, coverage: dict, complete: bool, values: dict) -> dict:
    return {"date": day, "complete": complete, "coverage": coverage, **values}


def _active_cluster_count(connection) -> int:
    return connection.execute(
        """SELECT COUNT(*) FROM clusters c JOIN locations l ON l.id=c.location_id
           WHERE c.enabled=1 AND l.enabled=1"""
    ).fetchone()[0]


def get_provisioned_report_history(start_date: date | None = None, end_date: date | None = None) -> dict:
    start, end = _bounds(start_date, end_date)
    with transaction() as connection:
        cluster_count = _active_cluster_count(connection)
        factors = get_capacity_factors(connection)
        installed_factor = factors["eff"] * (factors["rf"] / factors["dp"])
        rows = connection.execute(
            """SELECT m.snapshot_date, m.cluster_id, m.metrics_available,
                      m.raw_total_bytes, m.usable_total_bytes, m.usable_free_bytes
               FROM cluster_daily_metrics m
               JOIN clusters c ON c.id=m.cluster_id AND c.enabled=1
               JOIN locations l ON l.id=c.location_id AND l.enabled=1
               WHERE m.snapshot_date BETWEEN ? AND ?
               ORDER BY m.snapshot_date, m.cluster_id""",
            (start, end),
        ).fetchall()
        bucket_rows = connection.execute(
            """SELECT b.snapshot_date, b.cluster_id,
                      COUNT(*) AS observed_buckets,
                      SUM(CASE WHEN b.metrics_available=1 AND b.used_bytes IS NOT NULL
                               THEN 1 ELSE 0 END) AS usage_available,
                      SUM(CASE WHEN b.metrics_available=1 AND b.quota_bytes IS NOT NULL
                               THEN 1 ELSE 0 END) AS quota_available,
                      SUM(CASE WHEN b.metrics_available=1 AND b.used_bytes IS NOT NULL
                               THEN b.used_bytes ELSE NULL END) AS used_bytes,
                      SUM(CASE WHEN b.metrics_available=1 AND b.quota_bytes IS NOT NULL
                               THEN b.quota_bytes ELSE NULL END) AS quota_bytes,
                      r.status AS collection_status
               FROM bucket_daily_metrics b
               JOIN clusters c ON c.id=b.cluster_id AND c.enabled=1
               JOIN locations l ON l.id=c.location_id AND l.enabled=1
               LEFT JOIN (
                    SELECT cluster_id, snapshot_date, status,
                           ROW_NUMBER() OVER (
                               PARTITION BY cluster_id, snapshot_date
                               ORDER BY started_at DESC, id DESC
                           ) AS rn
                    FROM collection_runs
                ) r ON r.cluster_id=b.cluster_id
                    AND r.snapshot_date=b.snapshot_date AND r.rn=1
               WHERE b.snapshot_date BETWEEN ? AND ?
               GROUP BY b.snapshot_date, b.cluster_id, r.status
               ORDER BY b.snapshot_date, b.cluster_id""",
            (start, end),
        ).fetchall()

    by_day: dict[str, list] = {}
    for row in rows:
        by_day.setdefault(row["snapshot_date"], []).append(row)
    bucket_by_day: dict[str, list] = {}
    for row in bucket_rows:
        bucket_by_day.setdefault(row["snapshot_date"], []).append(row)

    dates = _days(start, end)
    points = []
    for day in dates:
        clusters = by_day.get(day, [])
        valid = [r for r in clusters if r["metrics_available"] == 1 and
                 r["raw_total_bytes"] is not None and r["usable_total_bytes"] is not None and
                 r["usable_free_bytes"] is not None]
        complete = cluster_count > 0 and len(clusters) == cluster_count and len(valid) == cluster_count
        if complete:
            usable_total = sum(float(r["usable_total_bytes"]) for r in valid)
            usable_free = sum(float(r["usable_free_bytes"]) for r in valid)
            used = usable_total - usable_free
            installed = sum(float(r["raw_total_bytes"]) for r in valid) * installed_factor
            utilization = used / installed * 100 if installed > 0 else None
        else:
            usable_total = usable_free = used = installed = utilization = None

        buckets = bucket_by_day.get(day, [])
        observed = sum(int(r["observed_buckets"] or 0) for r in buckets)
        usage_complete = bool(buckets) and all(
            r["collection_status"] == "success" and
            r["usage_available"] == r["observed_buckets"] and r["observed_buckets"] > 0
            for r in buckets
        )
        quota_complete = bool(buckets) and all(
            r["collection_status"] == "success" and
            r["quota_available"] == r["observed_buckets"] and r["observed_buckets"] > 0
            for r in buckets
        )
        used_bucket = sum(float(r["used_bytes"] or 0) for r in buckets) if usage_complete else None
        quota = sum(float(r["quota_bytes"] or 0) for r in buckets) if quota_complete else None
        quota_remaining = quota - used_bucket if quota is not None and used_bucket is not None else None
        points.append(_series_point(
            day,
            coverage={
                "enabled_clusters": cluster_count,
                "cluster_snapshots": len(clusters),
                "cluster_metrics_available": len(valid),
                "bucket_observed": observed,
                "bucket_clusters": len(buckets),
                "bucket_usage_collection_complete": usage_complete,
                "bucket_quota_collection_complete": quota_complete,
                "bucket_coverage_basis": "observed bucket records and successful collection run; historical bucket inventory denominator is not persisted",
            },
            complete=complete,
            values={
                "installed_capacity_bytes": installed,
                "usable_total_bytes": usable_total,
                "usable_used_bytes": used,
                "usable_free_bytes": usable_free,
                "utilization_pct": utilization,
                "bucket_used_bytes": used_bucket,
                "bucket_quota_bytes": quota,
                "bucket_quota_remaining_bytes": quota_remaining,
            },
        ))
    return {
        "report": "provisioned",
        "generated_from": "sqlite_daily_snapshots",
        "requested_range": {"start_date": start, "end_date": end},
        "effective_range": {"start_date": points[0]["date"] if points else None, "end_date": points[-1]["date"] if points else None},
        "capacity_factors": factors,
        "enabled_cluster_count": cluster_count,
        "points": points,
        "bucket_history_limitation": "Historical expected bucket inventory is not persisted. Bucket values are reported only when observed records have complete metrics and successful collection status; they are not guaranteed to represent every bucket that existed on that date.",
    }


def get_bucket_usage_report_history(start_date: date | None = None, end_date: date | None = None) -> dict:
    start, end = _bounds(start_date, end_date)
    with transaction() as connection:
        rows = connection.execute(
            """SELECT b.snapshot_date, b.cluster_id,
                      COUNT(*) AS observed_buckets,
                      SUM(CASE WHEN b.metrics_available=1 AND b.used_bytes IS NOT NULL
                               THEN 1 ELSE 0 END) AS usage_available,
                      SUM(CASE WHEN b.metrics_available=1 AND b.quota_bytes IS NOT NULL
                               THEN 1 ELSE 0 END) AS quota_available,
                      SUM(CASE WHEN b.metrics_available=1 AND b.used_bytes IS NOT NULL
                               THEN b.used_bytes ELSE NULL END) AS used_bytes,
                      SUM(CASE WHEN b.metrics_available=1 AND b.quota_bytes IS NOT NULL
                               THEN b.quota_bytes ELSE NULL END) AS quota_bytes,
                      MAX(r.status) AS collection_status
               FROM bucket_daily_metrics b
               JOIN clusters c ON c.id=b.cluster_id AND c.enabled=1
               JOIN locations l ON l.id=c.location_id AND l.enabled=1
               LEFT JOIN collection_runs r ON r.cluster_id=b.cluster_id
                    AND r.snapshot_date=b.snapshot_date
               WHERE b.snapshot_date BETWEEN ? AND ?
               GROUP BY b.snapshot_date, b.cluster_id
               ORDER BY b.snapshot_date, b.cluster_id""",
            (start, end),
        ).fetchall()
        cluster_count = _active_cluster_count(connection)
    by_day: dict[str, list] = {}
    for row in rows:
        by_day.setdefault(row["snapshot_date"], []).append(row)
    points = []
    for day in _days(start, end):\n        clusters = by_day.get(day, [])
        usage_complete = bool(clusters) and all(
            r["collection_status"] == "success" and r["usage_available"] == r["observed_buckets"]
            and r["observed_buckets"] > 0 for r in clusters
        )
        quota_complete = bool(clusters) and all(
            r["collection_status"] == "success" and r["quota_available"] == r["observed_buckets"]
            and r["observed_buckets"] > 0 for r in clusters
        )
        used = sum(float(r["used_bytes"] or 0) for r in clusters) if usage_complete else None
        quota = sum(float(r["quota_bytes"] or 0) for r in clusters) if quota_complete else None
        usage_pct = used / quota * 100 if used is not None and quota is not None and quota > 0 else None
        points.append({
            "date": day,
            "coverage": {
                "enabled_clusters": cluster_count,
                "clusters_with_bucket_records": len(clusters),
                "observed_buckets": sum(int(r["observed_buckets"] or 0) for r in clusters),
                "usage_complete_for_observed_records": usage_complete,
                "quota_complete_for_observed_records": quota_complete,
                "collection_success_clusters": sum(r["collection_status"] == "success" for r in clusters),
            },
            "used_bytes": used,
            "quota_bytes": quota,
            "utilization_pct": usage_pct,
        })
    return {
        "report": "bucket_usage",
        "generated_from": "sqlite_daily_snapshots",
        "requested_range": {"start_date": start, "end_date": end},
        "effective_range": {"start_date": points[0]["date"] if points else None, "end_date": points[-1]["date"] if points else None},
        "points": points,
        "coverage_limitation": "Historical expected bucket inventory and per-cluster successful collection coverage are not persisted consistently. Values are withheld unless all observed bucket records have metrics and a successful collection run; totals are not guaranteed to include buckets missing from observed records.",
    }


def get_raw_capacity_report_history(start_date: date | None = None, end_date: date | None = None) -> dict:
    start, end = _bounds(start_date, end_date)
    with transaction() as connection:
        cluster_count = _active_cluster_count(connection)
        rows = connection.execute(
            """SELECT m.snapshot_date, m.cluster_id, m.metrics_available,
                      m.raw_total_bytes, m.raw_free_bytes
               FROM cluster_daily_metrics m
               JOIN clusters c ON c.id=m.cluster_id AND c.enabled=1
               JOIN locations l ON l.id=c.location_id AND l.enabled=1
               WHERE m.snapshot_date BETWEEN ? AND ?
               ORDER BY m.snapshot_date, m.cluster_id""",
            (start, end),
        ).fetchall()
    by_day: dict[str, list] = {}
    for row in rows:
        by_day.setdefault(row["snapshot_date"], []).append(row)
    points = []
    for day in _days(start, end):
        clusters = by_day.get(day, [])
        valid = [r for r in clusters if r["metrics_available"] == 1 and
                 r["raw_total_bytes"] is not None and r["raw_free_bytes"] is not None]
        complete = cluster_count > 0 and len(clusters) == cluster_count and len(valid) == cluster_count
        if complete:
            total = sum(float(r["raw_total_bytes"]) for r in valid)
            free = sum(float(r["raw_free_bytes"]) for r in valid)
            used = total - free
            utilization = used / total * 100 if total > 0 else None
        else:
            total = free = used = utilization = None
        points.append({
            "date": day,
            "complete": complete,
            "coverage": {"enabled_clusters": cluster_count, "snapshots": len(clusters), "metrics_available": len(valid)},
            "raw_total_bytes": total,
            "raw_free_bytes": free,
            "raw_used_bytes": used,
            "raw_used_pct": utilization,
        })
    return {
        "report": "raw_capacity",
        "generated_from": "sqlite_daily_snapshots",
        "requested_range": {"start_date": start, "end_date": end},
        "effective_range": {"start_date": points[0]["date"] if points else None, "end_date": points[-1]["date"] if points else None},
        "enabled_cluster_count": cluster_count,
        "points": points,
    }
