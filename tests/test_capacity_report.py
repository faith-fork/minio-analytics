from __future__ import annotations

from fastapi.testclient import TestClient

import pytest

from app.database.database import transaction


def _insert_cluster_snapshot() -> None:
    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO cluster_daily_metrics (
                snapshot_date, cluster_id, snapshot_ts, collected_at,
                raw_total_bytes, raw_free_bytes,
                usable_total_bytes, usable_free_bytes, metrics_available
            ) VALUES (
                '2026-01-01', 'cluster-1',
                '2026-01-01T00:00:00Z', '2026-01-01T00:05:00Z',
                10000, 3000, 8000, 2500, 1
            )
            """
        )


def test_capacity_report_returns_approved_totals_and_cluster_breakdown(
    viewer_client: TestClient,
) -> None:
    _insert_cluster_snapshot()

    response = viewer_client.get("/api/analytics/capacity-report")

    assert response.status_code == 200
    data = response.json()
    assert data["generated_from"] == "sqlite"
    assert data["cluster_count"] == 1
    assert data["totals_bytes"] == {
        "installed_capacity_bytes": 10000,
        "cap_capacity_bytes": 8000,
        "used_cap_bytes": 5500,
        "provisioned_bytes": 3000,
        "used_bucket_bytes": 600,
        "free_capacity_bytes": 2500,
    }
    item = data["items"][0]
    assert item["cluster_id"] == "cluster-1"
    assert item["cluster_snapshot_date"] == "2026-01-01"
    assert item["bucket_snapshot_date"] == "2026-01-01"
    assert item["active_bucket_count"] == 3
    assert item["buckets_with_metrics"] == 3
    assert item["buckets_with_quota"] == 3
    assert item["buckets_with_usage"] == 3
    assert item["usage_pct"] == pytest.approx(55.0)
    assert item["provisioned_pct"] == pytest.approx(30.0)
    assert data["avg_used_pct"] == pytest.approx(55.0)


def test_capacity_report_withholds_only_incomplete_bucket_metric_totals(
    viewer_client: TestClient,
) -> None:
    _insert_cluster_snapshot()
    with transaction() as connection:
        connection.execute(
            "UPDATE bucket_daily_metrics SET quota_bytes = NULL WHERE bucket_id = 3"
        )

    response = viewer_client.get("/api/analytics/capacity-report")
    assert response.status_code == 200
    totals = response.json()["totals_bytes"]
    assert totals["provisioned_bytes"] is None
    assert totals["used_bucket_bytes"] == 600

    with transaction() as connection:
        connection.execute(
            "UPDATE bucket_daily_metrics SET used_bytes = NULL WHERE bucket_id = 2"
        )

    response = viewer_client.get("/api/analytics/capacity-report")
    totals = response.json()["totals_bytes"]
    assert totals["provisioned_bytes"] is None
    assert totals["used_bucket_bytes"] is None


def test_capacity_report_does_not_treat_missing_cluster_metrics_as_zero(
    viewer_client: TestClient,
) -> None:
    _insert_cluster_snapshot()
    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO clusters (id, location_id, name)
            VALUES ('cluster-2', 'LOC1', 'Cluster Without Snapshot')
            """
        )

    response = viewer_client.get("/api/analytics/capacity-report")
    assert response.status_code == 200
    data = response.json()
    assert data["cluster_count"] == 2
    assert data["totals_bytes"]["installed_capacity_bytes"] is None
    assert data["totals_bytes"]["cap_capacity_bytes"] is None
    assert data["totals_bytes"]["used_cap_bytes"] is None
    assert data["totals_bytes"]["free_capacity_bytes"] is None
    assert data["totals_bytes"]["provisioned_bytes"] == 3000
    assert data["totals_bytes"]["used_bucket_bytes"] == 600


def test_capacity_report_returns_zero_bucket_totals_for_empty_cluster(
    viewer_client: TestClient,
) -> None:
    with transaction() as connection:
        connection.execute("UPDATE buckets SET is_active = 0")

    response = viewer_client.get("/api/analytics/capacity-report")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["active_bucket_count"] == 0
    assert item["provisioned_bytes"] == 0
    assert item["used_bucket_bytes"] == 0


def test_capacity_report_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/analytics/capacity-report").status_code == 401
