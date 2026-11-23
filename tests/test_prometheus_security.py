from __future__ import annotations

import socket

import pytest

from app.collectors.prometheus_security import (
    PrometheusEndpointError,
    resolve_prometheus_endpoint,
    validate_prometheus_endpoint,
)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:9090",
    "http://localhost:9090",
    "http://169.254.1.10:9090",
    "http://169.254.169.254:80",
    "http://100.100.100.200:80",
    "http://fd00:ec2::254:80",
    "http://0.0.0.0:9090",
    "http://224.0.0.1:9090",
    "http://[::1]:9090",
    "http://[fe80::1]:9090",
    "http://[::]:9090",
    "http://[::ffff:127.0.0.1]:9090",
])
def test_rejects_loopback_link_local_metadata_and_special_ranges(url):
    with pytest.raises(PrometheusEndpointError):
        validate_prometheus_endpoint(url)


@pytest.mark.parametrize("url", [
    "http://10.1.2.3:9090",
    "http://172.16.0.10:9090",
    "http://172.31.255.254:9090",
    "http://192.168.10.20:9090",
    "http://[fd00::10]:9090",
    "https://8.8.8.8:443",
])
def test_allows_customer_private_and_global_addresses(url):
    validate_prometheus_endpoint(url)


def test_rejects_hostname_when_any_dns_answer_is_prohibited():
    def resolver(host, port, type):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port)),
        ]

    with pytest.raises(PrometheusEndpointError, match="prohibited"):
        resolve_prometheus_endpoint("http://prometheus.internal:9090", resolver=resolver)


def test_pins_every_resolved_customer_address_without_resolving_again():
    def resolver(host, port, type):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.2", port)),
        ]

    host, port, addresses, scheme = resolve_prometheus_endpoint(
        "https://prometheus.internal:9090", resolver=resolver
    )
    assert (host, port, scheme) == ("prometheus.internal", 9090, "https")
    assert addresses == ("10.1.2.3", "192.168.1.2")


@pytest.mark.parametrize("url", [
    "ftp://prometheus.internal:9090",
    "http://user:password@10.1.2.3:9090",
    "http://10.1.2.3:9090/path",
    "http://10.1.2.3:9090/?token=secret",
])
def test_rejects_unsupported_or_credential_bearing_urls(url):
    with pytest.raises(PrometheusEndpointError):
        validate_prometheus_endpoint(url)
