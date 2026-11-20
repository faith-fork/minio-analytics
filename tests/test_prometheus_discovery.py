from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.collectors.prometheus import MetricSample, PrometheusError
from app.collectors.prometheus_discovery import (
    build_prometheus_url,
    discover_minio_clusters,
)


class FakePrometheus:
    def __init__(self, responses):
        self.responses = responses
        self.queries = []
        self.closed = False

    def query(self, metric):
        self.queries.append(metric)
        response = self.responses.get(metric, [])
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        self.closed = True


def sample(labels, value=1.0):
    return MetricSample(labels=labels, value=value, timestamp=1.0)


@pytest.mark.parametrize(
    ("protocol", "hostname", "port", "expected"),
    [
        ("http", "prometheus.internal", 9090, "http://prometheus.internal:9090"),
        ("https", "10.0.0.5", 9443, "https://10.0.0.5:9443"),
        ("https", "2001:db8::10", 9443, "https://[2001:db8::10]:9443"),
    ],
)
def test_build_prometheus_url(protocol, hostname, port, expected):
    assert build_prometheus_url(protocol, hostname, port) == expected


@pytest.mark.parametrize(
    ("protocol", "hostname", "port"),
    [
        ("ftp", "prometheus.internal", 9090),
        ("http", "", 9090),
        ("http", "https://prometheus.internal", 9090),
        ("http", "prometheus.internal/path", 9090),
        ("http", "prometheus.internal", 70000),
    ],
)
def test_build_prometheus_url_rejects_invalid_fields(protocol, hostname, port):
    with pytest.raises(ValueError):
        build_prometheus_url(protocol, hostname, port)


def test_discovery_prefers_cluster_label_and_returns_multiple_clusters():
    from app.collectors.prometheus_discovery import IDENTIFICATION_METRICS

    fake = FakePrometheus({
        IDENTIFICATION_METRICS[0]: [
            sample({"cluster": "Site1"}),
            sample({"cluster": "Site2"}),
        ],
        IDENTIFICATION_METRICS[1]: [
            sample({"cluster": "Site1"}),
            sample({"cluster": "Site2"}),
        ],
    })
    result = discover_minio_clusters("http://prometheus:9090", client=fake)

    assert result["status"] == "success"
    assert result["cluster_count"] == 2
    assert result["selection_required"] is True
    assert [item["label_value"] for item in result["clusters"]] == ["Site1", "Site2"]
    assert all(item["label_name"] == "cluster" for item in result["clusters"])
    assert fake.closed is False



def test_discovery_prefers_cluster_label_when_other_identity_labels_exist():
    from app.collectors.prometheus_discovery import IDENTIFICATION_METRICS

    fake = FakePrometheus({
        IDENTIFICATION_METRICS[0]: [
            sample({"cluster": "Site1", "site": "Chennai", "environment": "LAB"}),
        ],
        IDENTIFICATION_METRICS[1]: [
            sample({"cluster": "Site1", "site": "Chennai", "environment": "LAB"}),
        ],
    })
    result = discover_minio_clusters("http://prometheus:9090", client=fake)

    assert result["identity_labels"] == ["cluster"]
    assert result["cluster_count"] == 1
    assert result["clusters"][0]["label_value"] == "Site1"


def test_discovery_uses_known_alternative_identity_labels():
    from app.collectors.prometheus_discovery import IDENTIFICATION_METRICS

    fake = FakePrometheus({
        IDENTIFICATION_METRICS[0]: [sample({"site": "Chennai"})],
        IDENTIFICATION_METRICS[1]: [],
    })
    result = discover_minio_clusters("http://prometheus:9090", client=fake)

    assert result["identity_labels"] == ["site"]
    assert result["clusters"][0]["label_value"] == "Chennai"
    assert result["selection_required"] is False


def test_discovery_fails_when_no_minio_identity_is_found():
    fake = FakePrometheus({})
    with pytest.raises(PrometheusError, match="discovery failed"):
        discover_minio_clusters("http://prometheus:9090", client=fake)


def test_discovery_reports_partial_metric_query_errors():
    from app.collectors.prometheus_discovery import IDENTIFICATION_METRICS

    fake = FakePrometheus({
        IDENTIFICATION_METRICS[0]: [sample({"cluster": "Site1"})],
        IDENTIFICATION_METRICS[1]: PrometheusError("query denied"),
    })
    result = discover_minio_clusters("http://prometheus:9090", client=fake)

    assert result["cluster_count"] == 1
    assert result["warnings"] == [f"{IDENTIFICATION_METRICS[1]}: query denied"]


def test_discovery_endpoint_requires_admin_and_is_read_only(client, admin_client, viewer_client, monkeypatch):
    from app.api import clusters as cluster_api
    from app.main import app

    def fake_discovery(base_url):
        assert base_url == "http://prometheus.internal:9090"
        return {
            "status": "success",
            "prometheus_url": base_url,
            "minio_metrics_found": True,
            "identity_labels": ["cluster"],
            "clusters": [{"label_name": "cluster", "label_value": "Site1"}],
            "cluster_count": 1,
            "selection_required": False,
            "warnings": [],
        }

    monkeypatch.setattr(cluster_api, "discover_minio_clusters", fake_discovery)
    with TestClient(app, base_url="https://testserver") as anonymous_client:
        assert anonymous_client.post("/api/clusters/discover", json={
            "hostname": "prometheus.internal"
        }).status_code == 401
    assert viewer_client.post("/api/clusters/discover", json={
        "hostname": "prometheus.internal"
    }).status_code == 403

    relogin = admin_client.post("/api/auth/login", json={
        "username": "admin-test", "password": "Admin-Test-Password-123!"
    })
    assert relogin.status_code == 200
    before = admin_client.get("/api/analytics/clusters").json()
    response = admin_client.post("/api/clusters/discover", json={
        "protocol": "http",
        "hostname": "prometheus.internal",
        "port": 9090,
    })
    assert response.status_code == 200
    assert response.json()["clusters"][0]["label_value"] == "Site1"
    after = admin_client.get("/api/analytics/clusters").json()
    assert after == before
