from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from app.database.database import initialize_database, transaction
from app.database.prometheus_config import load_database_locations
from scripts.backfill_history import _collect_day

LOG = logging.getLogger("minio_analytics.backfill_worker")


def run_one_backfill_day() -> dict[str, Any] | None:
    """Process at most one calendar day. The SQLite cursor is the durable checkpoint."""
    initialize_database()
    with transaction() as c:
        row = c.execute(
            """SELECT * FROM backfill_jobs WHERE status='queued'
               ORDER BY created_at LIMIT 1"""
        ).fetchone()
        if row is None:
            return None
        job = dict(row)
        c.execute(
            """UPDATE backfill_jobs SET status='running', started_at=COALESCE(started_at, ?),
               updated_at=? WHERE job_id=? AND status='queued'""",
            (job["created_at"], job["created_at"], job["job_id"]),
        )

    day = date.fromisoformat(job["next_date"])
    try:
        locations = load_database_locations()
        location = next((item for item in locations if item.id == job["location_id"]), None)
        if location is None:
            raise RuntimeError("Configured location is no longer available")
        cluster = next((item for item in location.clusters if item.id == job["cluster_id"]), None)
        if cluster is None:
            raise RuntimeError("Cluster is no longer bound to an enabled Prometheus connection")
        result = _collect_day(location, cluster, day, 2, False)
        error_text = "; ".join(result.get("errors", [])) or None
        status = result.get("status", "failed")
    except Exception as exc:
        LOG.exception("Backfill job %s failed on %s", job["job_id"], day)
        error_text = str(exc)
        status = "failed"

    next_day = day + timedelta(days=1)
    with transaction() as c:
        current = c.execute(
            "SELECT status, completed_days, total_days FROM backfill_jobs WHERE job_id=?",
            (job["job_id"],),
        ).fetchone()
        if current is None:
            return {"job_id": job["job_id"], "status": "missing"}
        if current["status"] == "cancelled":
            return {"job_id": job["job_id"], "status": "cancelled"}
        if current["status"] == "paused":
            return {"job_id": job["job_id"], "status": "paused"}
        c.execute(
            """INSERT INTO backfill_job_days(job_id, snapshot_date, status, error_text, completed_at)
               VALUES(?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))
               ON CONFLICT(job_id, snapshot_date) DO UPDATE SET
                 status=excluded.status, error_text=excluded.error_text,
                 completed_at=excluded.completed_at""",
            (job["job_id"], day.isoformat(), status, error_text),
        )
        completed = current["completed_days"] + 1
        finished = completed >= current["total_days"]
        c.execute(
            """UPDATE backfill_jobs SET next_date=?, completed_days=?,
               successful_days=successful_days+?, partial_days=partial_days+?,
               failed_days=failed_days+?, status=?, last_error=?, updated_at=?,
               finished_at=CASE WHEN ? THEN strftime('%Y-%m-%dT%H:%M:%fZ','now') ELSE finished_at END
               WHERE job_id=?""",
            (next_day.isoformat(), completed, int(status == "success"),
             int(status == "partial"), int(status == "failed"),
             "completed" if finished else "queued", error_text,
             __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
             int(finished), job["job_id"]),
        )
    return {"job_id": job["job_id"], "date": day.isoformat(), "day_status": status,
            "completed_days": completed, "total_days": current["total_days"],
            "job_status": "completed" if finished else "queued"}
