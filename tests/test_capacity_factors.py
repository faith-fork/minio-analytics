from fastapi.testclient import TestClient
from app.database.database import transaction


def test_capacity_factors_default_and_persisted(admin_client: TestClient) -> None:
    with transaction() as connection:
        connection.execute(
            """INSERT INTO cluster_daily_metrics
               (snapshot_date, cluster_id, snapshot_ts, collected_at,
                raw_total_bytes, raw_free_bytes, usable_total_bytes,
                usable_free_bytes, metrics_available)
               VALUES ('2026-01-01', 'cluster-1', '2026-01-01T00:00:00Z',
                       '2026-01-01T00:05:00Z', 10000, 3000, 8000, 2500, 1)"""
        )
    data = admin_client.get("/api/analytics/capacity-report").json()
    assert data["capacity_factors"] == {"dp": 1.33, "rf": 0.85, "eff": 0.99}
    updated = admin_client.put("/api/analytics/capacity-factors", json={"dp": 1.5, "rf": 0.9, "eff": 0.98})
    assert updated.status_code == 200
    assert updated.json()["factors"] == {"dp": 1.5, "rf": 0.9, "eff": 0.98}
    report = admin_client.get("/api/analytics/capacity-report").json()
    assert report["totals_bytes"]["installed_capacity_bytes"] == 10000 * 0.98 * (0.9 / 1.5)


def test_capacity_factors_are_admin_only(admin_client: TestClient) -> None:
    admin_client.post("/api/auth/logout")
    login = admin_client.post("/api/auth/login", json={"username": "viewer-test", "password": "Viewer-Test-Password-123!"})
    assert login.status_code == 200
    assert admin_client.put("/api/analytics/capacity-factors", json={"dp": 1.33, "rf": 0.85, "eff": 0.99}).status_code == 403


def test_capacity_factors_validate_ranges(admin_client: TestClient) -> None:
    assert admin_client.put("/api/analytics/capacity-factors", json={"dp": 0, "rf": 0.85, "eff": 0.99}).status_code == 422
    assert admin_client.put("/api/analytics/capacity-factors", json={"dp": 1.33, "rf": 0.85, "eff": 1.01}).status_code == 422


def test_capacity_factor_changes_are_audited(admin_client: TestClient) -> None:
    admin_client.put("/api/analytics/capacity-factors", json={"dp": 1.4, "rf": 0.9, "eff": 0.97})
    with transaction() as connection:
        rows = connection.execute("SELECT setting_key, old_value, new_value, changed_by FROM settings_audit WHERE setting_key LIKE 'capacity_%' ORDER BY setting_key").fetchall()
    assert len(rows) == 3
    assert all(row["changed_by"] == "admin-test" for row in rows)
