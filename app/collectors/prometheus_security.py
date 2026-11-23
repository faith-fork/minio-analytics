from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit


class PrometheusEndpointError(ValueError):
    """Raised when a Prometheus endpoint violates outbound network policy."""


# RFC1918 customer networks and IPv6 Unique Local Addresses are intentionally
# supported. Other non-global ranges (loopback, link-local, CGNAT, multicast,
# reserved, unspecified, documentation and benchmarking ranges) are denied.
_PRIVATE_V4 = tuple(ipaddress.ip_network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
))
_PRIVATE_V6 = ipaddress.ip_network("fc00::/7")
_BLOCKED_METADATA = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("100.100.100.200"),
}


def _address_allowed(value: str) -> bool:
    address = ipaddress.ip_address(value.split("%", 1)[0])
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    if address in _BLOCKED_METADATA:
        return False
    if address.is_global:
        return True
    if isinstance(address, ipaddress.IPv4Address):
        return any(address in network for network in _PRIVATE_V4)
    return address in _PRIVATE_V6


def validate_prometheus_endpoint(base_url: str, *, resolver=None) -> tuple[str, int]:
    """Validate a Prometheus URL and every address currently returned by DNS.

    Private customer-network IPv4 and IPv6 ULA destinations are allowed.
    DNS is checked immediately before each request. This preflight check does
    not pin the subsequent TCP connection to the validated address; deployments
    requiring protection against an actively rebinding DNS server must additionally
    enforce outbound network policy at the host/network boundary.
    """
    try:
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"}:
            raise PrometheusEndpointError("Prometheus URL must use http or https")
        if not parsed.hostname or parsed.username or parsed.password:
            raise PrometheusEndpointError("Prometheus URL must contain a hostname and no credentials")
        if parsed.query or parsed.fragment:
            raise PrometheusEndpointError("Prometheus URL must not contain a query or fragment")
        if parsed.path not in {"", "/"}:
            raise PrometheusEndpointError("Prometheus base URL must not contain a path")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        if isinstance(exc, PrometheusEndpointError):
            raise
        raise PrometheusEndpointError("Invalid Prometheus URL") from exc

    host = parsed.hostname
    if "%" in host:
        raise PrometheusEndpointError("Scoped IPv6 addresses are not supported")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        lookup = resolver or socket.getaddrinfo
        try:
            records = lookup(host, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise PrometheusEndpointError("Prometheus hostname could not be resolved") from exc
        addresses = {record[4][0] for record in records}
    else:
        addresses = {str(literal)}

    if not addresses:
        raise PrometheusEndpointError("Prometheus hostname resolved to no addresses")
    if not all(_address_allowed(address) for address in addresses):
        raise PrometheusEndpointError(
            "Prometheus endpoint resolves to a prohibited network address"
        )
    return host, port
