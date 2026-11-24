from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import stat
from pydantic import BaseModel,Field
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import FileResponse
from pathlib import Path
from scripts.backup_database import (
    DEFAULT_MINIMUM_BACKUPS, backup_database, backup_management_lock,
    inspect_backup_retention, verify_backup,
)
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
BACKUP_AUDIT_DIR = Path("/data/minio-analytics/logs")
BACKUP_AUDIT_FILE = BACKUP_AUDIT_DIR / "backup-cleanup-audit.jsonl"


class BackupCleanupPreviewRequest(BaseModel):
    retention_days: int = Field(default=14, ge=1, le=365)
    minimum_keep: int = Field(default=DEFAULT_MINIMUM_BACKUPS, ge=1, le=100)


class BackupCleanupRequest(BackupCleanupPreviewRequest):
    current_password: str = Field(min_length=1, max_length=1024)
    preview_token: str = Field(min_length=64, max_length=64)


def _append_backup_audit(record: dict) -> None:
    BACKUP_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    if BACKUP_AUDIT_DIR.is_symlink() or BACKUP_AUDIT_FILE.is_symlink():
        raise RuntimeError("Backup audit path must not contain symbolic links")
    payload = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(BACKUP_AUDIT_FILE, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _verify_master_admin_password(actor: dict, password: str) -> None:
    with transaction() as c:
        user = c.execute(
            "SELECT password_hash,is_active FROM users WHERE id=?", (actor["id"],)
        ).fetchone()
    if user is None or not user["is_active"] or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=403, detail="Password confirmation failed")


@router.get("/backups")
def list_backups(
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    actor: dict = Depends(require_master_admin),
):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if BACKUP_DIR.is_symlink():
        raise HTTPException(status_code=500, detail="Backup directory must not be a symbolic link")
    paths = []
    for path in BACKUP_DIR.glob("*.db"):
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISREG(metadata.st_mode) and not path.is_symlink():
            paths.append((path, metadata))
    paths.sort(key=lambda item: (item[1].st_mtime, item[0].name), reverse=True)
    page = paths[offset:offset + limit]
    items = []
    for path, metadata in page:
        verified, verification_error = verify_backup(path)
        items.append({
            "filename": path.name,
            "size_bytes": metadata.st_size,
            "created_at": datetime.fromtimestamp(metadata.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
            "integrity": "verified" if verified else "failed",
            "verification_error": verification_error,
            "download_url": f"/api/master-admin/backups/{path.name}/download",
        })
    return {
        "items": items,
        "count": len(paths),
        "total_count": len(paths),
        "limit": limit,
        "offset": offset,
    }


@router.post("/backups", status_code=201)
def create_backup(actor: dict = Depends(require_master_admin)):
    try:
        path = backup_database(BACKUP_DIR, retention_days=14, minimum_keep=DEFAULT_MINIMUM_BACKUPS)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Backup failed: {exc}") from exc
    stat_result = path.stat()
    return {
        "created": True,
        "filename": path.name,
        "size_bytes": stat_result.st_size,
        "integrity": "verified",
        "created_at": datetime.fromtimestamp(stat_result.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
        "download_url": f"/api/master-admin/backups/{path.name}/download",
    }


@router.post("/backups/cleanup/preview")
def preview_backup_cleanup(
    request: BackupCleanupPreviewRequest,
    actor: dict = Depends(require_master_admin),
):
    try:
        return inspect_backup_retention(BACKUP_DIR, request.retention_days, request.minimum_keep)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to inspect backup retention: {exc}") from exc


@router.post("/backups/cleanup")
def cleanup_backups(
    request: BackupCleanupRequest,
    actor: dict = Depends(require_master_admin),
):
    _verify_master_admin_password(actor, request.current_password)
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        with backup_management_lock(BACKUP_DIR):
            preview = inspect_backup_retention(BACKUP_DIR, request.retention_days, request.minimum_keep)
            candidates = preview["candidates"]
            if not hmac.compare_digest(preview["preview_token"], request.preview_token):
                raise HTTPException(status_code=409, detail="Backup inventory changed after preview. Refresh the cleanup preview before confirming.")
            _append_backup_audit({
                "timestamp": timestamp,
                "event": "backup_cleanup_started",
                "actor": actor["username"],
                "retention_days": request.retention_days,
                "minimum_keep": request.minimum_keep,
                "candidate_count": len(candidates),
                "candidate_size_bytes": sum(item["size_bytes"] for item in candidates),
                "candidate_filenames": [item["filename"] for item in candidates],
            })
            deleted = []
            for item in candidates:
                path = BACKUP_DIR / item["filename"]
                try:
                    metadata = path.lstat()
                except FileNotFoundError:
                    continue
                if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
                    continue
                path.unlink()
                deleted.append({"filename": path.name, "size_bytes": metadata.st_size})
            result = {
                "deleted": deleted,
                "deleted_count": len(deleted),
                "deleted_size_bytes": sum(item["size_bytes"] for item in deleted),
                "retention_days": request.retention_days,
                "minimum_keep": request.minimum_keep,
                "preserved": preview["preserved"],
                "unverified": preview["unverified"],
            }
            _append_backup_audit({
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "event": "backup_cleanup_completed",
                "actor": actor["username"],
                **result,
            })
            return result
    except HTTPException:
        raise
    except Exception as exc:
        try:
            _append_backup_audit({
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "event": "backup_cleanup_failed",
                "actor": actor["username"],
                "error": str(exc),
            })
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Backup cleanup failed: {exc}") from exc


@router.get("/backups/{filename}/download")
def download_backup(filename: str, actor: dict = Depends(require_master_admin)):
    if not filename.endswith(".db") or Path(filename).name != filename or any(ch in filename for ch in ("/", "\\")):
        raise HTTPException(status_code=400, detail="Invalid backup filename")
    path = BACKUP_DIR / filename
    if not path.is_file() or path.is_symlink():
        raise HTTPException(status_code=404, detail="Backup not found")
    return FileResponse(path, media_type="application/vnd.sqlite3", filename=filename)
