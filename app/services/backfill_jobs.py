from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from typing import Any

from app.database.database import initialize_database, transaction

ACTIVE = ("queued", "running", "paused")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def create_job(*, location_id: str, cluster_id: str, start_date: date, end_date: date,
               requested_by: str) -> dict[str, Any]:
    if (end_date - start_date).days < 0:
        raise ValueError("End date must be on or after start date")
    days = (end_date - start_date).days + 1
    if days > 60:
        raise ValueError("A backfill job may cover at most 60 calendar days")
    initialize_database()
    job_id = str(uuid.uuid4())
    with transaction() as c:
        target = c.execute(
            """SELECT c.id, c.name, c.location_id, l.name AS location_name,
                      cpb.connection_id, pc.enabled AS connection_enabled,
                      c.enabled AS cluster_enabled, l.enabled AS location_enabled
               FROM clusters c JOIN locations l ON l.id=c.location_id
               JOIN cluster_prometheus_bindings cpb ON cpb.cluster_id=c.id
               JOIN prometheus_connections pc ON pc.connection_id=cpb.connection_id
               WHERE c.id=? AND c.location_id=?""",
            (cluster_id, location_id),
        ).fetchone()
        if target is None:
            raise ValueError("Cluster is not bound to a configured Prometheus connection")
        if not target["connection_enabled"] or not target["cluster_enabled"] or not target["location_enabled"]:
            raise ValueError("Location, cluster and Prometheus connection must all be enabled")
        active = c.execute(
            """SELECT job_id FROM backfill_jobs
               WHERE cluster_id=? AND status IN ('queued','running','paused') LIMIT 1""",
            (cluster_id,),
        ).fetchone()
        if active:
            raise ValueError("This cluster already has an active backfill job")
        c.execute(
            """INSERT INTO backfill_jobs
               (job_id, location_id, cluster_id, start_date, end_date, next_date,
                status, total_days, requested_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)""",
            (job_id, location_id, cluster_id, start_date.isoformat(), end_date.isoformat(),
             start_date.isoformat(), days, requested_by, _now(), _now()),
        )
        c.execute(
            """INSERT INTO settings_audit(setting_key, old_value, new_value, changed_by)
               VALUES('historical_backfill', NULL, ?, ?)""",
            (json.dumps({"job_id": job_id, "cluster_id": cluster_id,
                         "start_date": start_date.isoformat(), "end_date": end_date.isoformat()}),
             requested_by),
        )
        row = c.execute("SELECT * FROM backfill_jobs WHERE job_id=?", (job_id,)).fetchone()
    return dict(row)


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    initialize_database()
    with transaction() as c:
        rows = c.execute(
            """SELECT j.*, l.name AS location_name, cl.name AS cluster_name
               FROM backfill_jobs j JOIN locations l ON l.id=j.location_id
               JOIN clusters cl ON cl.id=j.cluster_id
               ORDER BY j.created_at DESC LIMIT ?""", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def get_job(job_id: str) -> dict[str, Any] | None:
    initialize_database()
    with transaction() as c:
        row = c.execute(
            """SELECT j.*, l.name AS location_name, cl.name AS cluster_name
               FROM backfill_jobs j JOIN locations l ON l.id=j.location_id
               JOIN clusters cl ON cl.id=j.cluster_id WHERE j.job_id=?""", (job_id,)
        ).fetchone()
    return dict(row) if row else None


def transition_job(job_id: str, action: str, actor: str) -> dict[str, Any]:
    if action not in {"pause", "resume", "cancel", "retry"}:
        raise ValueError("Unsupported job action")
    initialize_database()
    with transaction() as c:
        row = c.execute("SELECT * FROM backfill_jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise LookupError("Backfill job not found")
        status = row["status"]
        if action == "pause" and status in {"queued", "running"}:
            new_status = "paused"
        elif action == "resume" and status in {"paused", "failed"}:
            new_status = "queued"
        elif action == "cancel" and status in {"queued", "running", "paused", "failed"}:
            new_status = "cancelled"
        elif action == "retry" and status == "completed" and row["failed_days"] > 0:
            failed = c.execute(
                "SELECT MIN(snapshot_date) AS first_failed FROM backfill_job_days WHERE job_id=? AND status='failed'",
                (job_id,),
            ).fetchone()["first_failed"]
            if failed is None:
                raise ValueError("No failed dates are available to retry")
            c.execute("DELETE FROM backfill_job_days WHERE job_id=? AND snapshot_date>=?", (job_id, failed))
            counts = c.execute(
                """SELECT COUNT(*) AS completed,
                          SUM(status='success') AS successful,
                          SUM(status='partial') AS partial
                   FROM backfill_job_days WHERE job_id=?""", (job_id,)
            ).fetchone()
            c.execute(
                """UPDATE backfill_jobs SET next_date=?, completed_days=?,
                   successful_days=?, partial_days=?, failed_days=0,
                   last_error=NULL, finished_at=NULL WHERE job_id=?""",
                (failed, counts["completed"], counts["successful"] or 0,
                 counts["partial"] or 0, job_id),
            )
            new_status = "queued"
        else:
            raise ValueError(f"Cannot {action} a job in {status} state")
        c.execute(
            """UPDATE backfill_jobs SET status=?, updated_at=?, last_error=NULL
               WHERE job_id=?""", (new_status, _now(), job_id)
        )
        c.execute(
            """INSERT INTO settings_audit(setting_key, old_value, new_value, changed_by)
               VALUES('historical_backfill_job', ?, ?, ?)""",
            (status, json.dumps({"job_id": job_id, "status": new_status}), actor),
        )
        updated = c.execute("SELECT * FROM backfill_jobs WHERE job_id=?", (job_id,)).fetchone()
    return dict(updated)
