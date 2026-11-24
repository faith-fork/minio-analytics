from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import app

from app.database.database import transaction
from app.services.backfill_jobs import create_job, transition_job


def _configure_prometheus():
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


def test_backfill_job_creation_and_duplicate_guard(client):
    _configure_prometheus()
    job = create_job(
        location_id="LOC1", cluster_id="cluster-1",
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 3),
        requested_by="admin-test",
    )
    assert job["status"] == "queued"
    assert job["total_days"] == 3
    assert job["next_date"] == "2026-01-01"
    with pytest.raises(ValueError, match="already has an active"):
        create_job(
            location_id="LOC1", cluster_id="cluster-1",
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 2),
            requested_by="admin-test",
        )


def test_backfill_job_rejects_disabled_connection(client):
    _configure_prometheus()
    with transaction() as connection:
        connection.execute("UPDATE prometheus_connections SET enabled=0 WHERE connection_id='prom-loc1'")
    with pytest.raises(ValueError, match="must all be enabled"):
        create_job(
            location_id="LOC1", cluster_id="cluster-1",
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 1),
            requested_by="admin-test",
        )


def test_master_admin_api_authorization_and_date_validation(admin_client):
    _configure_prometheus()
    payload = {
        "location_id": "LOC1", "cluster_id": "cluster-1",
        "start_date": "2026-01-01", "end_date": "2026-01-03",
    }
    with TestClient(app, base_url="https://testserver") as viewer_client:
        login = viewer_client.post(
            "/api/auth/login",
            json={"username": "viewer-test", "password": "Viewer-Test-Password-123!"},
        )
        assert login.status_code == 200
        assert viewer_client.get("/api/master-admin/backfill-jobs").status_code == 403
        response = admin_client.post("/api/master-admin/backfill-jobs", json=payload)
        assert response.status_code == 201
        job_id = response.json()["job"]["job_id"]
        assert admin_client.get(f"/api/master-admin/backfill-jobs/{job_id}").status_code == 200
        assert viewer_client.post(
            f"/api/master-admin/backfill-jobs/{job_id}/action",
            json={"action": "cancel"},
        ).status_code == 403
    too_long = {**payload, "end_date": "2026-03-02"}
    assert admin_client.post("/api/master-admin/backfill-jobs", json=too_long).status_code == 422


def test_pause_resume_cancel_and_retry_failed_dates(client):
    _configure_prometheus()
    job = create_job(
        location_id="LOC1", cluster_id="cluster-1",
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 3),
        requested_by="admin-test",
    )
    job_id = job["job_id"]
    assert transition_job(job_id, "pause", "admin-test")["status"] == "paused"
    assert transition_job(job_id, "resume", "admin-test")["status"] == "queued"
    assert transition_job(job_id, "cancel", "admin-test")["status"] == "cancelled"



def test_retry_rewinds_to_first_failed_day_and_preserves_earlier_days(client):
    _configure_prometheus()
    job = create_job(
        location_id="LOC1", cluster_id="cluster-1",
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 3),
        requested_by="admin-test",
    )
    job_id = job["job_id"]
    with transaction() as connection:
        connection.execute(
            """UPDATE backfill_jobs SET status='completed', completed_days=3,
               successful_days=1, partial_days=1, failed_days=1 WHERE job_id=?""",
            (job_id,),
        )
        connection.executemany(
            """INSERT INTO backfill_job_days(job_id,snapshot_date,status,completed_at)
               VALUES(?,?,?,'2026-01-04T00:00:00Z')""",
            [(job_id, "2026-01-01", "success"),
             (job_id, "2026-01-02", "failed"),
             (job_id, "2026-01-03", "partial")],
        )
    updated = transition_job(job_id, "retry", "admin-test")
    assert updated["status"] == "queued"
    assert updated["next_date"] == "2026-01-02"
    assert updated["completed_days"] == 1
    assert updated["successful_days"] == 1
    assert updated["failed_days"] == 0
    with transaction() as connection:
        rows = connection.execute(
            "SELECT snapshot_date FROM backfill_job_days WHERE job_id=? ORDER BY snapshot_date",
            (job_id,),
        ).fetchall()
    assert [row["snapshot_date"] for row in rows] == ["2026-01-01"]
