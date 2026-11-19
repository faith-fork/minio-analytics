from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any

from app.collectors.bucket_collector import collect_bucket_snapshots
from app.collectors.cluster_collector import collect_cluster_snapshot
from app.config.loader import LocationConfig
from app.database.database import initialize_database, transaction
from app.database.persistence import (
    _snapshot_date,
    persist_bucket_snapshots,
    persist_cluster_snapshot,
    sync_configuration,
)

logger = logging.getLogger(__name__)


def _record_run(
    *,
    run_id: str,
    snapshot_date: str,
    location_id: str,
    cluster_id: str,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    attempt: int,
    metrics_collected: int,
    error_text: str | None,
    details: dict[str, Any],
) -> None:
    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO collection_runs (
                run_id, snapshot_date, location_id, cluster_id,
                started_at, finished_at, status, attempt,
                metrics_collected, error_text, details_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                snapshot_date,
                location_id,
                cluster_id,
                started_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                finished_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                status,
                attempt,
                metrics_collected,
                error_text,
                json.dumps(details, sort_keys=True, separators=(",", ":")),
            ),
        )


def collect_location(
    location: LocationConfig,
    snapshot_ts: datetime,
    max_attempts: int = 2,
) -> list[dict[str, Any]]:
    """Collect and persist all clusters for one location.

    Each cluster gets at most one retry by default. A failed metric family does
    not prevent a successful family from being persisted. Failed Prometheus
    values remain unavailable/NULL; collection_runs records the partial result.
    """
    if snapshot_ts.tzinfo is None or snapshot_ts.utcoffset() is None:
        raise ValueError("snapshot_ts must be timezone-aware")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    initialize_database()
    sync_configuration([location])
    day = _snapshot_date(snapshot_ts)
    results: list[dict[str, Any]] = []

    for cluster in location.clusters:
        run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)
        cluster_snapshot = None
        last_cluster_snapshot = None
        bucket_snapshots = None
        errors: list[str] = []
        attempts_used = 0

        for attempt in range(1, max_attempts + 1):
            attempts_used = attempt
            attempt_errors: list[str] = []
            logger.info(
                "Collecting location=%s cluster=%s attempt=%s/%s snapshot=%s",
                location.id, cluster.id, attempt, max_attempts, snapshot_ts.isoformat()
            )

            try:
                candidate_cluster = collect_cluster_snapshot(
                    location=location,
                    cluster=cluster,
                    snapshot_ts=snapshot_ts,
                )
                last_cluster_snapshot = candidate_cluster
                if not candidate_cluster.metrics_available:
                    attempt_errors.append(
                        "cluster metrics: " + (candidate_cluster.error_text or "unavailable")
                    )
                else:
                    cluster_snapshot = candidate_cluster
            except Exception as exc:
                attempt_errors.append(f"cluster metrics: {exc}")

            try:
                candidate_buckets = collect_bucket_snapshots(
                    location=location,
                    cluster=cluster,
                    snapshot_ts=snapshot_ts,
                )
                if not candidate_buckets:
                    attempt_errors.append("bucket metrics: no buckets returned")
                else:
                    bucket_snapshots = candidate_buckets
            except Exception as exc:
                attempt_errors.append(f"bucket metrics: {exc}")

            if not attempt_errors:
                errors = []
                break

            errors = attempt_errors
            logger.warning(
                "Collection attempt failed location=%s cluster=%s: %s",
                location.id, cluster.id, "; ".join(attempt_errors)
            )

        # Persist each successful metric family, even if its sibling failed.
        snapshot_to_persist = cluster_snapshot or last_cluster_snapshot
        if snapshot_to_persist is not None:
            persist_cluster_snapshot(snapshot_to_persist, snapshot_date=day)

        if bucket_snapshots is not None:
            persist_bucket_snapshots(bucket_snapshots, snapshot_date=day)

        cluster_ok = cluster_snapshot is not None
        buckets_ok = bucket_snapshots is not None
        status = "success" if cluster_ok and buckets_ok else (
            "partial" if cluster_ok or buckets_ok else "failed"
        )
        metrics_collected = (1 if cluster_ok else 0) + (
            len(bucket_snapshots) if buckets_ok else 0
        )
        error_text = "; ".join(errors) if errors else None
        details = {
            "bucket_count": len(bucket_snapshots) if buckets_ok else None,
            "cluster_metrics_available": cluster_ok,
            "bucket_metrics_available": buckets_ok,
            "errors": errors,
        }
        finished_at = datetime.now(timezone.utc)
        _record_run(
            run_id=run_id,
            snapshot_date=day,
            location_id=location.id,
            cluster_id=cluster.id,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            attempt=attempts_used,
            metrics_collected=metrics_collected,
            error_text=error_text,
            details=details,
        )
        results.append(
            {
                "location_id": location.id,
                "cluster_id": cluster.id,
                "snapshot_date": day,
                "status": status,
                "attempts": attempts_used,
                "metrics_collected": metrics_collected,
                "errors": errors,
            }
        )

    return results


def collect_all(
    locations: list[LocationConfig],
    snapshot_ts: datetime | None = None,
    max_attempts: int = 2,
) -> list[dict[str, Any]]:
    """Synchronize configuration and collect all configured locations."""
    target = snapshot_ts or datetime.now(timezone.utc)
    if target.tzinfo is None or target.utcoffset() is None:
        raise ValueError("snapshot_ts must be timezone-aware")
    initialize_database()
    sync_configuration(locations)

    results: list[dict[str, Any]] = []
    for location in locations:
        results.extend(
            collect_location(
                location=location,
                snapshot_ts=target,
                max_attempts=max_attempts,
            )
        )
    return results
