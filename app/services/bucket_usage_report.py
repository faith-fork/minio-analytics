from __future__ import annotations

from app.database.database import transaction


def get_consolidated_bucket_usage_report() -> dict:
    """Return active-bucket usage from each cluster's latest stored bucket snapshot.

    Metric totals are withheld independently when any active bucket lacks that
    metric. Missing measurements are never treated as zero.
    """
    with transaction() as connection:
        rows = connection.execute(
            """
            WITH active_clusters AS (
                SELECT c.id AS cluster_id, c.name AS cluster_name,
                       l.id AS location_id, l.name AS location_name
                FROM clusters c
                JOIN locations l ON l.id = c.location_id
                WHERE c.enabled = 1 AND l.enabled = 1
            ),
            active_bucket_counts AS (
                SELECT b.cluster_id, COUNT(*) AS active_bucket_count
                FROM buckets b
                JOIN active_clusters ac ON ac.cluster_id = b.cluster_id
                WHERE b.is_active = 1
                GROUP BY b.cluster_id
            ),
            latest_bucket_dates AS (
                SELECT m.cluster_id, MAX(m.snapshot_date) AS snapshot_date
                FROM bucket_daily_metrics m
                JOIN buckets b ON b.id = m.bucket_id AND b.is_active = 1
                JOIN active_clusters ac ON ac.cluster_id = b.cluster_id
                GROUP BY m.cluster_id
            )
            SELECT ac.location_id, ac.location_name,
                   ac.cluster_id, ac.cluster_name,
                   b.id AS bucket_id, b.bucket_name,
                   b.tenant_id AS current_tenant_id,
                   d.snapshot_date AS bucket_snapshot_date,
                   m.snapshot_ts, m.collected_at,
                   m.tenant_id_at_snapshot,
                   st.name AS tenant_name_at_snapshot,
                   m.used_bytes, m.quota_bytes, m.object_count,
                   m.version_count, m.delete_marker_count,
                   m.metrics_available, m.error_text
            FROM active_clusters ac
            JOIN buckets b ON b.cluster_id = ac.cluster_id AND b.is_active = 1
            LEFT JOIN latest_bucket_dates d ON d.cluster_id = ac.cluster_id
            LEFT JOIN bucket_daily_metrics m
                ON m.bucket_id = b.id
               AND m.cluster_id = b.cluster_id
               AND m.snapshot_date = d.snapshot_date
            LEFT JOIN tenants st ON st.id = m.tenant_id_at_snapshot
            ORDER BY ac.location_name, ac.cluster_name,
                     st.name COLLATE NOCASE, b.bucket_name COLLATE NOCASE
            """
        ).fetchall()
        cluster_counts = connection.execute(
            """
            SELECT COUNT(*) AS active_clusters
            FROM clusters c
            JOIN locations l ON l.id = c.location_id
            WHERE c.enabled = 1 AND l.enabled = 1
              AND EXISTS (SELECT 1 FROM buckets b
                          WHERE b.cluster_id = c.id AND b.is_active = 1)
            """
        ).fetchone()["active_clusters"]

    items = [dict(row) for row in rows]
    metric_fields = ("used_bytes", "quota_bytes", "object_count",
                     "version_count", "delete_marker_count")
    totals = {}
    for field in metric_fields:
        values = [item[field] for item in items]
        totals[field] = (
            sum(values)
            if items and all(
                item["metrics_available"] == 1 and item[field] is not None
                for item in items
            )
            else None
        )

    active_bucket_count = len(items)
    buckets_with_metrics = sum(
        item["metrics_available"] == 1 for item in items
    )
    buckets_with_snapshots = sum(item["bucket_snapshot_date"] is not None for item in items)
    latest_cluster_dates = {}
    for item in items:
        latest_cluster_dates[item["cluster_id"]] = (
            item["bucket_snapshot_date"], item["snapshot_ts"]
        )
    all_cluster_dates_available = (
        len(latest_cluster_dates) == cluster_counts
        and all(snapshot_date and snapshot_ts
                for snapshot_date, snapshot_ts in latest_cluster_dates.values())
    )
    data_as_of = (
        min(snapshot_ts for _, snapshot_ts in latest_cluster_dates.values())
        if all_cluster_dates_available and latest_cluster_dates
        else None
    )

    for item in items:
        used = item["used_bytes"]
        quota = item["quota_bytes"]
        item["usage_pct"] = (
            used / quota * 100
            if item["metrics_available"] == 1
            and used is not None and quota is not None and quota > 0
            else None
        )
        if item["bucket_snapshot_date"] is None:
            item["status"] = "No snapshot"
        elif item["metrics_available"] != 1:
            item["status"] = "Unavailable"
        else:
            item["status"] = "Available"

    return {
        "generated_from": "sqlite",
        "data_as_of": data_as_of,
        "active_cluster_count": cluster_counts,
        "active_bucket_count": active_bucket_count,
        "buckets_with_snapshots": buckets_with_snapshots,
        "buckets_with_metrics": buckets_with_metrics,
        "buckets_without_metrics": active_bucket_count - buckets_with_metrics,
        "coverage_pct": (
            buckets_with_metrics / active_bucket_count * 100
            if active_bucket_count else None
        ),
        "totals_bytes": totals,
        "items": items,
    }
