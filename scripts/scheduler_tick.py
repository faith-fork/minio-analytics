from __future__ import annotations
import os
import fcntl,json,logging
from datetime import datetime,time,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from app.collectors.node_health import collect_node_health
from app.collectors.orchestrator import collect_all
from app.database.prometheus_config import load_database_locations
from app.config.loader import load_locations
from app.database.database import initialize_database,transaction

IST=ZoneInfo("Asia/Kolkata")
LOCK=Path("/run/lock/minio-analytics-scheduler.lock")
LOG=logging.getLogger("minio_analytics.scheduler")

def _state(key):
    with transaction() as c:
        r=c.execute("SELECT last_completed_at FROM scheduler_state WHERE job_key=?",(key,)).fetchone()
    return r["last_completed_at"] if r else None

def _record_start(key,now):
    with transaction() as c:
        c.execute("""INSERT INTO scheduler_state(job_key,last_started_at,last_status,last_error) VALUES(?,?,'running',NULL)
        ON CONFLICT(job_key) DO UPDATE SET last_started_at=excluded.last_started_at,last_status='running',last_error=NULL""",(key,now))

def _record_finish(key,now,status,error=None):
    with transaction() as c:
        c.execute("""UPDATE scheduler_state SET last_completed_at=?,last_status=?,last_error=? WHERE job_key=?""",(now,status,error,key))

def _due_node(now,interval):
    last=_state("node_health")
    if not last:return True
    try: previous=datetime.fromisoformat(last.replace("Z","+00:00"))
    except ValueError:return True
    return (now-previous).total_seconds()>=interval*60

def _due_retention(now):
    last=_state("telemetry_retention")
    if not last:return True
    try:return datetime.fromisoformat(last.replace("Z","+00:00")).astimezone(IST).date()<now.astimezone(IST).date()
    except ValueError:return True

def _cleanup_expired_telemetry(retention_days):
    cutoff=(datetime.now(timezone.utc)-timedelta(days=retention_days)).isoformat(timespec="seconds").replace("+00:00","Z")
    with transaction() as c:
        result=c.execute("DELETE FROM node_health_runs WHERE snapshot_ts < ?",(cutoff,))
        deleted=result.rowcount
    LOG.info("Telemetry retention cleanup deleted %s expired node-health runs older than %s days",deleted,retention_days)
    return [{"deleted_runs":deleted,"retention_days":retention_days,"status":"success"}]

def _due_daily(now,scheduled):
    local=now.astimezone(IST)
    if local.timetz().replace(tzinfo=None)<scheduled:return False
    last=_state("daily_collection")
    if not last:return True
    try:return datetime.fromisoformat(last.replace("Z","+00:00")).astimezone(IST).date()<local.date()
    except ValueError:return True

def _run(key,fn,now):
    stamp=now.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
    _record_start(key,stamp)
    try:
        result=fn()
        errors=[x for x in result if x.get("error") or x.get("status") in ("failed","partial")]
        status="partial" if errors else "success"
        _record_finish(key,datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z"),status,json.dumps(errors) if errors else None)
        LOG.info("%s completed status=%s result=%s",key,status,result)
    except Exception as exc:
        _record_finish(key,datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z"),"failed",str(exc))
        LOG.exception("%s failed",key)

def _load_locations():
    source = os.getenv("MINIO_ANALYTICS_CONFIG_SOURCE", "database").strip().lower()
    if source == "database":
        return load_database_locations()
    if source == "yaml":
        return load_locations()
    raise ValueError(
        "MINIO_ANALYTICS_CONFIG_SOURCE must be 'database' or 'yaml'"
    )


def main():
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    initialize_database()
    LOCK.parent.mkdir(parents=True,exist_ok=True)
    with LOCK.open("w") as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            LOG.info("Previous scheduler tick still active; skipping")
            return 0
        with transaction() as c:
            values={r["setting_key"]:r["setting_value"] for r in c.execute("SELECT setting_key,setting_value FROM app_settings")}
        interval=int(values.get("node_interval_minutes","5"))
        retention_days=int(values.get("telemetry_retention_days","3"))
        hh,mm=values.get("daily_collection_time","00:15").split(":")
        daily_time=time(int(hh),int(mm))
        now=datetime.now(timezone.utc)
        locations=_load_locations()
        if _due_node(now,interval):
            _run("node_health",lambda:collect_node_health(locations,now),now)
        if _due_retention(now):
            _run("telemetry_retention",lambda:_cleanup_expired_telemetry(retention_days),now)
        if _due_daily(now,daily_time):
            from datetime import datetime as dt
            snapshot=dt.combine(now.astimezone(IST).date(),time.min,tzinfo=IST).astimezone(timezone.utc)
            _run("daily_collection",lambda:collect_all(locations,snapshot_ts=snapshot,max_attempts=2),now)
    return 0

if __name__=="__main__":raise SystemExit(main())
