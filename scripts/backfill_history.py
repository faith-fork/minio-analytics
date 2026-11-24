from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.collectors.bucket_collector import collect_bucket_snapshots
from app.collectors.cluster_collector import collect_cluster_snapshot
from app.collectors.topology_collector import collect_topology_snapshot
from app.config.loader import load_locations
from app.database.database import initialize_database, transaction
from app.database.persistence import (
    persist_bucket_snapshots,
    persist_cluster_snapshot,
    persist_topology_snapshot,
    sync_configuration,
)
from app.database.prometheus_config import load_database_locations

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("minio_analytics.backfill")


def _snapshot_timestamp(day: date) -> datetime:
    """Use the same daily snapshot boundary as the production scheduler: 00:00 IST."""
    return datetime.combine(day, time.min, tzinfo=IST).astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _record_run(location, cluster, day, started, finished, status, attempt, counts, errors):
    details = {
        "mode": "historical_backfill",
        "topology_counts": counts.get("topology", {}),
        "errors": errors,
    }
    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO collection_runs (
                run_id, snapshot_date, location_id, cluster_id, started_at, finished_at,
                status, attempt, metrics_collected, error_text, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()), day.isoformat(), location.id, cluster.id,
                _utc_text(started), _utc_text(finished), status, attempt,
                sum(counts.values()) if all(isinstance(v, int) for v in counts.values()) else (
                    counts.get("cluster", 0) + counts.get("buckets", 0)
                    + sum(counts.get("topology", {}).values())
                ),
                "; ".join(errors) if errors else None,
                json.dumps(details, sort_keys=True, separators=(",", ":")),
            ),
        )


def _collect_day(location, cluster, day: date, max_attempts: int, dry_run: bool) -> dict:
    snapshot_ts = _snapshot_timestamp(day)
    started = datetime.now(timezone.utc)
    errors: list[str] = []
    counts = {"cluster": 0, "buckets": 0, "topology": {}}
    cluster_snapshot = None
    bucket_snapshots = None
    topology_snapshot = None
    attempts_used = 0

    for attempt in range(1, max_attempts + 1):
        attempts_used = attempt
        attempt_errors: list[str] = []
        try:
            candidate = collect_cluster_snapshot(location, cluster, snapshot_ts)
            if candidate.metrics_available:
                cluster_snapshot = candidate
            else:
                attempt_errors.append("cluster: " + (candidate.error_text or "unavailable"))
        except Exception as exc:
            attempt_errors.append(f"cluster: {exc}")

        try:
            candidate_buckets = collect_bucket_snapshots(location, cluster, snapshot_ts)
            if candidate_buckets:
                bucket_snapshots = candidate_buckets
            else:
                attempt_errors.append("buckets: no bucket usage samples")
        except Exception as exc:
            attempt_errors.append(f"buckets: {exc}")

        try:
            candidate_topology = collect_topology_snapshot(location, cluster, snapshot_ts)
            topology_snapshot = candidate_topology
            attempt_errors.extend(
                f"topology {family}: {message}"
                for family, message in candidate_topology.family_errors.items()
            )
        except Exception as exc:
            attempt_errors.append(f"topology: {exc}")

        if not attempt_errors:
            errors = []
            break
        errors = attempt_errors
        if attempt < max_attempts:
            logger.warning(
                "%s/%s %s attempt %s/%s: %s",
                location.id, cluster.id, day, attempt, max_attempts, "; ".join(errors)
            )

    cluster_ok = cluster_snapshot is not None
    buckets_ok = bucket_snapshots is not None
    topology_ok = topology_snapshot is not None and not topology_snapshot.family_errors
    successful_families = sum((cluster_ok, buckets_ok, topology_ok))
    status = "success" if successful_families == 3 else ("partial" if successful_families else "failed")

    if not dry_run:
        # The normal persistence functions use date/identity upserts. Re-running
        # a day safely refreshes that day's values without deleting history.
        if cluster_snapshot is not None:
            persist_cluster_snapshot(cluster_snapshot, snapshot_date=day)
            counts["cluster"] = 1
        if bucket_snapshots is not None:
            counts["buckets"] = persist_bucket_snapshots(bucket_snapshots, snapshot_date=day).get("metrics_upserts", 0)
        if topology_snapshot is not None:
            counts["topology"] = persist_topology_snapshot(topology_snapshot, snapshot_date=day)

        _record_run(
            location, cluster, day, started, datetime.now(timezone.utc),
            status, attempts_used, counts, errors,
        )

    return {
        "date": day.isoformat(),
        "location": location.id,
        "cluster": cluster.id,
        "status": status,
        "attempts": attempts_used,
        "cluster_snapshot": cluster_ok,
        "bucket_snapshots": len(bucket_snapshots or []),
        "topology": counts.get("topology", {}),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill historical MinIO capacity, bucket and topology snapshots from Prometheus."
    )
    parser.add_argument(
        "--source", choices=("database", "yaml"), default="database",
        help="Configuration source (default: active SQLite Prometheus connections).",
    )
    parser.add_argument("--config", default=None, help="YAML location configuration (used with --source yaml).")
    parser.add_argument("--days", type=int, default=60, help="Number of IST dates to backfill (1-60; default: 60).")
    parser.add_argument(
        "--end-date", type=date.fromisoformat, default=None,
        help="Inclusive end date YYYY-MM-DD (default: yesterday in IST).",
    )
    parser.add_argument("--max-attempts", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--dry-run", action="store_true", help="Query Prometheus and report results without writing SQLite.")
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO")
    args = parser.parse_args()

    if not 1 <= args.days <= 60:
        parser.error("--days must be between 1 and 60")
    if args.source == "database" and args.config:
        parser.error("--config can only be used with --source yaml")

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.source == "database":
        locations = load_database_locations()
    else:
        locations = load_locations(args.config)

    if not args.dry_run:
        initialize_database()
        if args.source == "yaml":
            sync_configuration(locations)

    end_day = args.end_date or (datetime.now(IST).date() - timedelta(days=1))
    start_day = end_day - timedelta(days=args.days - 1)
    summary = {
        "mode": "dry-run" if args.dry_run else "backfill",
        "source": args.source,
        "start_date": start_day.isoformat(),
        "end_date": end_day.isoformat(),
        "dates_requested": args.days,
        "cluster_days_total": 0,
        "success": 0,
        "partial": 0,
        "failed": 0,
        "results": [],
    }

    for offset in range(args.days):
        day = start_day + timedelta(days=offset)
        logger.info("Backfilling %s (Prometheus instant-query timestamp %s)", day, _snapshot_timestamp(day).isoformat())
        for location in locations:
            for cluster in location.clusters:
                summary["cluster_days_total"] += 1
                result = _collect_day(location, cluster, day, args.max_attempts, args.dry_run)
                summary[result["status"]] += 1
                summary["results"].append(result)
                logger.info(
                    "%s %s/%s: %s (attempts=%s)",
                    day, location.id, cluster.id, result["status"], result["attempts"]
                )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
