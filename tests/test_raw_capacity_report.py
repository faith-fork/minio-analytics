from __future__ import annotations

from fastapi.testclient import TestClient

import pytest

from app.database.database import transaction


def _insert_raw_snapshot(
    cluster_id: str = "cluster-1",
    snapshot_date: str = "2026-01-01",
    raw_total: float = 10000,
    raw_free: float = 3000,
    metrics_available: int = 1,
) -> None:
    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO cluster_daily_metrics (
                snapshot_date, cluster_id, snapshot_ts, collected_at,
                raw_total_bytes, raw_free_bytes, usable_total_bytes,
                usable_free_bytes, nodes_online, nodes_offline,
                metrics_available
            ) VALUES (?, ?, ?, ?, ?, ?, 8000, 2500, 4, 0, ?)
            """,
            (
                snapshot_date, cluster_id,
                f"{snapshot_date}T00:00:00Z",
                f"{snapshot_date}T00:05:00Z",
                raw_total, raw_free, metrics_available,
            ),
        )


def test_raw_capacity_report_returns_latest_snapshot_and_fleet_totals(
    viewer_client: TestClient,
) -> None:
    _insert_raw_snapshot()
    response = viewer_client.get("/api/analytics/raw-capacity-report")

    assert response.status_code == 200
    data = response.json()
    assert data["generated_from"] == "sqlite"
    assert data["cluster_count"] == 1
    assert data["available_cluster_count"] == 1
    assert data["unavailable_cluster_count"] == 0
    assert data["complete_coverage"] is True
    assert data["totals_bytes"] == {
        "raw_total_bytes": 10000,
        "raw_free_bytes": 3000,
        "raw_used_bytes": 7000,
    }
    assert data["raw_used_pct"] == pytest.approx(70.0)
    item = data["items"][0]
    assert item["cluster_id"] == "cluster-1"
    assert item["snapshot_date"] == "2026-01-01"
    assert item["raw_used_bytes"] == 7000
    assert item["raw_used_pct"] == pytest.approx(70.0)
    assert item["nodes_online"] == 4
    assert item["status"] == "Available"
    assert data["data_as_of"] == "2026-01-01T00:00:00Z"


def test_raw_capacity_report_uses_latest_snapshot_per_cluster(
    viewer_client: TestClient,
) -> None:
    _insert_raw_snapshot()
    _insert_raw_snapshot(snapshot_date="2026-01-02", raw_total=12000, raw_free=2000)

    data = viewer_client.get("/api/analytics/raw-capacity-report").json()
    item = data["items"][0]
    assert item["snapshot_date"] == "2026-01-02"
    assert item["raw_total_bytes"] == 12000
    assert item["raw_free_bytes"] == 2000
    assert item["raw_used_bytes"] == 10000
    assert data["totals_bytes"]["raw_total_bytes"] == 12000
    assert data["raw_used_pct"] == pytest.approx(10000 / 12000 * 100)


def test_raw_capacity_report_withholds_fleet_totals_for_missing_cluster_metrics(
    viewer_client: TestClient,
) -> None:
    _insert_raw_snapshot()
    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO clusters (id, location_id, name)
            VALUES ('cluster-2', 'LOC1', 'Cluster Without Snapshot')
            """
        )

    data = viewer_client.get("/api/analytics/raw-capacity-report").json()
    assert data["cluster_count"] == 2
    assert data["available_cluster_count"] == 1
    assert data["unavailable_cluster_count"] == 1
    assert data["complete_coverage"] is False
    assert data["totals_bytes"] == {
        "raw_total_bytes": None,
        "raw_free_bytes": None,
        "raw_used_bytes": None,
    }
    assert data["raw_used_pct"] is None
    missing = next(item for item in data["items"] if item["cluster_id"] == "cluster-2")
    assert missing["raw_used_bytes"] is None
    assert missing["status"] == "Unavailable"


def test_raw_capacity_report_withholds_totals_when_raw_free_is_missing(
    viewer_client: TestClient,
) -> None:
    _insert_raw_snapshot()
    with transaction() as connection:
        connection.execute(
            "UPDATE cluster_daily_metrics SET raw_free_bytes = NULL"
        )

    data = viewer_client.get("/api/analytics/raw-capacity-report").json()
    assert data["complete_coverage"] is False
    assert data["totals_bytes"]["raw_total_bytes"] is None
    assert data["items"][0]["raw_used_bytes"] is None


def test_raw_capacity_report_excludes_disabled_clusters(
    viewer_client: TestClient,
) -> None:
    _insert_raw_snapshot()
    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO clusters (id, location_id, name, enabled)
            VALUES ('cluster-2', 'LOC1', 'Disabled Cluster', 0)
            """
        )

    data = viewer_client.get("/api/analytics/raw-capacity-report").json()
    assert data["cluster_count"] == 1
    assert [item["cluster_id"] for item in data["items"]] == ["cluster-1"]


def test_raw_capacity_report_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/analytics/raw-capacity-report").status_code == 401
