from fastapi.testclient import TestClient


def test_report_column_preferences_default_to_visible(admin_client: TestClient) -> None:
    response = admin_client.get("/api/analytics/report-column-preferences")
    assert response.status_code == 200
    assert response.json()["columns"] == {"used_usable": True, "used_bkt": True}


def test_report_column_preferences_can_be_updated_and_persisted(
    admin_client: TestClient,
) -> None:
    updated = admin_client.put(
        "/api/analytics/report-column-preferences",
        json={"used_usable": False, "used_bkt": True},
    )
    assert updated.status_code == 200
    assert updated.json()["columns"] == {"used_usable": False, "used_bkt": True}

    refreshed = admin_client.get("/api/analytics/report-column-preferences")
    assert refreshed.status_code == 200
    assert refreshed.json()["columns"] == {"used_usable": False, "used_bkt": True}


def test_report_column_preferences_are_isolated_per_user(
    admin_client: TestClient,
) -> None:
    admin_client.put(
        "/api/analytics/report-column-preferences",
        json={"used_usable": False, "used_bkt": False},
    )
    admin_client.post("/api/auth/logout")

    viewer_login = admin_client.post(
        "/api/auth/login",
        json={"username": "viewer-test", "password": "Viewer-Test-Password-123!"},
    )
    assert viewer_login.status_code == 200
    assert admin_client.get("/api/analytics/report-column-preferences").json()[
        "columns"
    ] == {"used_usable": True, "used_bkt": True}

    admin_client.put(
        "/api/analytics/report-column-preferences",
        json={"used_usable": True, "used_bkt": False},
    )
    admin_client.post("/api/auth/logout")
    admin_login = admin_client.post(
        "/api/auth/login",
        json={"username": "admin-test", "password": "Admin-Test-Password-123!"},
    )
    assert admin_login.status_code == 200
    assert admin_client.get("/api/analytics/report-column-preferences").json()[
        "columns"
    ] == {"used_usable": False, "used_bkt": False}


def test_report_column_preferences_require_authentication(client: TestClient) -> None:
    assert client.get("/api/analytics/report-column-preferences").status_code == 401
    assert client.put(
        "/api/analytics/report-column-preferences",
        json={"used_usable": False, "used_bkt": True},
    ).status_code == 401
