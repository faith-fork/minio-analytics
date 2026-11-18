from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.collectors.prometheus import PrometheusClient, PrometheusError
from app.config.loader import ClusterConfig, LocationConfig

RAW_EFF_FACTOR = 0.993
LOOKBACK_DAYS = 30


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


def _scalar(client: PrometheusClient, promql: str, at: int | None = None) -> float | None:
    samples = client.query(promql, at=at)
    if not samples:
        return None
    if len(samples) != 1:
        raise PrometheusError(
            f"Expected one sample for scalar query, received {len(samples)}: {promql}"
        )
    return samples[0].value


def collect_cluster_snapshot(
    location: LocationConfig,
    cluster: ClusterConfig,
    snapshot_ts: datetime,
    client: PrometheusClient | None = None,
) -> ClusterSnapshot:
    """Collect cluster capacity/node metrics at one shared snapshot timestamp.

    The endpoint is location-scoped. When a location has multiple clusters,
    metric labels must be checked and filtered to the correct cluster before
    enabling collection for that location.
    """
    own_client = client is None
    prom = client or PrometheusClient(location.prometheus_url)
    collected_at = datetime.now(timezone.utc)
    timestamp = int(snapshot_ts.timestamp())

    queries = {
        "raw_total_bytes": (
            f"max(minio_cluster_capacity_raw_total_bytes @ {timestamp}) * {RAW_EFF_FACTOR}"
        ),
        "raw_free_bytes": (
            f"max(minio_cluster_capacity_raw_free_bytes @ {timestamp})"
        ),
        "usable_total_bytes": (
            f"max(minio_cluster_capacity_usable_total_bytes @ {timestamp})"
        ),
        "usable_free_bytes": (
            f"max(minio_cluster_capacity_usable_free_bytes @ {timestamp})"
        ),
        "nodes_online": "max(minio_cluster_nodes_online_total)",
        "nodes_offline": "max(minio_cluster_nodes_offline_total)",
        "growth_bytes_per_day": (
            "deriv((max(minio_cluster_capacity_raw_total_bytes) * "
            f"{RAW_EFF_FACTOR} - max(minio_cluster_capacity_raw_free_bytes)"
            f")[{LOOKBACK_DAYS}d:1d]) * 86400"
        ),
        "days_to_full": (
            f"(max(minio_cluster_capacity_raw_free_bytes @ {timestamp}) / "
            f"-deriv(max(minio_cluster_capacity_raw_free_bytes)[{LOOKBACK_DAYS}d:1d])) / 86400"
        ),
    }

    try:
        values = {name: _scalar(prom, query) for name, query in queries.items()}
        # Required storage capacity metrics must be present. Missing values are
        # not coerced to zero, since that would make an unavailable metric look valid.
        required = (
            "raw_total_bytes",
            "raw_free_bytes",
            "usable_total_bytes",
            "usable_free_bytes",
        )
        missing = [name for name in required if values[name] is None]
        if missing:
            raise PrometheusError(f"Missing required metrics: {', '.join(missing)}")

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
