from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from typing import Optional

from app.collectors.prometheus import PrometheusClient, PrometheusError
from app.config.loader import ClusterConfig, LocationConfig

BUCKET_USAGE_METRIC = "minio_cluster_usage_buckets_total_bytes"
BUCKET_QUOTA_METRIC = "minio_cluster_usage_buckets_quota_total_bytes"
BUCKET_OBJECTS_METRIC = "minio_cluster_usage_buckets_objects_count"
BUCKET_OBJECT_SIZE_METRIC = "minio_cluster_usage_buckets_object_size_distribution"
BUCKET_VERSION_DISTRIBUTION_METRIC = (
    "minio_cluster_usage_buckets_object_version_count_distribution"
)


@dataclass(frozen=True)
class BucketSnapshot:
    location_id: str
    location_name: str
    cluster_id: str
    cluster_name: str
    bucket_name: str
    snapshot_ts: datetime
    collected_at: datetime
    used_bytes: float
    quota_bytes: Optional[float]
    object_count: Optional[int]
    object_size_distribution: dict[str, int] = field(default_factory=dict)
    version_count_distribution: dict[str, int] = field(default_factory=dict)
    metrics_available: bool = True
    error_text: Optional[str] = None


def _promql_string(value: str) -> str:
    """Escape a string for a PromQL double-quoted label matcher."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _number(value: float, metric: str) -> float:
    if not isfinite(value) or value < 0:
        raise PrometheusError(f"Invalid value for {metric}: {value}")
    return value


def _deduplicate(
    client: PrometheusClient,
    metric: str,
    selector: str,
    group_labels: tuple[str, ...],
    at: int,
) -> dict[tuple[str, ...], float]:
    """Deduplicate replicated MinIO gauges and reject conflicting replicas.

    The lab endpoint reports identical bucket gauges from all four nodes.
    max by (...) selects one replica without multiplying the value. We also
    compare raw replicas first so an inconsistent set is not silently hidden.
    """
    raw = client.query(f"{metric}{selector}", at=at)
    grouped: dict[tuple[str, ...], list[float]] = {}

    for sample in raw:
        if any(label not in sample.labels for label in group_labels):
            raise PrometheusError(
                f"{metric} sample is missing one of labels {group_labels}: "
                f"{sample.labels}"
            )
        key = tuple(sample.labels[label] for label in group_labels)
        grouped.setdefault(key, []).append(_number(sample.value, metric))

    result: dict[tuple[str, ...], float] = {}
    for key, values in grouped.items():
        if max(values) != min(values):
            raise PrometheusError(
                f"Conflicting replicated values for {metric} {key}: {values}"
            )
        result[key] = max(values)

    return result


def collect_bucket_snapshots(
    location: LocationConfig,
    cluster: ClusterConfig,
    snapshot_ts: datetime,
    client: PrometheusClient | None = None,
) -> list[BucketSnapshot]:
    """Collect one cluster's bucket usage and available distribution metrics.

    Bucket usage is the inventory source. Quota, object count, and distribution
    metrics are optional per bucket. Missing optional metrics remain None or an
    empty distribution; they are never converted to zero.

    The current MinIO endpoint repeats these gauges identically on each node.
    Replicas are deduplicated, never summed. Conflicting replicas fail the
    collection rather than choosing an arbitrary value.
    """
    own_client = client is None
    prom = client or PrometheusClient(
        location.prometheus_url, verify_tls=location.verify_tls,
        auth_header=location.auth_header
    )
    collected_at = datetime.now(timezone.utc)
    timestamp = int(snapshot_ts.timestamp())
    label_value = _promql_string(cluster.prometheus_label_value)
    selector = f'{{{cluster.identity_label_name}="{label_value}"}}'

    try:
        usage = _deduplicate(
            prom, BUCKET_USAGE_METRIC, selector, ("bucket",), timestamp
        )
        if not usage:
            raise PrometheusError(
                f"No bucket usage metrics for Prometheus cluster "
                f"{cluster.prometheus_label_value}"
            )

        quotas = _deduplicate(
            prom, BUCKET_QUOTA_METRIC, selector, ("bucket",), timestamp
        )
        objects = _deduplicate(
            prom, BUCKET_OBJECTS_METRIC, selector, ("bucket",), timestamp
        )
        object_sizes = _deduplicate(
            prom,
            BUCKET_OBJECT_SIZE_METRIC,
            selector,
            ("bucket", "range"),
            timestamp,
        )
        version_distribution = _deduplicate(
            prom,
            BUCKET_VERSION_DISTRIBUTION_METRIC,
            selector,
            ("bucket", "range"),
            timestamp,
        )

        bucket_names = sorted(key[0] for key in usage)
        snapshots: list[BucketSnapshot] = []

        for bucket_name in bucket_names:
            size_distribution = {
                range_name: int(value)
                for (name, range_name), value in object_sizes.items()
                if name == bucket_name
            }
            version_counts = {
                range_name: int(value)
                for (name, range_name), value in version_distribution.items()
                if name == bucket_name
            }

            object_value = objects.get((bucket_name,))
            snapshots.append(
                BucketSnapshot(
                    location_id=location.id,
                    location_name=location.name,
                    cluster_id=cluster.id,
                    cluster_name=cluster.name,
                    bucket_name=bucket_name,
                    snapshot_ts=snapshot_ts,
                    collected_at=collected_at,
                    used_bytes=usage[(bucket_name,)],
                    quota_bytes=quotas.get((bucket_name,)),
                    object_count=(
                        int(object_value) if object_value is not None else None
                    ),
                    object_size_distribution=size_distribution,
                    version_count_distribution=version_counts,
                    metrics_available=True,
                )
            )

        return snapshots
    finally:
        if own_client:
            prom.close()
