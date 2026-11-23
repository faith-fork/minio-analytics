from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit


class PrometheusEndpointError(ValueError):
    """Raised when a Prometheus endpoint violates outbound network policy."""


_PRIVATE_V4 = tuple(ipaddress.ip_network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
))
_PRIVATE_V6 = ipaddress.ip_network("fc00::/7")
_BLOCKED_METADATA = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("100.100.100.200"),
    ipaddress.ip_address("fd00:ec2::254"),
}


def _normalized_address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    address = ipaddress.ip_address(value.split("%", 1)[0])
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


def _address_allowed(value: str) -> bool:
    address = _normalized_address(value)
    if address in _BLOCKED_METADATA:
        return False
    if address.is_global:
        return True
    if isinstance(address, ipaddress.IPv4Address):
        return any(address in network for network in _PRIVATE_V4)
    return address in _PRIVATE_V6


def resolve_prometheus_endpoint(base_url: str, *, resolver=None) -> tuple[str, int, tuple[str, ...], str]:
    """Validate endpoint syntax and return the exact IPs to which transport must connect.

    RFC1918 IPv4 and IPv6 ULA customer networks are allowed. Every A/AAAA
    answer must satisfy policy. The returned address set must be used by the
    transport directly; resolving the hostname again would reintroduce DNS
    rebinding between validation and connection.
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
        addresses = {_normalized_address(record[4][0]) for record in records}
    else:
        addresses = {_normalized_address(str(literal))}

    if not addresses:
        raise PrometheusEndpointError("Prometheus hostname resolved to no addresses")
    if not all(_address_allowed(str(address)) for address in addresses):
        raise PrometheusEndpointError(
            "Prometheus endpoint resolves to a prohibited network address"
        )
    return host, port, tuple(sorted(str(address) for address in addresses)), parsed.scheme


def validate_prometheus_endpoint(base_url: str, *, resolver=None) -> tuple[str, int]:
    """Compatibility helper returning the validated hostname and port."""
    host, port, _addresses, _scheme = resolve_prometheus_endpoint(
        base_url, resolver=resolver
    )
    return host, port
