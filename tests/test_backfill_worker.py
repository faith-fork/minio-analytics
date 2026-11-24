from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.database.database import transaction
from app.services.backfill_jobs import create_job
from scripts import backfill_worker


def _create_one_day_job():
    with transaction() as connection:
        connection.execute(
            """INSERT INTO prometheus_connections
               (connection_id, location_id, protocol, hostname, port, enabled)
               VALUES ('prom-loc1', 'LOC1', 'http', '10.20.30.40', 9090, 1)"""
        )
        connection.execute(
            """INSERT INTO cluster_prometheus_bindings
               (cluster_id, connection_id, identity_label_name, identity_label_value)
               VALUES ('cluster-1', 'prom-loc1', 'cluster', 'cluster-1')"""
        )
    return create_job(
        location_id="LOC1",
        cluster_id="cluster-1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        requested_by="admin-test",
    )


def _mock_location():
    cluster = SimpleNamespace(id="cluster-1")
    return [SimpleNamespace(id="LOC1", clusters=[cluster])]


def test_worker_processes_one_day_and_persists_completion_checkpoint(client, monkeypatch):
    job = _create_one_day_job()
    monkeypatch.setattr(backfill_worker, "load_database_locations", _mock_location)
    monkeypatch.setattr(
        backfill_worker,
        "_collect_day",
        lambda *args: {"status": "success", "errors": []},
    )

    result = backfill_worker.run_one_backfill_day()

    assert result == {
        "job_id": job["job_id"],
        "date": "2026-01-01",
        "day_status": "success",
        "completed_days": 1,
        "total_days": 1,
        "job_status": "completed",
    }
    with transaction() as connection:
        saved_job = connection.execute(
            "SELECT status, completed_days, successful_days, failed_days FROM backfill_jobs WHERE job_id=?",
            (job["job_id"],),
        ).fetchone()
        saved_day = connection.execute(
            "SELECT status FROM backfill_job_days WHERE job_id=? AND snapshot_date='2026-01-01'",
            (job["job_id"],),
        ).fetchone()
    assert tuple(saved_job) == ("completed", 1, 1, 0)
    assert saved_day["status"] == "success"


def test_worker_recovers_interrupted_running_job_after_scheduler_restart(client, monkeypatch):
    job = _create_one_day_job()
    with transaction() as connection:
        connection.execute(
            "UPDATE backfill_jobs SET status='running' WHERE job_id=?",
            (job["job_id"],),
        )
    monkeypatch.setattr(backfill_worker, "load_database_locations", _mock_location)
    monkeypatch.setattr(
        backfill_worker,
        "_collect_day",
        lambda *args: {"status": "success", "errors": []},
    )

    result = backfill_worker.run_one_backfill_day()

    assert result is not None
    assert result["job_status"] == "completed"
    with transaction() as connection:
        saved_job = connection.execute(
            "SELECT status, completed_days FROM backfill_jobs WHERE job_id=?",
            (job["job_id"],),
        ).fetchone()
    assert tuple(saved_job) == ("completed", 1)
