from __future__ import annotations

from datetime import date, timedelta

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
                (date.fromisoformat(snapshot_date) - timedelta(days=1)).isoformat() + "T18:30:00Z",
                (date.fromisoformat(snapshot_date) - timedelta(days=1)).isoformat() + "T18:35:00Z",
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
    assert data["data_as_of"] == "2025-12-31T18:30:00Z"


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


def test_raw_capacity_report_calculates_day_over_day_change_and_30_day_trend(viewer_client: TestClient) -> None:
    for offset in range(5):
        day = date(2026, 1, 1) + timedelta(days=offset)
        _insert_raw_snapshot(snapshot_date=day.isoformat(), raw_total=10000, raw_free=9000 - offset * 10)
    item = viewer_client.get('/api/analytics/raw-capacity-report').json()['items'][0]
    assert item['change_vs_yesterday_bytes'] == pytest.approx(10)
    assert item['trend_growth_bytes_per_day'] == pytest.approx(10)
    assert item['projected_days_to_full'] == 896
    assert item['trend_sample_count'] == 5


def test_raw_capacity_report_change_is_unavailable_when_yesterdays_snapshot_is_missing(viewer_client: TestClient) -> None:
    _insert_raw_snapshot(snapshot_date='2026-01-01', raw_total=10000, raw_free=9000)
    _insert_raw_snapshot(snapshot_date='2026-01-03', raw_total=10000, raw_free=8980)
    item = viewer_client.get('/api/analytics/raw-capacity-report').json()['items'][0]
    assert item['change_vs_yesterday_bytes'] is None
    assert item['trend_sample_count'] == 2


def test_raw_capacity_report_does_not_project_when_used_is_declining(viewer_client: TestClient) -> None:
    for offset in range(4):
        day = date(2026, 1, 1) + timedelta(days=offset)
        _insert_raw_snapshot(snapshot_date=day.isoformat(), raw_total=10000, raw_free=9000 + offset * 10)
    item = viewer_client.get('/api/analytics/raw-capacity-report').json()['items'][0]
    assert item['trend_growth_bytes_per_day'] == pytest.approx(-10)
    assert item['projected_days_to_full'] is None
