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
# RFC 6598 Shared Address Space is used by some enterprise/customer networks.
_SHARED_V4 = ipaddress.ip_network("100.64.0.0/10")
# Treat the rest of 100.0.0.0/8 conservatively as non-public. Some Python
# ipaddress versions classify addresses outside RFC 6598 in this block as
# global; they must not become an accidental bypass of the shared-range rule.
_IPV4_100_BLOCK = ipaddress.ip_network("100.0.0.0/8")
_BLOCKED_METADATA = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("100.100.100.200"),
    ipaddress.ip_address("fd00:ec2::254"),
    ipaddress.ip_address("168.63.129.16"),
}


def _normalized_address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    address = ipaddress.ip_address(value.split("%", 1)[0])
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


def _address_allowed(value: str) -> bool:
    """Allow customer/private and globally routable targets, deny special targets."""
    address = _normalized_address(value)
    if address in _BLOCKED_METADATA:
        return False
    if address.is_loopback or address.is_link_local or address.is_multicast:
        return False
    if address.is_unspecified or address.is_reserved:
        return False
    if isinstance(address, ipaddress.IPv4Address):
        # Only RFC 6598 within 100.0.0.0/8 is accepted for customer networks.
        # Do this before is_global: its classification has varied by Python
        # version for addresses surrounding the shared-address block.
        if address in _IPV4_100_BLOCK:
            return address in _SHARED_V4
        if address.is_global:
            return True
        return any(address in network for network in _PRIVATE_V4)
    if address.is_global:
        return True
    return address in _PRIVATE_V6
    return address in _PRIVATE_V6


def resolve_prometheus_endpoint(base_url: str, *, resolver=None) -> tuple[str, int, tuple[str, ...], str]:
    """Validate a Prometheus endpoint and return the exact addresses to connect to.

    Hostnames use the operating system resolver (DNS and local hosts sources,
    according to system resolver configuration). Every A/AAAA result must be
    allowed; mixed safe/unsafe answer sets are rejected. The returned IPs must
    be used directly by the transport to prevent a second DNS lookup/rebinding.
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
        # getaddrinfo follows the host's configured NSS resolver path, including
        # /etc/hosts where configured, as well as DNS.
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
