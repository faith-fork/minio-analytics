from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Iterable
from zoneinfo import ZoneInfo

from app.config.loader import LocationConfig
from app.database.database import initialize_database, transaction

IST = ZoneInfo("Asia/Kolkata")


def _timestamp(value: datetime) -> str:
    """Serialize an aware timestamp in UTC using an explicit Z suffix."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Snapshot timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _snapshot_date(snapshot_ts: datetime) -> str:
    """Use the business-local calendar date (midnight IST snapshots)."""
    if snapshot_ts.tzinfo is None or snapshot_ts.utcoffset() is None:
        raise ValueError("Snapshot timestamps must be timezone-aware")
    return snapshot_ts.astimezone(IST).date().isoformat()


def sync_configuration(locations: Iterable[LocationConfig]) -> dict[str, int]:
    """Upsert configured locations and clusters without deleting historical rows."""
    initialize_database()
    location_count = 0
    cluster_count = 0

    with transaction() as connection:
        for location in locations:
            connection.execute(
                """
                INSERT INTO locations (id, name, enabled)
                VALUES (?, ?, 1)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    enabled = 1,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                """,
                (location.id, location.name),
            )
            location_count += 1

            for cluster in location.clusters:
                labels_json = json.dumps(
                    {"prometheus_label_value": cluster.prometheus_label_value},
                    sort_keys=True,
                    separators=(",", ":"),
                )
                connection.execute(
                    """
                    INSERT INTO clusters (id, location_id, name, enabled, labels_json)
                    VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        location_id = excluded.location_id,
                        name = excluded.name,
                        enabled = 1,
                        labels_json = excluded.labels_json,
                        updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    """,
                    (cluster.id, location.id, cluster.name, labels_json),
                )
                cluster_count += 1

    return {"locations_synced": location_count, "clusters_synced": cluster_count}


def persist_bucket_snapshots(
    snapshots: Iterable[object],
    snapshot_date: str | date | None = None,
) -> dict[str, int]:
    """Persist bucket inventory and daily metrics in one idempotent transaction.

    The bucket's current tenant assignment is copied into tenant_id_at_snapshot
    only when that day's metric row is first inserted. Replaying a collection
    cannot rewrite historical tenant attribution after a later reassignment.
    Missing buckets are deliberately not marked inactive or deleted.
    """
    initialize_database()
    items = list(snapshots)
    if not items:
        return {"buckets_seen": 0, "inventory_upserts": 0, "metrics_upserts": 0}

    rows = []
    for item in items:
        snapshot_ts = item.snapshot_ts
        collected_at = item.collected_at
        snapshot_ts_text = _timestamp(snapshot_ts)
        collected_at_text = _timestamp(collected_at)

        if snapshot_date is None:
            day = _snapshot_date(snapshot_ts)
        elif isinstance(snapshot_date, date):
            day = snapshot_date.isoformat()
        else:
            day = date.fromisoformat(snapshot_date).isoformat()

        rows.append(
            {
                "cluster_id": item.cluster_id,
                "bucket_name": item.bucket_name,
                "snapshot_ts": snapshot_ts_text,
                "collected_at": collected_at_text,
                "snapshot_date": day,
                "used_bytes": item.used_bytes,
                "quota_bytes": item.quota_bytes,
                "object_count": item.object_count,
                "metrics_available": int(bool(item.metrics_available)),
                "error_text": item.error_text,
                "object_size_distribution_json": json.dumps(
                    item.object_size_distribution or {},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "version_count_distribution_json": json.dumps(
                    item.version_count_distribution or {},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        )

    days = {row["snapshot_date"] for row in rows}
    if len(days) != 1:
        raise ValueError(
            "A single persistence call must contain snapshots for one business date"
        )

    inventory_upserts = 0
    metrics_upserts = 0
    with transaction() as connection:
        for row in rows:
            connection.execute(
                """
                INSERT INTO buckets (
                    cluster_id, bucket_name, first_seen_at, last_seen_at, is_active
                )
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(cluster_id, bucket_name) DO UPDATE SET
                    last_seen_at = excluded.last_seen_at,
                    is_active = 1,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                """,
                (
                    row["cluster_id"],
                    row["bucket_name"],
                    row["snapshot_ts"],
                    row["snapshot_ts"],
                ),
            )
            inventory_upserts += 1

            bucket = connection.execute(
                """
                SELECT id, tenant_id
                FROM buckets
                WHERE cluster_id = ? AND bucket_name = ?
                """,
                (row["cluster_id"], row["bucket_name"]),
            ).fetchone()
            if bucket is None:
                raise RuntimeError(
                    f"Bucket inventory upsert failed for {row['cluster_id']}/"
                    f"{row['bucket_name']}"
                )

            connection.execute(
                """
                INSERT INTO bucket_daily_metrics (
                    snapshot_date, bucket_id, cluster_id, bucket_name,
                    tenant_id_at_snapshot, snapshot_ts, collected_at,
                    used_bytes, quota_bytes, object_count,
                    version_count, delete_marker_count,
                    object_size_distribution_json,
                    version_count_distribution_json,
                    metrics_available, error_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?)
                ON CONFLICT(snapshot_date, bucket_id) DO UPDATE SET
                    snapshot_ts = excluded.snapshot_ts,
                    collected_at = excluded.collected_at,
                    used_bytes = excluded.used_bytes,
                    quota_bytes = excluded.quota_bytes,
                    object_count = excluded.object_count,
                    object_size_distribution_json =
                        excluded.object_size_distribution_json,
                    version_count_distribution_json =
                        excluded.version_count_distribution_json,
                    metrics_available = excluded.metrics_available,
                    error_text = excluded.error_text
                """,
                (
                    row["snapshot_date"],
                    bucket["id"],
                    row["cluster_id"],
                    row["bucket_name"],
                    bucket["tenant_id"],
                    row["snapshot_ts"],
                    row["collected_at"],
                    row["used_bytes"],
                    row["quota_bytes"],
                    row["object_count"],
                    row["object_size_distribution_json"],
                    row["version_count_distribution_json"],
                    row["metrics_available"],
                    row["error_text"],
                ),
            )
            metrics_upserts += 1

    return {
        "buckets_seen": len(rows),
        "inventory_upserts": inventory_upserts,
        "metrics_upserts": metrics_upserts,
    }


def persist_cluster_snapshot(
    snapshot: object,
    snapshot_date: str | date | None = None,
) -> dict[str, int | str]:
    """Persist one cluster's daily capacity snapshot idempotently.

    Failed collections are stored with NULL metric values and an explicit
    availability flag/error; they are never represented as zero capacity.
    """
    initialize_database()

    if snapshot_date is None:
        day = _snapshot_date(snapshot.snapshot_ts)
    elif isinstance(snapshot_date, date):
        day = snapshot_date.isoformat()
    else:
        day = date.fromisoformat(snapshot_date).isoformat()

    values = {
        "snapshot_date": day,
        "cluster_id": snapshot.cluster_id,
        "snapshot_ts": _timestamp(snapshot.snapshot_ts),
        "collected_at": _timestamp(snapshot.collected_at),
        "raw_total_bytes": snapshot.raw_total_bytes,
        "raw_free_bytes": snapshot.raw_free_bytes,
        "usable_total_bytes": snapshot.usable_total_bytes,
        "usable_free_bytes": snapshot.usable_free_bytes,
        "nodes_online": snapshot.nodes_online,
        "nodes_offline": snapshot.nodes_offline,
        "growth_bytes_per_day": snapshot.growth_bytes_per_day,
        "days_to_full": snapshot.days_to_full,
        "metrics_available": int(bool(snapshot.metrics_available)),
        "error_text": snapshot.error_text,
    }

    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO cluster_daily_metrics (
                snapshot_date, cluster_id, snapshot_ts, collected_at,
                raw_total_bytes, raw_free_bytes,
                usable_total_bytes, usable_free_bytes,
                nodes_online, nodes_offline,
                growth_bytes_per_day, days_to_full,
                metrics_available, error_text
            )
            VALUES (
                :snapshot_date, :cluster_id, :snapshot_ts, :collected_at,
                :raw_total_bytes, :raw_free_bytes,
                :usable_total_bytes, :usable_free_bytes,
                :nodes_online, :nodes_offline,
                :growth_bytes_per_day, :days_to_full,
                :metrics_available, :error_text
            )
            ON CONFLICT(snapshot_date, cluster_id) DO UPDATE SET
                snapshot_ts = excluded.snapshot_ts,
                collected_at = excluded.collected_at,
                raw_total_bytes = excluded.raw_total_bytes,
                raw_free_bytes = excluded.raw_free_bytes,
                usable_total_bytes = excluded.usable_total_bytes,
                usable_free_bytes = excluded.usable_free_bytes,
                nodes_online = excluded.nodes_online,
                nodes_offline = excluded.nodes_offline,
                growth_bytes_per_day = excluded.growth_bytes_per_day,
                days_to_full = excluded.days_to_full,
                metrics_available = excluded.metrics_available,
                error_text = excluded.error_text
            """,
            values,
        )

    return {
        "cluster_id": snapshot.cluster_id,
        "snapshot_date": day,
        "metrics_upserts": 1,
        "metrics_available": values["metrics_available"],
    }


def persist_topology_snapshot(
    snapshot: object,
    snapshot_date: str | date | None = None,
) -> dict[str, int]:
    """Persist node, drive, pool and erasure-set telemetry idempotently."""
    initialize_database()
    if snapshot_date is None:
        day = _snapshot_date(snapshot.snapshot_ts)
    elif isinstance(snapshot_date, date):
        day = snapshot_date.isoformat()
    else:
        day = date.fromisoformat(snapshot_date).isoformat()

    snapshot_ts = _timestamp(snapshot.snapshot_ts)
    collected_at = _timestamp(snapshot.collected_at)
    cluster_id = snapshot.cluster_id

    with transaction() as connection:
        for row in snapshot.nodes:
            connection.execute(
                """
                INSERT INTO node_daily_metrics (
                    snapshot_date, cluster_id, node_name, node_exporter_instance,
                    minio_instance, node_exporter_up, minio_scrape_up,
                    cpu_utilization_pct, memory_total_bytes, memory_available_bytes,
                    memory_used_bytes, load1, drives_online, drives_offline, snapshot_ts, collected_at
                ) VALUES (
                    :snapshot_date, :cluster_id, :node_name, :node_exporter_instance,
                    :minio_instance, :node_exporter_up, :minio_scrape_up,
                    :cpu_utilization_pct, :memory_total_bytes, :memory_available_bytes,
                    :memory_used_bytes, :load1, :drives_online, :drives_offline, :snapshot_ts, :collected_at
                )
                ON CONFLICT(snapshot_date, cluster_id, node_name) DO UPDATE SET
                    node_exporter_instance=excluded.node_exporter_instance,
                    minio_instance=excluded.minio_instance,
                    node_exporter_up=excluded.node_exporter_up,
                    minio_scrape_up=excluded.minio_scrape_up,
                    cpu_utilization_pct=excluded.cpu_utilization_pct,
                    memory_total_bytes=excluded.memory_total_bytes,
                    memory_available_bytes=excluded.memory_available_bytes,
                    memory_used_bytes=excluded.memory_used_bytes,
                    load1=excluded.load1,
                    drives_online=excluded.drives_online,
                    drives_offline=excluded.drives_offline,
                    snapshot_ts=excluded.snapshot_ts,
                    collected_at=excluded.collected_at
                """,
                {"snapshot_date": day, "cluster_id": cluster_id,
                 "snapshot_ts": snapshot_ts, "collected_at": collected_at, **row},
            )

        for row in snapshot.drives:
            connection.execute(
                """
                INSERT INTO drive_daily_metrics (
                    snapshot_date, cluster_id, node_name, server, drive_path, mountpoint,
                    total_bytes, used_bytes, free_bytes, availability_errors, io_errors,
                    timeout_errors, filesystem_total_bytes, filesystem_available_bytes,
                    filesystem_free_bytes, filesystem_readonly, filesystem_used_bytes,
                    filesystem_used_pct, snapshot_ts, collected_at
                ) VALUES (
                    :snapshot_date, :cluster_id, :node_name, :server, :drive_path, :mountpoint,
                    :total_bytes, :used_bytes, :free_bytes, :availability_errors, :io_errors,
                    :timeout_errors, :filesystem_total_bytes, :filesystem_available_bytes,
                    :filesystem_free_bytes, :filesystem_readonly, :filesystem_used_bytes,
                    :filesystem_used_pct, :snapshot_ts, :collected_at
                )
                ON CONFLICT(snapshot_date, cluster_id, server, drive_path) DO UPDATE SET
                    node_name=excluded.node_name, mountpoint=excluded.mountpoint,
                    total_bytes=excluded.total_bytes, used_bytes=excluded.used_bytes,
                    free_bytes=excluded.free_bytes,
                    availability_errors=excluded.availability_errors,
                    io_errors=excluded.io_errors, timeout_errors=excluded.timeout_errors,
                    filesystem_total_bytes=excluded.filesystem_total_bytes,
                    filesystem_available_bytes=excluded.filesystem_available_bytes,
                    filesystem_free_bytes=excluded.filesystem_free_bytes,
                    filesystem_readonly=excluded.filesystem_readonly,
                    filesystem_used_bytes=excluded.filesystem_used_bytes,
                    filesystem_used_pct=excluded.filesystem_used_pct,
                    snapshot_ts=excluded.snapshot_ts, collected_at=excluded.collected_at
                """,
                {"snapshot_date": day, "cluster_id": cluster_id,
                 "snapshot_ts": snapshot_ts, "collected_at": collected_at, **row},
            )

        for row in snapshot.pools:
            connection.execute(
                """
                INSERT INTO pool_daily_metrics (
                    snapshot_date, cluster_id, pool_id, erasure_set_count,
                    online_drives, healing_drives, snapshot_ts, collected_at
                ) VALUES (
                    :snapshot_date, :cluster_id, :pool_id, :erasure_set_count,
                    :online_drives, :healing_drives, :snapshot_ts, :collected_at
                )
                ON CONFLICT(snapshot_date, cluster_id, pool_id) DO UPDATE SET
                    erasure_set_count=excluded.erasure_set_count,
                    online_drives=excluded.online_drives,
                    healing_drives=excluded.healing_drives,
                    snapshot_ts=excluded.snapshot_ts, collected_at=excluded.collected_at
                """,
                {"snapshot_date": day, "cluster_id": cluster_id,
                 "snapshot_ts": snapshot_ts, "collected_at": collected_at, **row},
            )

        for row in snapshot.erasure_sets:
            connection.execute(
                """
                INSERT INTO erasure_set_daily_metrics (
                    snapshot_date, cluster_id, pool_id, set_id, status_value,
                    online_drives, healing_drives, read_quorum, write_quorum,
                    snapshot_ts, collected_at
                ) VALUES (
                    :snapshot_date, :cluster_id, :pool_id, :set_id, :status_value,
                    :online_drives, :healing_drives, :read_quorum, :write_quorum,
                    :snapshot_ts, :collected_at
                )
                ON CONFLICT(snapshot_date, cluster_id, pool_id, set_id) DO UPDATE SET
                    status_value=excluded.status_value,
                    online_drives=excluded.online_drives,
                    healing_drives=excluded.healing_drives,
                    read_quorum=excluded.read_quorum,
                    write_quorum=excluded.write_quorum,
                    snapshot_ts=excluded.snapshot_ts, collected_at=excluded.collected_at
                """,
                {"snapshot_date": day, "cluster_id": cluster_id,
                 "snapshot_ts": snapshot_ts, "collected_at": collected_at, **row},
            )

        connection.execute(
            """
            INSERT INTO topology_daily_runs (
                snapshot_date, cluster_id, snapshot_ts, collected_at,
                family_errors_json, node_count, drive_count, pool_count, erasure_set_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(snapshot_date, cluster_id) DO UPDATE SET
                snapshot_ts=excluded.snapshot_ts, collected_at=excluded.collected_at,
                family_errors_json=excluded.family_errors_json,
                node_count=excluded.node_count, drive_count=excluded.drive_count,
                pool_count=excluded.pool_count, erasure_set_count=excluded.erasure_set_count
            """,
            (day, cluster_id, snapshot_ts, collected_at,
             json.dumps(snapshot.family_errors, sort_keys=True, separators=(",", ":")),
             len(snapshot.nodes), len(snapshot.drives), len(snapshot.pools),
             len(snapshot.erasure_sets)),
        )

    return {
        "nodes": len(snapshot.nodes),
        "drives": len(snapshot.drives),
        "pools": len(snapshot.pools),
        "erasure_sets": len(snapshot.erasure_sets),
    }
