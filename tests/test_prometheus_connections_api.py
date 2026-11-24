from __future__ import annotations

from fastapi.testclient import TestClient


def connection_payload() -> dict:
    return {
        "connection_id": "prometheus-lab",
        "location_id": "LAB2",
        "location_name": "Lab Two",
        "protocol": "http",
        "hostname": "prometheus.internal",
        "port": 9090,
        "verify_tls": True,
        "enabled": True,
        "clusters": [{
            "cluster_id": "cluster-lab-two",
            "cluster_name": "MinIO Lab Two",
            "identity_label_name": "cluster",
            "identity_label_value": "lab-two",
        }],
    }


def test_prometheus_connection_management_requires_master_admin(
    client: TestClient, viewer_client: TestClient
) -> None:
    assert client.get("/api/master-admin/prometheus-connections").status_code == 401
    assert viewer_client.get("/api/master-admin/prometheus-connections").status_code == 403


def test_master_admin_can_save_list_and_disable_prometheus_connection(
    admin_client: TestClient,
) -> None:
    response = admin_client.post(
        "/api/master-admin/prometheus-connections", json=connection_payload()
    )
    assert response.status_code == 201, response.text
    assert response.json()["saved"] is True
    assert response.json()["cluster_bindings"] == 1

    listed = admin_client.get("/api/master-admin/prometheus-connections")
    assert listed.status_code == 200
    item = listed.json()["items"][0]
    assert item["connection_id"] == "prometheus-lab"
    assert item["hostname"] == "prometheus.internal"
    assert item["port"] == 9090
    assert item["enabled"] is True
    assert item["clusters"][0]["identity_label_value"] == "lab-two"

    disabled = admin_client.patch(
        "/api/master-admin/prometheus-connections/prometheus-lab/enabled?enabled=false"
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert admin_client.get("/api/master-admin/prometheus-connections").json()["items"][0]["enabled"] is False


def test_prometheus_connection_test_uses_discovery_without_persisting(
    admin_client: TestClient, monkeypatch
) -> None:
    from app.api import prometheus_connections as api

    def fake_discovery(endpoint, *, verify_tls=True):
        assert endpoint == "http://prometheus.internal:9090"
        return {
            "status": "success",
            "prometheus_url": endpoint,
            "minio_metrics_found": True,
            "identity_labels": ["cluster"],
            "clusters": [{
                "label_name": "cluster",
                "label_value": "lab-two",
                "metrics_found": ["minio_cluster_capacity_raw_total_bytes"],
            }],
            "cluster_count": 1,
            "selection_required": False,
            "warnings": [],
        }

    monkeypatch.setattr(api, "discover_minio_clusters", fake_discovery)
    response = admin_client.post(
        "/api/master-admin/prometheus-connections/test",
        json={
            "protocol": "http",
            "hostname": "prometheus.internal",
            "port": 9090,
            "verify_tls": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["cluster_count"] == 1
    assert admin_client.get("/api/master-admin/prometheus-connections").json()["count"] == 0


def test_prometheus_connection_rejects_invalid_identifier(admin_client: TestClient) -> None:
    payload = connection_payload()
    payload["connection_id"] = "bad/id"
    response = admin_client.post(
        "/api/master-admin/prometheus-connections", json=payload
    )
    assert response.status_code == 422
