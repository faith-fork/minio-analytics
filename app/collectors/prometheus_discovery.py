from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlsplit
import ipaddress

from app.collectors.prometheus import PrometheusClient, PrometheusError


IDENTITY_LABELS = ("cluster", "site", "environment")
IDENTIFICATION_METRICS = (
    "minio_cluster_capacity_raw_total_bytes",
    "minio_cluster_nodes_online_total",
)


def build_prometheus_url(protocol: str, hostname: str, port: int) -> str:
    """Validate connection fields and build a Prometheus base URL."""
    scheme = protocol.strip().lower()
    host = hostname.strip()
    if scheme not in {"http", "https"}:
        raise ValueError("Protocol must be http or https")
    if not host or any(char in host for char in "/?#@"):
        raise ValueError("Enter a hostname or IP address, not a URL")
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    # Accept IPv4, DNS names and IPv6 literals; the latter need URL brackets.
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        parsed = urlsplit(f"{scheme}://{host}")
        try:
            parsed_port = parsed.port
        except ValueError as exc:
            raise ValueError("Invalid Prometheus hostname") from exc
        if not parsed.hostname or parsed.path or parsed.query or parsed.fragment:
            raise ValueError("Invalid Prometheus hostname")
        if parsed_port is not None:
            raise ValueError("Do not include a port in the hostname field")
        url_host = host
    else:
        url_host = f"[{address}]" if address.version == 6 else str(address)
    return f"{scheme}://{url_host}:{port}"


def discover_minio_clusters(
    base_url: str,
    *,
    timeout_seconds: float = 8.0,
    verify_tls: bool = True,
    client: PrometheusClient | None = None,
) -> dict:
    """Probe Prometheus and discover MinIO cluster identities without writes."""
    own_client = client is None
    prom = client or PrometheusClient(
        base_url, timeout_seconds=timeout_seconds, verify_tls=verify_tls
    )
    try:
        discovered: dict[tuple[str, str], set[str]] = defaultdict(set)
        metric_errors: list[str] = []
        for metric in IDENTIFICATION_METRICS:
            try:
                samples = prom.query(metric)
            except PrometheusError as exc:
                metric_errors.append(f"{metric}: {exc}")
                continue
            for sample in samples:
                for label in IDENTITY_LABELS:
                    value = sample.labels.get(label, "").strip()
                    if value:
                        discovered[(label, value)].add(metric)

        if not discovered:
            detail = "; ".join(metric_errors) or "No MinIO cluster identity labels were found"
            raise PrometheusError(
                "Prometheus is reachable, but MinIO cluster discovery failed. " + detail
            )

        # Select one identity dimension for the whole endpoint. Prefer the
        # canonical cluster label; use site/environment only when it is absent.
        selected_label = next(
            (label for label in IDENTITY_LABELS
             if any(key[0] == label for key in discovered)),
            None,
        )
        selected = [
            (key, metrics) for key, metrics in discovered.items()
            if key[0] == selected_label
        ]
        ordered = sorted(selected, key=lambda item: item[0][1].casefold())
        clusters = [
            {
                "label_name": label,
                "label_value": value,
                "metrics_found": sorted(metrics),
            }
            for ((label, value), metrics) in ordered
        ]
        label_names = sorted({item["label_name"] for item in clusters})
        return {
            "status": "success",
            "prometheus_url": base_url,
            "minio_metrics_found": True,
            "identity_labels": label_names,
            "clusters": clusters,
            "cluster_count": len(clusters),
            "selection_required": len(clusters) > 1,
            "warnings": metric_errors,
        }
    finally:
        if own_client:
            prom.close()
