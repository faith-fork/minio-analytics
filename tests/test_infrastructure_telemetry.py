from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.database.database import transaction
from scripts.scheduler_tick import _cleanup_expired_telemetry


def test_node_performance_endpoint_accepts_supported_windows(viewer_client):
    response = viewer_client.get("/api/analytics/clusters/cluster-1/nodes/performance?hours=6")
    assert response.status_code == 200
    payload = response.json()
    assert payload["hours"] == 6
    assert payload["interval_minutes"] == 5
    assert payload["expected_samples"] == 72
    assert payload["sample_count"] == 0
    assert payload["nodes"] == []


def test_node_performance_endpoint_rejects_unsupported_window(viewer_client):
    response = viewer_client.get("/api/analytics/clusters/cluster-1/nodes/performance?hours=3")
    assert response.status_code == 422


def test_retention_cleanup_removes_expired_runs_and_cascades_samples(client):
    now = datetime.now(timezone.utc)
    expired = (now - timedelta(days=4)).isoformat(timespec="seconds").replace("+00:00", "Z")
    recent = (now - timedelta(hours=1)).isoformat(timespec="seconds").replace("+00:00", "Z")
    with transaction() as connection:
        for run_id, stamp in (("expired-run", expired), ("recent-run", recent)):
            connection.execute(
                """INSERT INTO node_health_runs
                   (run_id,cluster_id,snapshot_ts,collected_at,node_count,drive_count)
                   VALUES(?, 'cluster-1', ?, ?, 1, 0)""",
                (run_id, stamp, stamp),
            )
            connection.execute(
                """INSERT INTO node_health_metrics
                   (run_id,cluster_id,node_name,node_exporter_up,minio_scrape_up)
                   VALUES(?, 'cluster-1', 'node-1', 1, 1)""",
                (run_id,),
            )

    result = _cleanup_expired_telemetry(3)
    assert result[0]["deleted_runs"] == 1

    with transaction() as connection:
        runs = connection.execute("SELECT run_id FROM node_health_runs ORDER BY run_id").fetchall()
        metrics = connection.execute("SELECT run_id FROM node_health_metrics ORDER BY run_id").fetchall()
    assert [row["run_id"] for row in runs] == ["recent-run"]
    assert [row["run_id"] for row in metrics] == ["recent-run"]
