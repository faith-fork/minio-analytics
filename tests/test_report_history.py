from __future__ import annotations

from fastapi.testclient import TestClient

from app.database.database import transaction


def _cluster_day(day: str, raw_total=10000, raw_free=4000, usable_total=8000, usable_free=3000):
    snapshot_ts = f"{day}T00:00:00Z"
    with transaction() as connection:
        connection.execute(
            """INSERT INTO cluster_daily_metrics
               (snapshot_date,cluster_id,snapshot_ts,collected_at,raw_total_bytes,raw_free_bytes,
                usable_total_bytes,usable_free_bytes,metrics_available)
               VALUES (?,?,?,?,?,?,?,?,1)""",
            (day,"cluster-1",snapshot_ts,f"{day}T00:05:00Z",raw_total,raw_free,usable_total,usable_free),
        )


def test_history_endpoints_require_authentication(client: TestClient):
    for path in (
        "/api/analytics/capacity-report/history",
        "/api/analytics/bucket-usage-report/history",
        "/api/analytics/raw-capacity-report/history",
    ):
        assert client.get(path).status_code == 401


def test_historical_reports_validate_date_ranges(viewer_client: TestClient):
    for path in (
        "/api/analytics/capacity-report/history",
        "/api/analytics/bucket-usage-report/history",
        "/api/analytics/raw-capacity-report/history",
    ):
        assert viewer_client.get(path, params={"start_date":"2026-01-02","end_date":"2026-01-01"}).status_code == 422
        assert viewer_client.get(path, params={"start_date":"2026-01-01","end_date":"2035-01-01"}).status_code == 422


def test_provisioned_history_returns_complete_series_and_null_gaps(viewer_client: TestClient):
    _cluster_day("2026-01-01")
    _cluster_day("2026-01-03",raw_total=12000,raw_free=3000,usable_total=9000,usable_free=2500)
    data=viewer_client.get("/api/analytics/capacity-report/history",params={"start_date":"2026-01-01","end_date":"2026-01-03"}).json()
    assert [p["date"] for p in data["points"]]==["2026-01-01","2026-01-02","2026-01-03"]
    assert data["points"][0]["complete"] is True
    assert data["points"][0]["usable_used_bytes"]==5000
    assert data["points"][1]["complete"] is False
    assert data["points"][1]["usable_used_bytes"] is None
    assert data["points"][2]["installed_capacity_bytes"] is not None


def test_raw_capacity_history_withholds_incomplete_fleet_values(viewer_client: TestClient):
    _cluster_day("2026-01-01")
    with transaction() as connection:
        connection.execute("INSERT INTO clusters(id,location_id,name) VALUES('cluster-2','LOC1','Cluster 2')")
        connection.execute(
            """INSERT INTO cluster_daily_metrics
               (snapshot_date,cluster_id,snapshot_ts,collected_at,raw_total_bytes,raw_free_bytes,
                usable_total_bytes,usable_free_bytes,metrics_available)
               VALUES ('2026-01-01','cluster-2','2026-01-01T00:00:00Z','2026-01-01T00:05:00Z',5000,2000,4000,1000,1)"""
        )
    data=viewer_client.get("/api/analytics/raw-capacity-report/history",params={"start_date":"2026-01-01","end_date":"2026-01-01"}).json()
    point=data["points"][0]
    assert point["complete"] is True
    assert point["raw_total_bytes"]==15000
    assert point["raw_used_bytes"]==9000


def test_bucket_history_is_withheld_without_successful_collection_run(viewer_client: TestClient):
    data=viewer_client.get("/api/analytics/bucket-usage-report/history",params={"start_date":"2026-01-01","end_date":"2026-01-01"}).json()
    point=data["points"][0]
    assert point["used_bytes"] is None
    assert point["quota_bytes"] is None
    assert point["utilization_pct"] is None
    with transaction() as connection:
        connection.execute(
            """INSERT INTO collection_runs(run_id,snapshot_date,cluster_id,started_at,finished_at,status,metrics_collected)
               VALUES('run-1','2026-01-01','cluster-1','2026-01-01T00:00:00Z','2026-01-01T00:10:00Z','success',3)"""
        )
    data=viewer_client.get("/api/analytics/bucket-usage-report/history",params={"start_date":"2026-01-01","end_date":"2026-01-01"}).json()
    point=data["points"][0]
    assert point["used_bytes"]==600
    assert point["quota_bytes"]==3000
    assert point["utilization_pct"]==20
