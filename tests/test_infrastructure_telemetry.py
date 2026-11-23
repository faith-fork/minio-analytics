from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.database.database import initialize_database, transaction
from scripts.scheduler_tick import _cleanup_expired_telemetry


def test_node_performance_endpoint_accepts_supported_windows(viewer_client):
    response = viewer_client.get("/api/analytics/clusters/cluster-1/nodes/performance?hours=6")
    assert response.status_code == 200
    payload = response.json()
    assert payload["hours"] == 6
    assert payload["interval_minutes"] == 5
    assert payload["expected_samples"] == 72
    assert payload["expected_intervals"] == 72
    assert payload["sample_count"] == 0
    assert payload["coverage_basis"] == "configured_interval_windows"
    assert payload["collection_run_coverage_pct"] == 0
    assert payload["nodes"] == []


def test_node_performance_endpoint_rejects_unsupported_window(viewer_client):
    response = viewer_client.get("/api/analytics/clusters/cluster-1/nodes/performance?hours=3")
    assert response.status_code == 422


def test_node_performance_coverage_uses_distinct_expected_intervals(viewer_client):
    stamp = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds").replace("+00:00", "Z")
    with transaction() as connection:
        connection.execute(
            """INSERT INTO node_health_runs
               (run_id,cluster_id,snapshot_ts,collected_at,node_count,drive_count)
               VALUES('partial-run','cluster-1',?,?,2,0)""",
            (stamp, stamp),
        )
        connection.execute(
            """INSERT INTO node_health_runs
               (run_id,cluster_id,snapshot_ts,collected_at,node_count,drive_count)
               VALUES('empty-run','cluster-1',?,?,2,0)""",
            (stamp, stamp),
        )
        # Only one of the two expected nodes has a row in the partial run;
        # the empty run must still count as an attempted collection run.
        connection.execute(
            """INSERT INTO node_health_metrics
               (run_id,cluster_id,node_name,node_exporter_up,minio_scrape_up,cpu_utilization_pct)
               VALUES('partial-run','cluster-1','node-1',1,1,25)"""
        )

    response = viewer_client.get("/api/analytics/clusters/cluster-1/nodes/performance?hours=2")
    assert response.status_code == 200
    payload = response.json()
    assert payload["sample_count"] == 2
    assert payload["coverage_basis"] == "configured_interval_windows"
    assert payload["covered_intervals"] == 1
    assert payload["missing_intervals"] == 23
    assert payload["collection_run_coverage_pct"] == pytest.approx(100 / 24)
    assert payload["observed_interval_minutes"] == 0
    assert payload["cadence_status"] == "faster_than_configured"
    assert len(payload["nodes"]) == 1
    assert payload["nodes"][0]["node_name"] == "node-1"


@pytest.mark.parametrize(
    ("existing_minutes", "expected_minutes"),
    [(None, "60"), ("5", "60"), ("15", "15")],
)
def test_legacy_collection_interval_migration_is_audited_and_versioned(
    client, existing_minutes, expected_minutes
):
    with transaction() as connection:
        connection.execute("DELETE FROM schema_version WHERE version=10")
        connection.execute(
            "UPDATE app_settings SET setting_value='2' WHERE setting_key='node_interval_hours'"
        )
        if existing_minutes is None:
            connection.execute(
                "DELETE FROM app_settings WHERE setting_key='node_interval_minutes'"
            )
        else:
            connection.execute(
                "UPDATE app_settings SET setting_value=? WHERE setting_key='node_interval_minutes'",
                (existing_minutes,),
            )

    initialize_database()

    with transaction() as connection:
        interval = connection.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key='node_interval_minutes'"
        ).fetchone()["setting_value"]
        version = connection.execute(
            "SELECT 1 FROM schema_version WHERE version=10"
        ).fetchone()
        audits = connection.execute(
            "SELECT old_value,new_value,changed_by FROM settings_audit WHERE setting_key='node_interval_minutes' AND changed_by='system-migration-v10'"
        ).fetchall()

    assert interval == expected_minutes
    assert version is not None
    if expected_minutes == "60":
        assert len(audits) == 1
        assert audits[0]["new_value"] == "60"
        assert audits[0]["changed_by"] == "system-migration-v10"
    else:
        assert audits == []


def test_retention_cleanup_removes_expired_runs_and_cascades_samples(client):
    now = datetime.now(timezone.utc)
    expired = (now - timedelta(days=4)).isoformat(timespec="seconds").replace("+00:00", "Z")
    recent = (now - timedelta(hours=1)).isoformat(timespec="seconds").replace("+00:00", "Z")
    with transaction() as connection:
        for run_id, stamp in (("expired-run", expired), ("recent-run", recent)):
            connection.execute(
                """INSERT INTO node_health_runs
                   (run_id,cluster_id,snapshot_ts,collected_at,node_count,drive_count)
                   VALUES(?, 'cluster-1', ?, ?, 1, 1)""",
                (run_id, stamp, stamp),
            )
            connection.execute(
                """INSERT INTO node_health_metrics
                   (run_id,cluster_id,node_name,node_exporter_up,minio_scrape_up)
                   VALUES(?, 'cluster-1', 'node-1', 1, 1)""",
                (run_id,),
            )
            connection.execute(
                """INSERT INTO drive_health_metrics
                   (run_id,cluster_id,node_name,server,drive_path)
                   VALUES(?, 'cluster-1', 'node-1', 'node-1:9000', '/mnt/disk1')""",
                (run_id,),
            )

    result = _cleanup_expired_telemetry(3)
    assert result[0]["deleted_runs"] == 1

    with transaction() as connection:
        runs = connection.execute("SELECT run_id FROM node_health_runs ORDER BY run_id").fetchall()
        metrics = connection.execute("SELECT run_id FROM node_health_metrics ORDER BY run_id").fetchall()
        drives = connection.execute("SELECT run_id FROM drive_health_metrics ORDER BY run_id").fetchall()
    assert [row["run_id"] for row in runs] == ["recent-run"]
    assert [row["run_id"] for row in metrics] == ["recent-run"]
    assert [row["run_id"] for row in drives] == ["recent-run"]



def test_node_performance_coverage_does_not_count_excess_runs_as_extra_coverage(
    viewer_client,
):
    now = datetime.now(timezone.utc)
    with transaction() as connection:
        connection.execute(
            "UPDATE app_settings SET setting_value='60' WHERE setting_key='node_interval_minutes'"
        )
        for index in range(24):
            stamp = (
                now - timedelta(hours=2) + timedelta(minutes=2.5 + index * 5)
            ).isoformat(timespec="seconds").replace("+00:00", "Z")
            connection.execute(
                """INSERT INTO node_health_runs
                   (run_id,cluster_id,snapshot_ts,collected_at,node_count,drive_count)
                   VALUES(?,?,?, ?,0,0)""",
                (f"five-minute-run-{index}", "cluster-1", stamp, stamp),
            )

    response = viewer_client.get(
        "/api/analytics/clusters/cluster-1/nodes/performance?hours=2"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["interval_minutes"] == 60
    assert payload["expected_samples"] == 2
    assert payload["sample_count"] == 24
    assert payload["covered_intervals"] == 2
    assert payload["missing_intervals"] == 0
    assert payload["excess_runs"] == 22
    assert payload["collection_run_coverage_pct"] == 100
    assert payload["interval_coverage_pct"] == 100
    assert payload["expected_intervals"] == 2
    assert payload["observed_interval_minutes"] == 5
    assert payload["cadence_adherence_pct"] == 0
    assert payload["cadence_status"] == "faster_than_configured"


def test_node_performance_cadence_reports_hourly_schedule_as_on_schedule(
    viewer_client,
):
    now = datetime.now(timezone.utc)
    with transaction() as connection:
        connection.execute(
            "UPDATE app_settings SET setting_value='60' WHERE setting_key='node_interval_minutes'"
        )
        for index, minutes_ago in enumerate((110, 50)):
            stamp = (now - timedelta(minutes=minutes_ago)).isoformat(
                timespec="seconds"
            ).replace("+00:00", "Z")
            connection.execute(
                """INSERT INTO node_health_runs
                   (run_id,cluster_id,snapshot_ts,collected_at,node_count,drive_count)
                   VALUES(?,?,?, ?,0,0)""",
                (f"hourly-run-{index}", "cluster-1", stamp, stamp),
            )

    response = viewer_client.get(
        "/api/analytics/clusters/cluster-1/nodes/performance?hours=2"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["sample_count"] == 2
    assert payload["covered_intervals"] == 2
    assert payload["collection_run_coverage_pct"] == 100
    assert payload["observed_interval_minutes"] == 60
    assert payload["cadence_adherence_pct"] == 100
    assert payload["cadence_status"] == "on_schedule"


def test_node_performance_coverage_reports_missing_expected_intervals(
    viewer_client,
):
    now = datetime.now(timezone.utc)
    with transaction() as connection:
        connection.execute(
            "UPDATE app_settings SET setting_value='60' WHERE setting_key='node_interval_minutes'"
        )
        stamp = (now - timedelta(minutes=110)).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
        connection.execute(
            """INSERT INTO node_health_runs
               (run_id,cluster_id,snapshot_ts,collected_at,node_count,drive_count)
               VALUES('single-hourly-run','cluster-1',?,?,0,0)""",
            (stamp, stamp),
        )

    response = viewer_client.get(
        "/api/analytics/clusters/cluster-1/nodes/performance?hours=2"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["expected_samples"] == 2
    assert payload["sample_count"] == 1
    assert payload["covered_intervals"] == 1
    assert payload["missing_intervals"] == 1
    assert len(payload["missing_interval_windows"]) == 1
    missing_window = payload["missing_interval_windows"][0]
    missing_start = datetime.fromisoformat(missing_window["start_ts"].replace("Z", "+00:00"))
    missing_end = datetime.fromisoformat(missing_window["end_ts"].replace("Z", "+00:00"))
    assert missing_end > missing_start
    assert (missing_end - missing_start).total_seconds() <= 60 * 60
    assert payload["missing_interval_windows_truncated"] == 0
    assert payload["collection_run_coverage_pct"] == 50
    assert payload["interval_coverage_pct"] == 50
    assert payload["cadence_status"] == "insufficient_history"


def test_node_performance_reports_collection_outcomes_and_hourly_reliability(
    viewer_client,
):
    now = datetime.now(timezone.utc)
    outcomes = (
        (115, "failed"),
        (65, "partial"),
        (5, "success"),
    )
    with transaction() as connection:
        for index, (minutes_ago, status) in enumerate(outcomes):
            stamp = (now - timedelta(minutes=minutes_ago)).isoformat(
                timespec="seconds"
            ).replace("+00:00", "Z")
            connection.execute(
                """INSERT INTO node_health_runs
                   (run_id,cluster_id,snapshot_ts,collected_at,node_count,drive_count,status)
                   VALUES(?,?,?, ?,0,0,?)""",
                (f"outcome-run-{index}", "cluster-1", stamp, stamp, status),
            )

    response = viewer_client.get(
        "/api/analytics/clusters/cluster-1/nodes/performance?hours=2"
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["sample_count"] == 3
    assert payload["run_status_counts"] == {
        "success": 1,
        "partial": 1,
        "failed": 1,
    }
    assert payload["interval_status_counts"] == {
        "success": 1,
        "partial": 1,
        "failed": 1,
        "missing": 21,
    }
    assert payload["successful_interval_pct"] == pytest.approx(100 / 24)
    assert len(payload["interval_statuses"]) == 24
    assert len(payload["reliability_trend"]) == 2
    assert sum(item["success_intervals"] for item in payload["reliability_trend"]) == 1
    assert sum(item["partial_intervals"] for item in payload["reliability_trend"]) == 1
    assert sum(item["failed_intervals"] for item in payload["reliability_trend"]) == 1
    assert sum(item["missing_intervals"] for item in payload["reliability_trend"]) == 21


def test_node_health_collection_persists_failed_cluster_outcome(
    monkeypatch, viewer_client
):
    from app.collectors import node_health
    from app.config.loader import ClusterConfig, LocationConfig

    def fail_collection(*args, **kwargs):
        raise RuntimeError("Prometheus unavailable")

    monkeypatch.setattr(node_health, "collect_topology_snapshot", fail_collection)
    location = LocationConfig(
        id="LOC1",
        name="Test Location",
        prometheus_url="http://prometheus.example:9090",
        clusters=(
            ClusterConfig(
                id="cluster-1",
                name="Test Cluster",
                prometheus_label_value="test-cluster",
            ),
        ),
    )
    snapshot = datetime.now(timezone.utc)

    results = node_health.collect_node_health([location], snapshot_ts=snapshot)

    assert results[0]["status"] == "failed"
    with transaction() as connection:
        row = connection.execute(
            """SELECT status,node_count,drive_count
               FROM node_health_runs WHERE run_id=?""",
            (results[0]["run_id"],),
        ).fetchone()
    assert row["status"] == "failed"
    assert row["node_count"] == 0
    assert row["drive_count"] == 0


def test_node_health_run_outcome_schema_is_versioned(viewer_client):
    with transaction() as connection:
        columns = {
            row["name"] for row in connection.execute(
                "PRAGMA table_info(node_health_runs)"
            )
        }
        version = connection.execute(
            "SELECT 1 FROM schema_version WHERE version=11"
        ).fetchone()

    assert {"status", "error_text"}.issubset(columns)
    assert version is not None



def test_node_health_outcome_migration_backfills_legacy_partial_runs(viewer_client):
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    with transaction() as connection:
        connection.execute(
            """INSERT INTO node_health_runs
               (run_id,cluster_id,snapshot_ts,collected_at,family_errors_json,status)
               VALUES('legacy-partial','cluster-1',?,?, '{"cpu":"timeout"}', 'success')""",
            (stamp, stamp),
        )
        connection.execute("DELETE FROM schema_version WHERE version=11")

    initialize_database()

    with transaction() as connection:
        row = connection.execute(
            "SELECT status FROM node_health_runs WHERE run_id='legacy-partial'"
        ).fetchone()
    assert row["status"] == "partial"


def test_performance_series_returns_raw_per_node_samples_and_filesystem_utilization(viewer_client):
    stamp = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    with transaction() as connection:
        connection.execute(
            """INSERT INTO node_health_runs
               (run_id,cluster_id,snapshot_ts,collected_at,node_count,drive_count)
               VALUES('series-run','cluster-1',?,?,2,1)""",
            (stamp, stamp),
        )
        for node, cpu, used in (("node-1", 25.0, 50.0), ("node-2", 75.0, 150.0)):
            connection.execute(
                """INSERT INTO node_health_metrics
                   (run_id,cluster_id,node_name,cpu_utilization_pct,
                    memory_total_bytes,memory_used_bytes,load1)
                   VALUES('series-run','cluster-1',?,?,?,?,?)""",
                (node, cpu, 200.0, used, cpu / 10),
            )
        connection.execute(
            """INSERT INTO drive_health_metrics
               (run_id,cluster_id,node_name,server,drive_path,mountpoint,
                filesystem_used_pct,total_bytes,used_bytes)
               VALUES('series-run','cluster-1','node-1','node-1:9000',
                      '/dev/sdb','/data',67.5,1000,700)"""
        )

    response = viewer_client.get(
        "/api/analytics/clusters/cluster-1/nodes/performance-series?hours=2"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["available_nodes"] == ["node-1", "node-2"]
    assert payload["sample_count"] == 2
    assert [row["node_name"] for row in payload["series"]] == ["node-1", "node-2"]
    assert payload["series"][0]["cpu_utilization_pct"] == 25.0
    assert payload["series"][0]["memory_used_pct"] == 25.0
    assert payload["statistics"]["node-1"]["cpu"]["average"] == 25.0
    assert payload["drive_series"][0]["filesystem_used_pct"] == 67.5
    assert payload["supported_metrics"] == [
        "cpu", "memory", "load", "filesystem_utilization"
    ]


def test_performance_series_supports_node_filter_and_custom_range(viewer_client):
    now = datetime.now(timezone.utc)
    stamp = (now - timedelta(minutes=1)).isoformat(timespec="seconds").replace("+00:00", "Z")
    start = (now - timedelta(hours=1)).isoformat(timespec="seconds").replace("+00:00", "Z")
    end = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    with transaction() as connection:
        connection.execute(
            """INSERT INTO node_health_runs
               (run_id,cluster_id,snapshot_ts,collected_at,node_count,drive_count)
               VALUES('filtered-series-run','cluster-1',?,?,2,0)""",
            (stamp, stamp),
        )
        for node in ("node-1", "node-2"):
            connection.execute(
                """INSERT INTO node_health_metrics
                   (run_id,cluster_id,node_name,cpu_utilization_pct)
                   VALUES('filtered-series-run','cluster-1',?,50)""",
                (node,),
            )

    response = viewer_client.get(
        "/api/analytics/clusters/cluster-1/nodes/performance-series",
        params=[("start_ts", start), ("end_ts", end), ("node_names", "node-2")],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_nodes"] == ["node-2"]
    assert [row["node_name"] for row in payload["series"]] == ["node-2"]
    assert payload["hours"] == 1.0


def test_performance_series_rejects_range_beyond_configured_retention(viewer_client):
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=4)).isoformat(timespec="seconds").replace("+00:00", "Z")
    end = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    response = viewer_client.get(
        "/api/analytics/clusters/cluster-1/nodes/performance-series",
        params={"start_ts": start, "end_ts": end},
    )
    assert response.status_code == 422
    assert "retention" in response.json()["detail"]


def test_performance_series_allows_ranges_longer_than_72_hours_within_retention(viewer_client):
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=4)).isoformat(timespec="seconds").replace("+00:00", "Z")
    end = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    with transaction() as connection:
        connection.execute(
            "UPDATE app_settings SET setting_value='5' WHERE setting_key='telemetry_retention_days'"
        )
    response = viewer_client.get(
        "/api/analytics/clusters/cluster-1/nodes/performance-series",
        params={"start_ts": start, "end_ts": end},
    )
    assert response.status_code == 200
    assert response.json()["retention_days"] == 5
    assert response.json()["hours"] == 96.0


def test_performance_series_accepts_72_hour_preset(viewer_client):
    response = viewer_client.get(
        "/api/analytics/clusters/cluster-1/nodes/performance-series?hours=72"
    )
    assert response.status_code == 200
    assert response.json()["hours"] == 72.0
