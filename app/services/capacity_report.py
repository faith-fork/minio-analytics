from __future__ import annotations

from app.database.database import transaction


def get_consolidated_capacity_report() -> dict:
    """Return latest per-cluster capacity with strict metric coverage.

    Cluster capacity uses each cluster's latest cluster snapshot. Bucket
    provisioned/used values use the latest bucket snapshot date for that
    cluster and require complete coverage of its currently active buckets.
    Missing or partial measurements are returned as None, never as zero.
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
            ranked_cluster_metrics AS (
                SELECT m.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY m.cluster_id
                           ORDER BY m.snapshot_date DESC, m.id DESC
                       ) AS rn
                FROM cluster_daily_metrics m
            ),
            latest_bucket_dates AS (
                SELECT m.cluster_id, MAX(m.snapshot_date) AS snapshot_date
                FROM bucket_daily_metrics m
                JOIN buckets b ON b.id = m.bucket_id
                WHERE b.is_active = 1
                GROUP BY m.cluster_id
            ),
            bucket_coverage AS (
                SELECT b.cluster_id,
                       COUNT(*) AS active_bucket_count,
                       COUNT(m.bucket_id) AS buckets_with_metrics,
                       SUM(CASE WHEN m.metrics_available = 1
                                     AND m.quota_bytes IS NOT NULL
                                THEN 1 ELSE 0 END) AS buckets_with_quota,
                       SUM(CASE WHEN m.metrics_available = 1
                                     AND m.used_bytes IS NOT NULL
                                THEN 1 ELSE 0 END) AS buckets_with_usage,
                       CASE
                           WHEN COUNT(m.bucket_id) = COUNT(*)
                                AND SUM(CASE WHEN m.metrics_available = 1
                                                  AND m.quota_bytes IS NOT NULL
                                             THEN 1 ELSE 0 END) = COUNT(*)
                           THEN SUM(m.quota_bytes)
                           ELSE NULL
                       END AS provisioned_bytes,
                       CASE
                           WHEN COUNT(m.bucket_id) = COUNT(*)
                                AND SUM(CASE WHEN m.metrics_available = 1
                                                  AND m.used_bytes IS NOT NULL
                                             THEN 1 ELSE 0 END) = COUNT(*)
                           THEN SUM(m.used_bytes)
                           ELSE NULL
                       END AS used_bucket_bytes
                FROM buckets b
                JOIN latest_bucket_dates d ON d.cluster_id = b.cluster_id
                LEFT JOIN bucket_daily_metrics m
                    ON m.bucket_id = b.id
                   AND m.cluster_id = b.cluster_id
                   AND m.snapshot_date = d.snapshot_date
                WHERE b.is_active = 1
                GROUP BY b.cluster_id
            )
            SELECT ac.cluster_id, ac.cluster_name,
                   ac.location_id, ac.location_name,
                   cm.snapshot_date AS cluster_snapshot_date,
                   cm.metrics_available AS cluster_metrics_available,
                   CASE WHEN cm.metrics_available = 1
                        THEN cm.raw_total_bytes ELSE NULL END AS installed_capacity_bytes,
                   CASE WHEN cm.metrics_available = 1
                        THEN cm.usable_total_bytes ELSE NULL END AS cap_capacity_bytes,
                   CASE WHEN cm.metrics_available = 1
                                  AND cm.usable_total_bytes IS NOT NULL
                                  AND cm.usable_free_bytes IS NOT NULL
                        THEN cm.usable_total_bytes - cm.usable_free_bytes
                        ELSE NULL END AS used_cap_bytes,
                   CASE WHEN cm.metrics_available = 1
                        THEN cm.usable_free_bytes ELSE NULL END AS free_capacity_bytes,
                   d.snapshot_date AS bucket_snapshot_date,
                   COALESCE(bc.active_bucket_count, (
                       SELECT COUNT(*) FROM buckets b
                       WHERE b.cluster_id = ac.cluster_id AND b.is_active = 1
                   )) AS active_bucket_count,
                   COALESCE(bc.buckets_with_metrics, 0) AS buckets_with_metrics,
                   COALESCE(bc.buckets_with_quota, 0) AS buckets_with_quota,
                   COALESCE(bc.buckets_with_usage, 0) AS buckets_with_usage,
                   CASE WHEN COALESCE(bc.active_bucket_count, 0) = 0
                        THEN 0 ELSE bc.provisioned_bytes END AS provisioned_bytes,
                   CASE WHEN COALESCE(bc.active_bucket_count, 0) = 0
                        THEN 0 ELSE bc.used_bucket_bytes END AS used_bucket_bytes
            FROM active_clusters ac
            LEFT JOIN ranked_cluster_metrics cm
                ON cm.cluster_id = ac.cluster_id AND cm.rn = 1
            LEFT JOIN latest_bucket_dates d ON d.cluster_id = ac.cluster_id
            LEFT JOIN bucket_coverage bc ON bc.cluster_id = ac.cluster_id
            ORDER BY ac.location_name, ac.cluster_name
            """
        ).fetchall()

    items = [dict(row) for row in rows]
    metric_fields = (
        "installed_capacity_bytes",
        "cap_capacity_bytes",
        "used_cap_bytes",
        "provisioned_bytes",
        "used_bucket_bytes",
        "free_capacity_bytes",
    )
    cluster_count = len(items)
    totals = {}
    for field in metric_fields:
        values = [item[field] for item in items]
        totals[field] = (
            sum(values)
            if cluster_count > 0 and all(value is not None for value in values)
            else None
        )

    return {
        "generated_from": "sqlite",
        "cluster_count": cluster_count,
        "totals_bytes": totals,
        "items": items,
    }
