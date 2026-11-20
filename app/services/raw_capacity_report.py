from __future__ import annotations

from app.database.database import transaction


def get_consolidated_raw_capacity_report() -> dict:
    """Return latest raw-capacity snapshot for every enabled cluster.

    Fleet totals are returned only when every enabled cluster has a valid
    raw-capacity and raw-free measurement. Missing metrics are never treated
    as zero. Per-cluster used capacity is raw total minus raw free.
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
            ranked AS (
                SELECT m.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY m.cluster_id
                           ORDER BY m.snapshot_date DESC, m.id DESC
                       ) AS rn
                FROM cluster_daily_metrics m
            )
            SELECT ac.cluster_id, ac.cluster_name,
                   ac.location_id, ac.location_name,
                   m.snapshot_date, m.snapshot_ts, m.collected_at,
                   m.metrics_available, m.raw_total_bytes, m.raw_free_bytes,
                   m.nodes_online, m.nodes_offline, m.error_text
            FROM active_clusters ac
            LEFT JOIN ranked m
              ON m.cluster_id = ac.cluster_id AND m.rn = 1
            ORDER BY ac.location_name, ac.cluster_name
            """
        ).fetchall()

    items = []
    for row in rows:
        item = dict(row)
        available = (
            item["metrics_available"] == 1
            and item["raw_total_bytes"] is not None
            and item["raw_free_bytes"] is not None
        )
        item["metrics_available"] = bool(available)
        item["raw_used_bytes"] = (
            item["raw_total_bytes"] - item["raw_free_bytes"]
            if available else None
        )
        item["raw_used_pct"] = (
            item["raw_used_bytes"] / item["raw_total_bytes"] * 100
            if available and item["raw_total_bytes"] > 0 else None
        )
        item["status"] = "Available" if available else "Unavailable"
        items.append(item)

    cluster_count = len(items)
    complete = cluster_count > 0 and all(item["metrics_available"] for item in items)
    totals = {}
    for field in ("raw_total_bytes", "raw_free_bytes", "raw_used_bytes"):
        totals[field] = (
            sum(item[field] for item in items)
            if complete else None
        )
    raw_used_pct = (
        totals["raw_used_bytes"] / totals["raw_total_bytes"] * 100
        if complete and totals["raw_total_bytes"] > 0 else None
    )
    timestamps = [item["snapshot_ts"] for item in items]
    data_as_of = min(timestamps) if timestamps and all(timestamps) else None

    return {
        "generated_from": "sqlite",
        "cluster_count": cluster_count,
        "available_cluster_count": sum(item["metrics_available"] for item in items),
        "unavailable_cluster_count": sum(not item["metrics_available"] for item in items),
        "complete_coverage": complete,
        "data_as_of": data_as_of,
        "totals_bytes": totals,
        "raw_used_pct": raw_used_pct,
        "items": items,
    }
