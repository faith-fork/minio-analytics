from __future__ import annotations

from datetime import date, datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

from app.database.database import transaction

IST = ZoneInfo("Asia/Kolkata")
TREND_LOOKBACK_DAYS = 30


def _midnight_ist_date(value: str | None) -> date | None:
    """Accept only snapshots taken exactly at 00:00 IST."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        local = parsed.astimezone(IST)
        if local.hour != 0 or local.minute != 0 or local.second != 0:
            return None
        return local.date()
    except (TypeError, ValueError):
        return None


def _linear_growth_per_day(samples: list[tuple[date, float]]) -> float | None:
    """Ordinary least-squares slope using actual elapsed calendar days."""
    if len(samples) < 2:
        return None
    origin = samples[0][0]
    xs = [(day - origin).days for day, _ in samples]
    ys = [used for _, used in samples]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        return None
    slope = sum(
        (x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)
    ) / denominator
    return slope if isfinite(slope) else None


def get_consolidated_raw_capacity_report() -> dict:
    """Return latest raw-capacity snapshot and 30-day trends per enabled cluster.

    Historical metrics are read from the same daily 00:00 IST SQLite snapshots
    populated by the scheduled collector. The collector already applies the
    0.993 raw-efficiency adjustment to raw_total_bytes; do not apply it again.
    Missing metrics are never treated as zero.
    """
    with transaction() as connection:
        latest_rows = connection.execute(
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
        history_rows = connection.execute(
            """
            SELECT m.cluster_id, m.snapshot_date, m.snapshot_ts,
                   m.metrics_available, m.raw_total_bytes, m.raw_free_bytes
            FROM cluster_daily_metrics m
            JOIN clusters c ON c.id = m.cluster_id AND c.enabled = 1
            JOIN locations l ON l.id = c.location_id AND l.enabled = 1
            ORDER BY m.cluster_id, m.snapshot_date, m.id
            """
        ).fetchall()

    history: dict[str, list[tuple[date, float, float]]] = {}
    for row in history_rows:
        if row["metrics_available"] != 1:
            continue
        if row["raw_total_bytes"] is None or row["raw_free_bytes"] is None:
            continue
        sample_day = _midnight_ist_date(row["snapshot_ts"])
        if sample_day is None:
            continue
        total = float(row["raw_total_bytes"])
        free = float(row["raw_free_bytes"])
        used = max(total - free, 0.0)
        history.setdefault(row["cluster_id"], []).append((sample_day, used, free))

    items = []
    for row in latest_rows:
        item = dict(row)
        available = (
            item["metrics_available"] == 1
            and item["raw_total_bytes"] is not None
            and item["raw_free_bytes"] is not None
        )
        item["metrics_available"] = bool(available)
        item["raw_used_bytes"] = (
            max(float(item["raw_total_bytes"]) - float(item["raw_free_bytes"]), 0.0)
            if available else None
        )
        item["raw_used_pct"] = (
            item["raw_used_bytes"] / item["raw_total_bytes"] * 100
            if available and item["raw_total_bytes"] > 0 else None
        )

        samples = history.get(item["cluster_id"], [])
        latest_day = _midnight_ist_date(item["snapshot_ts"])
        if latest_day is not None:
            window_start = latest_day - timedelta(days=TREND_LOOKBACK_DAYS - 1)
            samples = [sample for sample in samples if window_start <= sample[0] <= latest_day]
        samples.sort(key=lambda sample: sample[0])

        # Change is deliberately a day-over-day comparison, not a comparison
        # with an older sample when yesterday's midnight snapshot is missing.
        change = None
        if latest_day is not None and len(samples) >= 2:
            by_day = {sample[0]: sample for sample in samples}
            previous = by_day.get(latest_day - timedelta(days=1))
            current = by_day.get(latest_day)
            if previous is not None and current is not None:
                change = current[1] - previous[1]

        growth = _linear_growth_per_day([(day, used) for day, used, _ in samples])
        projected = None
        if available and growth is not None and growth > 0:
            projected = int(float(item["raw_free_bytes"]) / growth)

        item["change_vs_yesterday_bytes"] = change
        item["trend_growth_bytes_per_day"] = growth
        item["projected_days_to_full"] = projected
        item["trend_sample_count"] = len(samples)
        item["status"] = "Available" if available else "Unavailable"
        items.append(item)

    cluster_count = len(items)
    complete = cluster_count > 0 and all(item["metrics_available"] for item in items)
    totals = {}
    for field in ("raw_total_bytes", "raw_free_bytes", "raw_used_bytes"):
        totals[field] = sum(item[field] for item in items) if complete else None
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
        "trend_lookback_days": TREND_LOOKBACK_DAYS,
        "totals_bytes": totals,
        "raw_used_pct": raw_used_pct,
        "items": items,
    }
