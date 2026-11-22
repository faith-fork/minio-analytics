from __future__ import annotations
from datetime import datetime, timezone
from pydantic import BaseModel,Field
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from scripts.backup_database import backup_database
from app.auth.dependencies import require_master_admin
from app.auth.security import verify_password
from app.database.database import database_path, transaction
router=APIRouter(prefix="/api/master-admin",tags=["master administration"])
class SettingsUpdate(BaseModel):
    current_password:str=Field(min_length=1,max_length=1024)
    node_interval_minutes:int|None=Field(default=None,ge=1,le=60)
    node_interval_hours:int|None=Field(default=None,ge=1,le=24)
    telemetry_retention_days:int|None=Field(default=None,ge=1,le=90)
    daily_collection_time:str=Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
@router.get("/settings")
def get_settings(actor:dict=Depends(require_master_admin)):
    with transaction() as c:
        rows=c.execute("SELECT setting_key,setting_value,updated_at FROM app_settings").fetchall()
        last=c.execute("SELECT MAX(changed_at) t FROM settings_audit").fetchone()["t"]
        run_count=c.execute("SELECT COUNT(*) FROM node_health_runs").fetchone()[0]
        node_samples=c.execute("SELECT COUNT(*) FROM node_health_metrics").fetchone()[0]
        drive_samples=c.execute("SELECT COUNT(*) FROM drive_health_metrics").fetchone()[0]
        cleanup=c.execute("SELECT last_completed_at,last_status,last_error FROM scheduler_state WHERE job_key='telemetry_retention'").fetchone()
    v={r["setting_key"]:r["setting_value"] for r in rows}
    db_path=database_path()
    db_size=db_path.stat().st_size if db_path.exists() else 0
    wal_path=Path(str(db_path)+"-wal")
    wal_size=wal_path.stat().st_size if wal_path.exists() else 0
    return {
        "settings":{"node_interval_minutes":int(v.get("node_interval_minutes","5")),"node_interval_hours":(int(v.get("node_interval_minutes","5"))//60 if int(v.get("node_interval_minutes","5")) % 60 == 0 else None),"telemetry_retention_days":int(v.get("telemetry_retention_days","3")),"daily_collection_time":v.get("daily_collection_time","00:15")},
        "telemetry_usage":{"collection_runs":run_count,"node_samples":node_samples,"drive_samples":drive_samples,"database_size_bytes":db_size,"wal_size_bytes":wal_size,"last_cleanup_at":cleanup["last_completed_at"] if cleanup else None,"last_cleanup_status":cleanup["last_status"] if cleanup else None,"last_cleanup_error":cleanup["last_error"] if cleanup else None},
        "last_change_at":last,"scheduler_refresh_seconds":60
    }
@router.put("/settings")
def update_settings(p:SettingsUpdate,actor:dict=Depends(require_master_admin)):
    with transaction() as c:
        u=c.execute("SELECT password_hash,is_active FROM users WHERE id=?",(actor["id"],)).fetchone()
        if u is None or not u["is_active"] or not verify_password(p.current_password,u["password_hash"]):
            raise HTTPException(status_code=403,detail="Password confirmation failed")
        interval_minutes=p.node_interval_minutes if p.node_interval_minutes is not None else (p.node_interval_hours*60 if p.node_interval_hours is not None else None)
        if interval_minutes is None:
            raise HTTPException(status_code=422,detail="node_interval_minutes or legacy node_interval_hours is required")
        if interval_minutes > 60:
            raise HTTPException(
                status_code=422,
                detail="Node telemetry collection interval cannot exceed 60 minutes; use node_interval_minutes",
            )
        updates={"node_interval_minutes":str(interval_minutes),"daily_collection_time":p.daily_collection_time}
        if p.telemetry_retention_days is not None:
            updates["telemetry_retention_days"]=str(p.telemetry_retention_days)
        for k,v in updates.items():
            old=c.execute("SELECT setting_value FROM app_settings WHERE setting_key=?",(k,)).fetchone()
            ov=old["setting_value"] if old else None
            if ov==v:continue
            c.execute("""INSERT INTO app_settings(setting_key,setting_value,updated_at,updated_by) VALUES(?,?,?,?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value,updated_at=excluded.updated_at,updated_by=excluded.updated_by""",(k,v,datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),actor["username"]))
            c.execute("INSERT INTO settings_audit(setting_key,old_value,new_value,changed_by) VALUES(?,?,?,?)",(k,ov,v,actor["username"]))
    return {"updated":True,"effective_within_seconds":60,"settings":updates}

BACKUP_DIR = Path("/data/minio-analytics/backups")

@router.get("/backups")
def list_backups(actor: dict = Depends(require_master_admin)):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for path in sorted(BACKUP_DIR.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_file() or path.is_symlink():
            continue
        stat = path.stat()
        items.append({
            "filename": path.name,
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
            "download_url": f"/api/master-admin/backups/{path.name}/download",
        })
    return {"items": items, "count": len(items)}

@router.post("/backups", status_code=201)
def create_backup(actor: dict = Depends(require_master_admin)):
    try:
        path = backup_database(BACKUP_DIR, retention_days=14)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Backup failed: {exc}") from exc
    stat = path.stat()
    return {
        "created": True,
        "filename": path.name,
        "size_bytes": stat.st_size,
        "integrity": "ok",
        "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
        "download_url": f"/api/master-admin/backups/{path.name}/download",
    }

@router.get("/backups/{filename}/download")
def download_backup(filename: str, actor: dict = Depends(require_master_admin)):
    if not filename.endswith(".db") or Path(filename).name != filename or any(ch in filename for ch in ("/", "\\")):
        raise HTTPException(status_code=400, detail="Invalid backup filename")
    path = BACKUP_DIR / filename
    if not path.is_file() or path.is_symlink():
        raise HTTPException(status_code=404, detail="Backup not found")
    return FileResponse(path, media_type="application/vnd.sqlite3", filename=filename)
