from __future__ import annotations

import json

import pytest

from app.collectors import prometheus as module
from app.collectors.prometheus import PrometheusClient, PrometheusError


class FakeResponse:
    def __init__(self, body=None, status=200):
        self.status = status
        self.body = body if body is not None else json.dumps({
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [{"metric": {"cluster": "site-a"}, "value": [123.0, "7"]}],
            },
        }).encode()
        self.closed = False

    def stream(self, amt, decode_content):
        for offset in range(0, len(self.body), 7):
            yield self.body[offset:offset + 7]

    def close(self):
        self.closed = True


class FakePool:
    instances = []
    response = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.request_kwargs = None
        self.closed = False
        self.__class__.instances.append(self)

    def request(self, *args, **kwargs):
        self.request_kwargs = (args, kwargs)
        return self.__class__.response or FakeResponse()

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def reset_pool():
    FakePool.instances = []
    FakePool.response = None
    yield


def test_http_query_uses_pinned_ip_and_preserves_hostname(monkeypatch):
    monkeypatch.setattr(module, "resolve_prometheus_endpoint",
        lambda url: ("prometheus.customer.internal", 9090, ("10.2.3.4",), "http"))
    monkeypatch.setattr(module, "_PinnedHTTPConnectionPool", FakePool)

    samples = PrometheusClient("http://prometheus.customer.internal:9090").query("up")

    pool = FakePool.instances[0]
    assert pool.kwargs["host"] == "prometheus.customer.internal"
    assert pool.kwargs["pinned_ip"] == "10.2.3.4"
    assert samples[0].labels == {"cluster": "site-a"}
    assert samples[0].value == 7.0
    assert pool.request_kwargs[1]["redirect"] is False
    assert pool.request_kwargs[1]["retries"] is False
    assert pool.closed


def test_https_query_keeps_hostname_for_sni_and_certificate_validation(monkeypatch):
    monkeypatch.setattr(module, "resolve_prometheus_endpoint",
        lambda url: ("prometheus.customer.internal", 9443, ("10.2.3.4",), "https"))
    monkeypatch.setattr(module, "_PinnedHTTPSConnectionPool", FakePool)

    PrometheusClient("https://prometheus.customer.internal:9443").query("up")

    kwargs = FakePool.instances[0].kwargs
    assert kwargs["host"] == "prometheus.customer.internal"
    assert kwargs["pinned_ip"] == "10.2.3.4"
    assert kwargs["assert_hostname"] == "prometheus.customer.internal"
    assert kwargs["server_hostname"] == "prometheus.customer.internal"
    assert kwargs["cert_reqs"] == module.ssl.CERT_REQUIRED


def test_tls_verification_can_only_be_disabled_explicitly(monkeypatch):
    monkeypatch.setattr(module, "resolve_prometheus_endpoint",
        lambda url: ("10.2.3.4", 9443, ("10.2.3.4",), "https"))
    monkeypatch.setattr(module, "_PinnedHTTPSConnectionPool", FakePool)

    PrometheusClient("https://10.2.3.4:9443", verify_tls=False).query("up")

    kwargs = FakePool.instances[0].kwargs
    assert kwargs["cert_reqs"] == module.ssl.CERT_NONE
    assert kwargs["assert_hostname"] is False


def test_redirect_is_rejected_and_response_closed(monkeypatch):
    monkeypatch.setattr(module, "resolve_prometheus_endpoint",
        lambda url: ("10.2.3.4", 9090, ("10.2.3.4",), "http"))
    monkeypatch.setattr(module, "_PinnedHTTPConnectionPool", FakePool)
    FakePool.response = FakeResponse(status=302)

    with pytest.raises(PrometheusError, match="redirects"):
        PrometheusClient("http://10.2.3.4:9090").query("up")
    assert FakePool.response.closed


def test_response_size_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(module, "resolve_prometheus_endpoint",
        lambda url: ("10.2.3.4", 9090, ("10.2.3.4",), "http"))
    monkeypatch.setattr(module, "_PinnedHTTPConnectionPool", FakePool)
    FakePool.response = FakeResponse(body=b"x" * (PrometheusClient.MAX_RESPONSE_BYTES + 1))

    with pytest.raises(PrometheusError, match="4 MiB"):
        PrometheusClient("http://10.2.3.4:9090").query("up")
    assert FakePool.response.closed


def test_request_timeout_is_passed_to_transport(monkeypatch):
    monkeypatch.setattr(module, "resolve_prometheus_endpoint",
        lambda url: ("10.2.3.4", 9090, ("10.2.3.4",), "http"))
    monkeypatch.setattr(module, "_PinnedHTTPConnectionPool", FakePool)

    PrometheusClient("http://10.2.3.4:9090", timeout_seconds=6.5).query("up")

    timeout = FakePool.instances[0].request_kwargs[1]["timeout"]
    assert timeout.total == 6.5


def test_prohibited_endpoint_is_rejected_before_transport_creation(monkeypatch):
    monkeypatch.setattr(module, "_PinnedHTTPConnectionPool", FakePool)

    with pytest.raises(PrometheusError, match="prohibited"):
        PrometheusClient("http://127.0.0.1:9090").query("up")
    assert FakePool.instances == []
