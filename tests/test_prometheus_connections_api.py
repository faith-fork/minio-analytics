from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


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
    viewer_client: TestClient,
) -> None:
    with TestClient(app, base_url="https://testserver") as anonymous_client:
        assert anonymous_client.get("/api/master-admin/prometheus-connections").status_code == 401
    assert viewer_client.get("/api/master-admin/prometheus-connections").status_code == 403


def test_master_admin_can_save_list_and_disable_prometheus_connection(
    admin_client: TestClient, monkeypatch
) -> None:
    from app.api import prometheus_connections as api

    monkeypatch.setattr(api, "discover_minio_clusters", lambda endpoint, verify_tls=True: {
        "clusters": [{"label_name": "cluster", "label_value": "lab-two"}],
        "cluster_count": 1,
    })
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


def test_save_revalidates_selected_cluster_against_exact_endpoint(
    admin_client: TestClient, monkeypatch
) -> None:
    from app.api import prometheus_connections as api

    observed = {}

    def fake_discovery(endpoint, *, verify_tls=True):
        observed["endpoint"] = endpoint
        observed["verify_tls"] = verify_tls
        return {
            "clusters": [{"label_name": "cluster", "label_value": "different-cluster"}],
            "cluster_count": 1,
        }

    monkeypatch.setattr(api, "discover_minio_clusters", fake_discovery)
    payload = connection_payload()
    payload["hostname"] = "changed-prometheus.internal"
    payload["port"] = 9191

    response = admin_client.post(
        "/api/master-admin/prometheus-connections", json=payload
    )

    assert response.status_code == 409
    assert "not present on the endpoint being saved" in response.json()["detail"]
    assert observed == {
        "endpoint": "http://changed-prometheus.internal:9191",
        "verify_tls": True,
    }
    assert admin_client.get("/api/master-admin/prometheus-connections").json()["count"] == 0


def test_save_accepts_only_cluster_identities_returned_by_current_endpoint(
    admin_client: TestClient, monkeypatch
) -> None:
    from app.api import prometheus_connections as api

    monkeypatch.setattr(api, "discover_minio_clusters", lambda endpoint, verify_tls=True: {
        "clusters": [{"label_name": "cluster", "label_value": "lab-two"}],
        "cluster_count": 1,
    })
    response = admin_client.post(
        "/api/master-admin/prometheus-connections", json=connection_payload()
    )
    assert response.status_code == 201, response.text




def test_save_preserves_existing_cluster_name_and_refuses_binding_reassignment(
    admin_client: TestClient, monkeypatch
) -> None:
    from app.api import prometheus_connections as api
    from app.database.database import transaction

    monkeypatch.setattr(api, "discover_minio_clusters", lambda endpoint, verify_tls=True: {
        "clusters": [
            {"label_name": "cluster", "label_value": "lab-two"},
            {"label_name": "cluster", "label_value": "lab-three"},
        ],
        "cluster_count": 2,
    })
    first = connection_payload()
    created = admin_client.post("/api/master-admin/prometheus-connections", json=first)
    assert created.status_code == 201, created.text

    renamed = {**first, "cluster_name": "Renamed by stale client"}
    saved = admin_client.post("/api/master-admin/prometheus-connections", json=renamed)
    assert saved.status_code == 201, saved.text

    with transaction() as connection:
        cluster = connection.execute(
            "SELECT name FROM clusters WHERE id='cluster-lab-two'"
        ).fetchone()
        binding = connection.execute(
            "SELECT connection_id, identity_label_name, identity_label_value "
            "FROM cluster_prometheus_bindings WHERE cluster_id='cluster-lab-two'"
        ).fetchone()
    assert cluster["name"] == "MinIO Lab Two"
    assert tuple(binding) == ("prometheus-lab", "cluster", "lab-two")

    reassignment = {
        **first,
        "clusters": [{
            **first["clusters"][0],
            "identity_label_value": "lab-three",
            "cluster_name": "Another name",
        }],
    }
    rejected = admin_client.post(
        "/api/master-admin/prometheus-connections", json=reassignment
    )
    assert rejected.status_code == 409
    assert "already bound" in rejected.json()["detail"]

    with transaction() as connection:
        binding = connection.execute(
            "SELECT connection_id, identity_label_value FROM cluster_prometheus_bindings "
            "WHERE cluster_id='cluster-lab-two'"
        ).fetchone()
    assert tuple(binding) == ("prometheus-lab", "lab-two")


def test_prometheus_connection_rejects_invalid_identifier(admin_client: TestClient) -> None:
    payload = connection_payload()
    payload["connection_id"] = "bad/id"
    response = admin_client.post(
        "/api/master-admin/prometheus-connections", json=payload
    )
    assert response.status_code == 422
