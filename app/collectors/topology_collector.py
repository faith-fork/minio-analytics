from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from app.collectors.prometheus import PrometheusClient, PrometheusError
from app.config.loader import ClusterConfig, LocationConfig


@dataclass(frozen=True)
class TopologySnapshot:
    location_id: str
    cluster_id: str
    snapshot_ts: datetime
    collected_at: datetime
    nodes: list[dict[str, Any]] = field(default_factory=list)
    drives: list[dict[str, Any]] = field(default_factory=list)
    pools: list[dict[str, Any]] = field(default_factory=list)
    erasure_sets: list[dict[str, Any]] = field(default_factory=list)
    family_errors: dict[str, str] = field(default_factory=dict)


def _q(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _host(value: str | None) -> str | None:
    if not value:
        return None
    # Exporters use different ports for MinIO and node_exporter.
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


def _samples(
    client: PrometheusClient, metric: str, selector: str, at: int
) -> list:
    return client.query(f"{metric}{selector}", at=at)


def _number(sample) -> float | None:
    value = sample.value
    return value if isfinite(value) else None


def _unique_by(
    samples: list, labels: tuple[str, ...], metric: str
) -> dict[tuple[str, ...], float | None]:
    grouped: dict[tuple[str, ...], list[float]] = {}
    for sample in samples:
        if any(key not in sample.labels for key in labels):
            continue
        key = tuple(sample.labels[key] for key in labels)
        value = _number(sample)
        if value is not None:
            grouped.setdefault(key, []).append(value)
    result: dict[tuple[str, ...], float | None] = {}
    for key, values in grouped.items():
        if max(values) != min(values):
            raise PrometheusError(
                f"Conflicting replicated values for {metric} {key}: {values}"
            )
        result[key] = values[0]
    return result


def collect_topology_snapshot(
    location: LocationConfig,
    cluster: ClusterConfig,
    snapshot_ts: datetime,
    client: PrometheusClient | None = None,
) -> TopologySnapshot:
    """Collect node, drive, pool and erasure-set telemetry at one instant.

    Node/drive identities are based on MinIO's server and drive labels. Node
    exporter instances are correlated by hostname, and filesystem mountpoints
    are correlated with MinIO drive paths ending in /minio. Replicated
    cluster-health gauges are deduplicated and conflicting replicas rejected.
    """
    if snapshot_ts.tzinfo is None or snapshot_ts.utcoffset() is None:
        raise ValueError("snapshot_ts must be timezone-aware")
    own_client = client is None
    prom = client or PrometheusClient(location.prometheus_url)
    at = int(snapshot_ts.timestamp())
    selector = f'{{cluster="{_q(cluster.prometheus_label_value)}"}}'
    node_selector = f'{{cluster="{_q(cluster.prometheus_label_value)}",job="node_exporter"}}'
    minio_node_selector = f'{{cluster="{_q(cluster.prometheus_label_value)}",job="minio-metrics-node"}}'
    collected_at = datetime.now(timezone.utc)
    errors: dict[str, str] = {}

    def query(metric: str, match: str, family: str) -> list:
        try:
            return _samples(prom, metric, match, at)
        except Exception as exc:
            errors[family] = str(exc)
            return []

    def unique(metric: str, match: str, labels: tuple[str, ...], family: str):
        try:
            return _unique_by(query(metric, match, family), labels, metric)
        except Exception as exc:
            errors[family] = str(exc)
            return {}

    try:
        # Node Exporter and MinIO target availability are deliberately distinct.
        node_up = unique("up", node_selector, ("instance",), "nodes")
        minio_up = unique("up", selector + ',job="minio-metrics-node"',
                          ("instance",), "nodes")
        cpu = unique(
            '100 * (1 - avg by (instance) (rate(node_cpu_seconds_total'
            + f'{{cluster="{_q(cluster.prometheus_label_value)}",job="node_exporter",mode="idle"}}'
            + '[5m])))',
            "", ("instance",), "nodes"
        )
        mem_total = unique("node_memory_MemTotal_bytes", node_selector,
                           ("instance",), "nodes")
        mem_available = unique("node_memory_MemAvailable_bytes", node_selector,
                                ("instance",), "nodes")
        load1 = unique("node_load1", node_selector, ("instance",), "nodes")

        node_exporter_hosts = {_host(key[0]) for key in node_up}
        minio_hosts = {_host(key[0]) for key in minio_up}
        if not node_up or not minio_up:
            errors["nodes"] = "Node Exporter or MinIO target availability metrics returned no samples"
        elif node_exporter_hosts != minio_hosts:
            errors["nodes"] = (
                "Node Exporter and MinIO scrape target coverage differs: "
                f"node_exporter={sorted(node_exporter_hosts)}, minio={sorted(minio_hosts)}"
            )
        hostnames = node_exporter_hosts | minio_hosts
        nodes: list[dict[str, Any]] = []
        for hostname in sorted(x for x in hostnames if x):
            node_instance = next((k[0] for k in node_up if _host(k[0]) == hostname), None)
            minio_instance = next((k[0] for k in minio_up if _host(k[0]) == hostname), None)
            node_key = (node_instance,) if node_instance else None
            minio_key = (minio_instance,) if minio_instance else None
            total = mem_total.get(node_key) if node_key else None
            available = mem_available.get(node_key) if node_key else None
            nodes.append({
                "node_name": hostname,
                "node_exporter_instance": node_instance,
                "minio_instance": minio_instance,
                "node_exporter_up": node_up.get(node_key) if node_key else None,
                "minio_scrape_up": minio_up.get(minio_key) if minio_key else None,
                "cpu_utilization_pct": cpu.get(node_key) if node_key else None,
                "memory_total_bytes": total,
                "memory_available_bytes": available,
                "memory_used_bytes": total - available if total is not None and available is not None else None,
                "load1": load1.get(node_key) if node_key else None,
            })

        # Per-drive MinIO metrics.
        drive_metrics = {
            "total_bytes": unique("minio_node_drive_total_bytes", minio_node_selector,
                                  ("server", "drive"), "drives"),
            "used_bytes": unique("minio_node_drive_used_bytes", minio_node_selector,
                                 ("server", "drive"), "drives"),
            "free_bytes": unique("minio_node_drive_free_bytes", minio_node_selector,
                                 ("server", "drive"), "drives"),
            "availability_errors": unique("minio_node_drive_errors_availability",
                                          minio_node_selector, ("server", "drive"), "drives"),
            "io_errors": unique("minio_node_drive_errors_ioerror",
                                minio_node_selector, ("server", "drive"), "drives"),
            "timeout_errors": unique("minio_node_drive_errors_timeout",
                                     minio_node_selector, ("server", "drive"), "drives"),
        }
        drive_reference = set(drive_metrics["total_bytes"])
        if not drive_reference:
            errors["drives"] = "No per-drive MinIO capacity samples returned"
        else:
            incomplete = [
                name for name, values in drive_metrics.items()
                if set(values) != drive_reference
            ]
            if incomplete:
                errors["drives"] = "Incomplete per-drive metric coverage: " + ", ".join(incomplete)

        fs_match = f'{{cluster="{_q(cluster.prometheus_label_value)}",job="node_exporter",mountpoint=~"/mnt/datadisk[0-9]+"}}'
        filesystem_metrics = {
            "filesystem_total_bytes": unique("node_filesystem_size_bytes", fs_match,
                                             ("instance", "mountpoint"), "filesystems"),
            "filesystem_available_bytes": unique("node_filesystem_avail_bytes", fs_match,
                                                 ("instance", "mountpoint"), "filesystems"),
            "filesystem_free_bytes": unique("node_filesystem_free_bytes", fs_match,
                                            ("instance", "mountpoint"), "filesystems"),
            "filesystem_readonly": unique("node_filesystem_readonly", fs_match,
                                          ("instance", "mountpoint"), "filesystems"),
        }

        filesystem_reference = set(filesystem_metrics["filesystem_total_bytes"])
        if not filesystem_reference:
            errors["filesystems"] = "No MinIO data mount filesystem metrics returned"
        else:
            incomplete_fs = [
                name for name, values in filesystem_metrics.items()
                if set(values) != filesystem_reference
            ]
            if incomplete_fs:
                errors["filesystems"] = "Incomplete filesystem metric coverage: " + ", ".join(incomplete_fs)

        drive_keys = set().union(*(set(values) for values in drive_metrics.values()))
        drives: list[dict[str, Any]] = []
        for server, drive_path in sorted(drive_keys):
            host = _host(server)
            mountpoint = drive_path[:-len("/minio")] if drive_path.endswith("/minio") else None
            fs_instance = next(
                (key[0] for key in filesystem_metrics["filesystem_total_bytes"]
                 if _host(key[0]) == host), None
            )
            fs_key = (fs_instance, mountpoint) if fs_instance and mountpoint else None
            row: dict[str, Any] = {
                "node_name": host,
                "server": server,
                "drive_path": drive_path,
                "mountpoint": mountpoint,
            }
            for name, values in drive_metrics.items():
                row[name] = values.get((server, drive_path))
            for name, values in filesystem_metrics.items():
                row[name] = values.get(fs_key) if fs_key else None
            total = row["filesystem_total_bytes"]
            available = row["filesystem_available_bytes"]
            row["filesystem_used_bytes"] = (
                total - available if total is not None and available is not None else None
            )
            row["filesystem_used_pct"] = (
                (total - available) / total * 100
                if total and available is not None else None
            )
            drives.append(row)

        # Pool/set metrics are replicated on each MinIO node. Deduplicate on
        # pool + set and retain the raw numeric status value without guessing
        # its enum interpretation.
        set_metrics = {
            "status_value": unique("minio_cluster_health_erasure_set_status", selector,
                                   ("pool", "set"), "erasure_sets"),
            "online_drives": unique("minio_cluster_health_erasure_set_online_drives",
                                    selector, ("pool", "set"), "erasure_sets"),
            "healing_drives": unique("minio_cluster_health_erasure_set_healing_drives",
                                     selector, ("pool", "set"), "erasure_sets"),
            "read_quorum": unique("minio_cluster_health_erasure_set_read_quorum",
                                  selector, ("pool", "set"), "erasure_sets"),
            "write_quorum": unique("minio_cluster_health_erasure_set_write_quorum",
                                   selector, ("pool", "set"), "erasure_sets"),
        }
        set_keys = set().union(*(set(values) for values in set_metrics.values()))
        if not set_keys:
            errors["erasure_sets"] = "No erasure-set health metrics returned"
        else:
            incomplete_sets = [
                name for name, values in set_metrics.items()
                if set(values) != set_keys
            ]
            if incomplete_sets:
                errors["erasure_sets"] = "Incomplete erasure-set metric coverage: " + ", ".join(incomplete_sets)
        erasure_sets = []
        pool_groups: dict[str, list[dict[str, Any]]] = {}
        for pool, set_id in sorted(set_keys):
            row = {"pool_id": pool, "set_id": set_id}
            for name, values in set_metrics.items():
                row[name] = values.get((pool, set_id))
            erasure_sets.append(row)
            pool_groups.setdefault(pool, []).append(row)

        pools = []
        for pool_id, sets in sorted(pool_groups.items()):
            pools.append({
                "pool_id": pool_id,
                "erasure_set_count": len(sets),
                "online_drives": (
                    sum(row["online_drives"] for row in sets)
                    if all(row["online_drives"] is not None for row in sets) else None
                ),
                "healing_drives": (
                    sum(row["healing_drives"] for row in sets)
                    if all(row["healing_drives"] is not None for row in sets) else None
                ),
            })

        return TopologySnapshot(
            location_id=location.id,
            cluster_id=cluster.id,
            snapshot_ts=snapshot_ts,
            collected_at=collected_at,
            nodes=nodes,
            drives=drives,
            pools=pools,
            erasure_sets=erasure_sets,
            family_errors=errors,
        )
    finally:
        if own_client:
            prom.close()
