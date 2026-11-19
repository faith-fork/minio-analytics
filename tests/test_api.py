from __future__ import annotations

from fastapi.testclient import TestClient


def test_authentication_and_role_enforcement(
    client: TestClient, viewer_client: TestClient
) -> None:
    assert client.get("/api/tenants").status_code == 401
    assert viewer_client.get("/api/tenants").status_code == 200
    assert viewer_client.post(
        "/api/tenants", json={"name": "Blocked Tenant"}
    ).status_code == 403
    assert viewer_client.get("/api/auth/users").status_code == 403
    assert viewer_client.put(
        "/api/buckets/bulk-tenant",
        json={"bucket_ids": [1], "tenant_id": None},
    ).status_code == 403


def test_admin_can_create_user_reset_password_and_deactivate(
    admin_client: TestClient,
) -> None:
    created = admin_client.post(
        "/api/auth/users",
        json={
            "username": "new-viewer",
            "password": "Initial-Password-123!",
            "role": "viewer",
        },
    )
    assert created.status_code == 201
    user_id = created.json()["id"]

    duplicate = admin_client.post(
        "/api/auth/users",
        json={
            "username": "NEW-VIEWER",
            "password": "Initial-Password-123!",
            "role": "viewer",
        },
    )
    assert duplicate.status_code == 409

    reset = admin_client.post(
        f"/api/auth/users/{user_id}/reset-password",
        json={"password": "Changed-Password-456!"},
    )
    assert reset.status_code == 200

    login = admin_client.post(
        "/api/auth/login",
        json={"username": "new-viewer", "password": "Changed-Password-456!"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "viewer"

    # The previous login changed this client session to the new viewer.
    admin_login = admin_client.post(
        "/api/auth/login",
        json={"username": "admin-test", "password": "Admin-Test-Password-123!"},
    )
    assert admin_login.status_code == 200

    deactivate = admin_client.post(
        f"/api/auth/users/{user_id}/active", json={"is_active": False}
    )
    assert deactivate.status_code == 200
    assert admin_client.get("/api/auth/users").status_code == 200


def test_last_active_admin_cannot_be_demoted_or_deactivated(
    admin_client: TestClient,
) -> None:
    users = admin_client.get("/api/auth/users").json()["items"]
    admin_id = next(user["id"] for user in users if user["username"] == "admin-test")

    demote = admin_client.patch(
        f"/api/auth/users/{admin_id}", json={"role": "viewer"}
    )
    assert demote.status_code == 409

    deactivate = admin_client.post(
        f"/api/auth/users/{admin_id}/active", json={"is_active": False}
    )
    assert deactivate.status_code == 409


def test_bulk_assignment_is_atomic_and_audited(admin_client: TestClient) -> None:
    tenant = admin_client.post(
        "/api/tenants", json={"name": "Bulk Tenant"}
    )
    assert tenant.status_code == 201
    tenant_id = tenant.json()["id"]

    invalid = admin_client.put(
        "/api/buckets/bulk-tenant",
        json={"bucket_ids": [1, 999], "tenant_id": tenant_id},
    )
    assert invalid.status_code == 404
    buckets_after_failure = admin_client.get("/api/buckets").json()["items"]
    assert all(bucket["tenant_id"] is None for bucket in buckets_after_failure)

    assigned = admin_client.put(
        "/api/buckets/bulk-tenant",
        json={
            "bucket_ids": [1, 2],
            "tenant_id": tenant_id,
            "note": "Automated bulk assignment test",
        },
    )
    assert assigned.status_code == 200
    assert assigned.json()["changed_count"] == 2
    assert assigned.json()["unchanged_count"] == 0

    replay = admin_client.put(
        "/api/buckets/bulk-tenant",
        json={"bucket_ids": [1, 2], "tenant_id": tenant_id},
    )
    assert replay.status_code == 200
    assert replay.json()["changed_count"] == 0
    assert replay.json()["unchanged_count"] == 2

    for bucket_id in (1, 2):
        history = admin_client.get(
            f"/api/buckets/{bucket_id}/history"
        ).json()
        assert history["count"] == 1
        assert history["items"][0]["tenant_id"] == tenant_id
        assert history["items"][0]["changed_by"] == "admin-test"


def test_single_assignment_and_snapshot_attribution_are_separate(
    admin_client: TestClient,
) -> None:
    tenant = admin_client.post(
        "/api/tenants", json={"name": "Current Owner"}
    ).json()
    tenant_id = tenant["id"]

    assigned = admin_client.put(
        "/api/buckets/1/tenant",
        json={"tenant_id": tenant_id, "note": "Ownership change"},
    )
    assert assigned.status_code == 200

    summary = admin_client.get("/api/analytics/tenants").json()
    current_owner = next(
        item for item in summary["items"] if item["tenant_id"] == tenant_id
    )
    assert current_owner["bucket_count"] == 1
    assert current_owner["used_bytes"] == 100

    bucket_history = admin_client.get("/api/analytics/buckets/1").json()
    assert bucket_history["bucket"]["current_tenant_id"] == tenant_id
    assert bucket_history["series"][0]["tenant_id_at_snapshot"] is None


def test_viewer_can_read_analytics_but_not_manage_users(
    viewer_client: TestClient,
) -> None:
    assert viewer_client.get("/api/analytics/overview").status_code == 200
    assert viewer_client.get("/api/analytics/tenants").status_code == 200
    assert viewer_client.get("/api/auth/users").status_code == 403
