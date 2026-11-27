from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Optional

from app.collectors.prometheus import PrometheusClient, PrometheusError
from app.config.loader import ClusterConfig, LocationConfig

RAW_EFF_FACTOR = 0.993
LOOKBACK_DAYS = 30
DAYS_TO_FULL_MIN_SAMPLES = 14
MAX_DAYS_TO_FULL = 1825


@dataclass(frozen=True)
class ClusterSnapshot:
    location_id: str
    location_name: str
    cluster_id: str
    cluster_name: str
    snapshot_ts: datetime
    collected_at: datetime
    raw_total_bytes: Optional[float]
    raw_free_bytes: Optional[float]
    usable_total_bytes: Optional[float]
    usable_free_bytes: Optional[float]
    nodes_online: Optional[int]
    nodes_offline: Optional[int]
    growth_bytes_per_day: Optional[float]
    days_to_full: Optional[float]
    metrics_available: bool
    error_text: Optional[str] = None


def _promql_string(value: str) -> str:
    """Escape a string for use inside a PromQL double-quoted label matcher."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _scalar(
    client: PrometheusClient, promql: str, at: int | float | None = None
) -> float | None:
    samples = client.query(promql, at=at)
    if not samples:
        return None
    if len(samples) != 1:
        raise PrometheusError(
            f"Expected one aggregated sample, received {len(samples)}: {promql}"
        )
    value = samples[0].value
    if not isfinite(value):
        return None
    return value


def collect_cluster_snapshot(
    location: LocationConfig,
    cluster: ClusterConfig,
    snapshot_ts: datetime,
    client: PrometheusClient | None = None,
) -> ClusterSnapshot:
    """Collect one cluster from a location-level Prometheus endpoint.

    MinIO exports cluster-wide gauges on multiple nodes/jobs. max() over the
    exact cluster label deliberately deduplicates those repeated observations;
    summing them would multiply capacity and node counts.
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

    queries = {
        "raw_total_bytes": (
            f"max(minio_cluster_capacity_raw_total_bytes{selector}) * {RAW_EFF_FACTOR}"
        ),
        "raw_free_bytes": f"max(minio_cluster_capacity_raw_free_bytes{selector})",
        "usable_total_bytes": f"max(minio_cluster_capacity_usable_total_bytes{selector})",
        "usable_free_bytes": f"max(minio_cluster_capacity_usable_free_bytes{selector})",
        "nodes_online": f"max(minio_cluster_nodes_online_total{selector})",
        "nodes_offline": f"max(minio_cluster_nodes_offline_total{selector})",
        "growth_bytes_per_day": (
            f"deriv((max(minio_cluster_capacity_raw_total_bytes{selector}) * "
            f"{RAW_EFF_FACTOR} - max(minio_cluster_capacity_raw_free_bytes{selector})"
            f")[{LOOKBACK_DAYS}d:1d]) * 86400"
        ),
        # A forecast is meaningful only when the 30-day window contains
        # enough daily observations and free capacity is genuinely declining.
        # Missing/insufficient history or a flat/increasing free-capacity trend
        # returns an empty vector, which is stored as unavailable (not zero).
        "days_to_full": (
            f"((max(minio_cluster_capacity_raw_free_bytes{selector}) / "
            f"-deriv((max(minio_cluster_capacity_raw_free_bytes{selector}))"
            f"[{LOOKBACK_DAYS}d:1d])) / 86400) "
            f"and (count_over_time((max(minio_cluster_capacity_raw_free_bytes{selector}))"
            f"[{LOOKBACK_DAYS}d:1d]) >= {DAYS_TO_FULL_MIN_SAMPLES}) "
            f"and (deriv((max(minio_cluster_capacity_raw_free_bytes{selector}))"
            f"[{LOOKBACK_DAYS}d:1d]) < 0) "
            f"and (((max(minio_cluster_capacity_raw_free_bytes{selector}) / "
            f"-deriv((max(minio_cluster_capacity_raw_free_bytes{selector}))"
            f"[{LOOKBACK_DAYS}d:1d])) / 86400) <= {MAX_DAYS_TO_FULL})"
        ),
    }

    try:
        values = {
            name: _scalar(prom, query, at=timestamp)
            for name, query in queries.items()
        }
        required = (
            "raw_total_bytes",
            "raw_free_bytes",
            "usable_total_bytes",
            "usable_free_bytes",
        )
        missing = [name for name in required if values[name] is None]
        if missing:
            raise PrometheusError(
                f"Missing required metrics for Prometheus cluster "
                f"{cluster.prometheus_label_value}: {', '.join(missing)}"
            )

        online = values["nodes_online"]
        offline = values["nodes_offline"]
        return ClusterSnapshot(
            location_id=location.id,
            location_name=location.name,
            cluster_id=cluster.id,
            cluster_name=cluster.name,
            snapshot_ts=snapshot_ts,
            collected_at=collected_at,
            raw_total_bytes=values["raw_total_bytes"],
            raw_free_bytes=values["raw_free_bytes"],
            usable_total_bytes=values["usable_total_bytes"],
            usable_free_bytes=values["usable_free_bytes"],
            nodes_online=int(online) if online is not None else None,
            nodes_offline=int(offline) if offline is not None else None,
            growth_bytes_per_day=values["growth_bytes_per_day"],
            days_to_full=values["days_to_full"],
            metrics_available=True,
        )
    except Exception as exc:
        return ClusterSnapshot(
            location_id=location.id,
            location_name=location.name,
            cluster_id=cluster.id,
            cluster_name=cluster.name,
            snapshot_ts=snapshot_ts,
            collected_at=collected_at,
            raw_total_bytes=None,
            raw_free_bytes=None,
            usable_total_bytes=None,
            usable_free_bytes=None,
            nodes_online=None,
            nodes_offline=None,
            growth_bytes_per_day=None,
            days_to_full=None,
            metrics_available=False,
            error_text=str(exc),
        )
    finally:
        if own_client:
            prom.close()
