from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml


@dataclass(frozen=True)
class ClusterConfig:
    id: str
    name: str
    prometheus_label_value: str
    identity_label_name: str = "cluster"


@dataclass(frozen=True)
class LocationConfig:
    id: str
    name: str
    prometheus_url: str
    clusters: tuple[ClusterConfig, ...]
    verify_tls: bool = True


def _required_string(data: dict, key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value.strip()


def load_locations(path: str | Path | None = None) -> list[LocationConfig]:
    """Load location-scoped Prometheus endpoints and their cluster label values."""
    configured = str(path or os.getenv("MINIO_ANALYTICS_CONFIG", "")).strip()
    if not configured:
        raise FileNotFoundError(
            "Configuration file not specified. Set MINIO_ANALYTICS_CONFIG "
            "or provide config/locations.yaml."
        )

    config_path = Path(configured).expanduser()
    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {config_path}: {exc}") from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("locations"), list):
        raise ValueError("Configuration must contain a top-level locations list")

    locations: list[LocationConfig] = []
    seen_location_ids: set[str] = set()
    seen_cluster_ids: set[str] = set()

    for index, item in enumerate(raw["locations"]):
        context = f"locations[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{context} must be a mapping")

        location_id = _required_string(item, "id", context)
        name = _required_string(item, "name", context)
        if location_id in seen_location_ids:
            raise ValueError(f"Duplicate location id: {location_id}")
        seen_location_ids.add(location_id)

        prom = item.get("prometheus")
        if not isinstance(prom, dict):
            raise ValueError(f"{context}.prometheus must be a mapping")

        host = _required_string(prom, "host", f"{context}.prometheus")
        scheme = str(prom.get("scheme", "http")).strip().lower()
        if scheme not in {"http", "https"}:
            raise ValueError(f"{context}.prometheus.scheme must be http or https")

        try:
            port = int(prom.get("port", 9090))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{context}.prometheus.port must be an integer") from exc
        if not 1 <= port <= 65535:
            raise ValueError(f"{context}.prometheus.port is outside 1..65535")

        if "://" in host:
            parsed = urlparse(host)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError(f"Invalid Prometheus URL for {name}")
            base_url = host.rstrip("/")
        else:
            base_url = f"{scheme}://{host}:{port}"

        raw_clusters = item.get("clusters")
        if not isinstance(raw_clusters, list) or not raw_clusters:
            raise ValueError(f"{context}.clusters must be a non-empty list")

        clusters: list[ClusterConfig] = []
        for cindex, cluster in enumerate(raw_clusters):
            ccontext = f"{context}.clusters[{cindex}]"
            if not isinstance(cluster, dict):
                raise ValueError(f"{ccontext} must be a mapping")
            cluster_id = _required_string(cluster, "id", ccontext)
            cluster_name = _required_string(cluster, "name", ccontext)
            label_value = _required_string(cluster, "prometheus_label_value", ccontext)
            if cluster_id in seen_cluster_ids:
                raise ValueError(f"Duplicate cluster id: {cluster_id}")
            seen_cluster_ids.add(cluster_id)
            clusters.append(
                ClusterConfig(
                    id=cluster_id,
                    name=cluster_name,
                    prometheus_label_value=label_value,
                )
            )

        locations.append(
            LocationConfig(
                id=location_id,
                name=name,
                prometheus_url=base_url,
                clusters=tuple(clusters),
            )
        )

    if not locations:
        raise ValueError("At least one location must be configured")
    return locations
