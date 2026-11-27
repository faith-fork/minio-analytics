from __future__ import annotations

from math import isfinite
from typing import Any

from app.collectors.prometheus import PrometheusClient
from app.config.loader import ClusterConfig, LocationConfig


METRICS = {
    "rx_bytes_per_second": "node_network_receive_bytes_total",
    "tx_bytes_per_second": "node_network_transmit_bytes_total",
    "rx_packets_per_second": "node_network_receive_packets_total",
    "tx_packets_per_second": "node_network_transmit_packets_total",
    "rx_errors_per_second": "node_network_receive_errs_total",
    "tx_errors_per_second": "node_network_transmit_errs_total",
    "rx_drops_per_second": "node_network_receive_drop_total",
    "tx_drops_per_second": "node_network_transmit_drop_total",
}


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _host(instance: str) -> str:
    # Prometheus commonly formats IPv6 targets as [address]:port.
    if instance.startswith("[") and "]:" in instance:
        return instance[1:instance.rfind("]")]
    return instance.rsplit(":", 1)[0] if instance.count(":") == 1 else instance


def collect_network_metrics(
    location: LocationConfig, cluster: ClusterConfig, snapshot_ts,
) -> tuple[list[dict[str, Any]], str | None]:
    """Collect per-interface rates at a common timestamp; errors are family-isolated."""
    at = int(snapshot_ts.timestamp())
    selector = f'{{{cluster.identity_label_name}="{_escape(cluster.prometheus_label_value)}",job="node_exporter"}}'
    prom = PrometheusClient(location.prometheus_url, verify_tls=location.verify_tls,
                            auth_header=location.auth_header)
    metric_values: dict[str, dict[tuple[str, str], float]] = {}
    errors: list[str] = []
    try:
        for field, metric in METRICS.items():
            try:
                samples = prom.query(f'rate({metric}{selector}[5m])', at=at)
                values: dict[tuple[str, str], float] = {}
                for sample in samples:
                    instance, device = sample.labels.get("instance"), sample.labels.get("device")
                    if not instance or not device or device == "lo":
                        continue
                    if not isfinite(sample.value):
                        continue
                    key = (instance, device)
                    if key in values and values[key] != sample.value:
                        raise ValueError(f"Conflicting values for {metric} {key}")
                    values[key] = sample.value
                metric_values[field] = values
                if not values:
                    errors.append(f"{metric}: no interface samples")
            except Exception as exc:
                metric_values[field] = {}
                errors.append(f"{metric}: {exc}")
    finally:
        try:
            prom.close()
        except Exception as exc:
            errors.append(f"Prometheus client close: {exc}")

    keys = set().union(*(set(values) for values in metric_values.values()))
    rows: list[dict[str, Any]] = []
    for instance, device in sorted(keys):
        row = {"node_name": _host(instance), "instance": instance, "interface_name": device}
        for field, values in metric_values.items():
            row[field] = values.get((instance, device))
        rows.append(row)
    return rows, "; ".join(errors) if errors else None
