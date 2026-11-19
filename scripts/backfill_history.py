from __future__ import annotations

import argparse
import json
import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.collectors.bucket_collector import collect_bucket_snapshots
from app.collectors.cluster_collector import collect_cluster_snapshot
from app.config.loader import load_locations
from app.database.database import initialize_database, transaction
from app.database.persistence import sync_configuration

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("minio_analytics.backfill")


def _snapshot_timestamp(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=IST).astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _collect_with_retry(location, cluster, snapshot_ts, attempts: int):
    cluster_snapshot = None
    bucket_snapshots = None
    errors: list[str] = []

    for attempt in range(1, attempts + 1):
        errors = []
        try:
            candidate = collect_cluster_snapshot(location, cluster, snapshot_ts)
            if candidate.metrics_available:
                cluster_snapshot = candidate
            else:
                errors.append(candidate.error_text or "Cluster metrics unavailable")
        except Exception as exc:
            errors.append(f"Cluster metrics: {exc}")

        try:
            candidate_buckets = collect_bucket_snapshots(location, cluster, snapshot_ts)
            if candidate_buckets:
                bucket_snapshots = candidate_buckets
            else:
                errors.append("No bucket usage metrics returned")
        except Exception as exc:
            errors.append(f"Bucket metrics: {exc}")

        if not errors:
            return cluster_snapshot, bucket_snapshots, attempt, []
        logger.warning(
            "Retryable historical collection issue for %s/%s on %s (attempt %s/%s): %s",
            location.id, cluster.id, snapshot_ts.date(), attempt, attempts, "; ".join(errors)
        )

    return cluster_snapshot, bucket_snapshots, attempts, errors


def _persist_historical(
    location,
    cluster,
    snapshot_ts: datetime,
    cluster_snapshot,
    bucket_snapshots,
    status: str,
    attempts: int,
    errors: list[str],
) -> None:
    day = snapshot_ts.astimezone(IST).date().isoformat()
    started = datetime.now(timezone.utc)
    metrics_count = 0

    with transaction() as connection:
        if cluster_snapshot is not None:
            connection.execute(
                """
                INSERT OR IGNORE INTO cluster_daily_metrics (
                    snapshot_date, cluster_id, snapshot_ts, collected_at,
                    raw_total_bytes, raw_free_bytes, usable_total_bytes, usable_free_bytes,
                    nodes_online, nodes_offline, growth_bytes_per_day, days_to_full,
                    metrics_available, error_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL)
                """,
                (
                    day, cluster_snapshot.cluster_id, _utc_text(snapshot_ts),
                    _utc_text(cluster_snapshot.collected_at),
                    cluster_snapshot.raw_total_bytes, cluster_snapshot.raw_free_bytes,
                    cluster_snapshot.usable_total_bytes, cluster_snapshot.usable_free_bytes,
                    cluster_snapshot.nodes_online, cluster_snapshot.nodes_offline,
                    cluster_snapshot.growth_bytes_per_day, cluster_snapshot.days_to_full,
                ),
            )
            metrics_count += 1

        for item in bucket_snapshots or []:
            ts_text = _utc_text(snapshot_ts)
            connection.execute(
                """
                INSERT INTO buckets (
                    cluster_id, bucket_name, first_seen_at, last_seen_at, is_active
                ) VALUES (?, ?, ?, ?, 0)
                ON CONFLICT(cluster_id, bucket_name) DO UPDATE SET
                    first_seen_at = MIN(buckets.first_seen_at, excluded.first_seen_at),
                    last_seen_at = MAX(buckets.last_seen_at, excluded.last_seen_at),
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                """,
                (item.cluster_id, item.bucket_name, ts_text, ts_text),
            )
            bucket = connection.execute(
                "SELECT id FROM buckets WHERE cluster_id = ? AND bucket_name = ?",
                (item.cluster_id, item.bucket_name),
            ).fetchone()
            if bucket is None:
                raise RuntimeError(f"Unable to resolve bucket {item.cluster_id}/{item.bucket_name}")

            # Historical tenant ownership is deliberately NULL unless it can be
            # reconstructed from a complete, trusted mapping audit trail.
            connection.execute(
                """
                INSERT OR IGNORE INTO bucket_daily_metrics (
                    snapshot_date, bucket_id, cluster_id, bucket_name,
                    tenant_id_at_snapshot, snapshot_ts, collected_at,
                    used_bytes, quota_bytes, object_count, version_count, delete_marker_count,
                    object_size_distribution_json, version_count_distribution_json,
                    metrics_available, error_text
                ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, 1, NULL)
                """,
                (
                    day, bucket["id"], item.cluster_id, item.bucket_name,
                    ts_text, _utc_text(item.collected_at), item.used_bytes,
                    item.quota_bytes, item.object_count,
                    json.dumps(item.object_size_distribution or {}, sort_keys=True, separators=(",", ":")),
                    json.dumps(item.version_count_distribution or {}, sort_keys=True, separators=(",", ":")),
                ),
            )
            metrics_count += 1

        finished = datetime.now(timezone.utc)
        details = {
            "mode": "historical_backfill",
            "bucket_count": len(bucket_snapshots or []),
            "cluster_metrics_available": cluster_snapshot is not None,
            "bucket_metrics_available": bucket_snapshots is not None,
            "errors": errors,
        }
        connection.execute(
            """
            INSERT INTO collection_runs (
                run_id, snapshot_date, location_id, cluster_id, started_at, finished_at,
                status, attempt, metrics_collected, error_text, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()), day, location.id, cluster.id, _utc_text(started),
                _utc_text(finished), status, attempts, metrics_count,
                "; ".join(errors) if errors else None,
                json.dumps(details, sort_keys=True, separators=(",", ":")),
            ),
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill historical MinIO analytics snapshots from Prometheus."
    )
    parser.add_argument("--config", default=None, help="Location YAML path.")
    parser.add_argument("--days", type=int, default=60, help="Number of IST dates to import (default: 60).")
    parser.add_argument(
        "--end-date", type=date.fromisoformat, default=None,
        help="Inclusive end date in YYYY-MM-DD (default: yesterday in IST).",
    )
    parser.add_argument("--max-attempts", type=int, choices=(1, 2), default=2)
    parser.add_argument("--dry-run", action="store_true", help="Query Prometheus and report results without writing to SQLite.")
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO")
    args = parser.parse_args()

    if not 1 <= args.days <= 90:
        parser.error("--days must be between 1 and 90")

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    locations = load_locations(args.config)
    end_day = args.end_date or (datetime.now(IST).date() - timedelta(days=1))
    start_day = end_day - timedelta(days=args.days - 1)
    days = [start_day + timedelta(days=offset) for offset in range(args.days)]

    if not args.dry_run:
        initialize_database()
        sync_configuration(locations)

    summary = {
        "mode": "dry-run" if args.dry_run else "backfill",
        "start_date": start_day.isoformat(),
        "end_date": end_day.isoformat(),
        "dates_requested": len(days),
        "clusters_total": 0,
        "clusters_success": 0,
        "clusters_partial": 0,
        "clusters_failed": 0,
        "bucket_snapshots_seen": 0,
        "errors": [],
    }

    for day in days:
        snapshot_ts = _snapshot_timestamp(day)
        logger.info("Backfilling IST date %s (Prometheus timestamp %s)", day, snapshot_ts.isoformat())
        for location in locations:
            for cluster in location.clusters:
                summary["clusters_total"] += 1
                cluster_snapshot, bucket_snapshots, attempts, errors = _collect_with_retry(
                    location, cluster, snapshot_ts, args.max_attempts
                )
                cluster_ok = cluster_snapshot is not None
                buckets_ok = bucket_snapshots is not None
                status = "success" if cluster_ok and buckets_ok else (
                    "partial" if cluster_ok or buckets_ok else "failed"
                )
                summary[f"clusters_{status}"] += 1
                bucket_count = len(bucket_snapshots or [])
                summary["bucket_snapshots_seen"] += bucket_count

                if not args.dry_run:
                    _persist_historical(
                        location, cluster, snapshot_ts, cluster_snapshot,
                        bucket_snapshots, status, attempts, errors,
                    )

                result = {
                    "date": day.isoformat(),
                    "location": location.id,
                    "cluster": cluster.id,
                    "status": status,
                    "attempts": attempts,
                    "buckets": bucket_count,
                    "errors": errors,
                }
                if errors:
                    summary["errors"].append(result)
                logger.info(
                    "%s %s/%s: status=%s buckets=%s attempts=%s",
                    day, location.id, cluster.id, status, bucket_count, attempts
                )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["clusters_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
