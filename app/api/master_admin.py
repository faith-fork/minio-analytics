from __future__ import annotations
from datetime import datetime,timezone
from pydantic import BaseModel,Field
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from datetime import datetime
from scripts.backup_database import backup_database
from app.auth.dependencies import require_master_admin
from app.auth.security import verify_password
from app.database.database import transaction
router=APIRouter(prefix="/api/master-admin",tags=["master administration"])
class SettingsUpdate(BaseModel):
    current_password:str=Field(min_length=1,max_length=1024)
    node_interval_hours:int=Field(ge=1,le=24)
    daily_collection_time:str=Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
@router.get("/settings")
def get_settings(actor:dict=Depends(require_master_admin)):
    with transaction() as c:
        rows=c.execute("SELECT setting_key,setting_value,updated_at FROM app_settings").fetchall()
        last=c.execute("SELECT MAX(changed_at) t FROM settings_audit").fetchone()["t"]
    v={r["setting_key"]:r["setting_value"] for r in rows}
    return {"settings":{"node_interval_hours":int(v.get("node_interval_hours","4")),"daily_collection_time":v.get("daily_collection_time","00:15")},"last_change_at":last,"scheduler_refresh_seconds":60}
@router.put("/settings")
def update_settings(p:SettingsUpdate,actor:dict=Depends(require_master_admin)):
    with transaction() as c:
        u=c.execute("SELECT password_hash,is_active FROM users WHERE id=?",(actor["id"],)).fetchone()
        if u is None or not u["is_active"] or not verify_password(p.current_password,u["password_hash"]):
            raise HTTPException(status_code=403,detail="Password confirmation failed")
        updates={"node_interval_hours":str(p.node_interval_hours),"daily_collection_time":p.daily_collection_time}
        for k,v in updates.items():
            old=c.execute("SELECT setting_value FROM app_settings WHERE setting_key=?",(k,)).fetchone()
            ov=old["setting_value"] if old else None
            if ov==v:continue
            c.execute("""INSERT INTO app_settings(setting_key,setting_value,updated_at,updated_by) VALUES(?,?,?,?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value,updated_at=excluded.updated_at,updated_by=excluded.updated_by""",(k,v,datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),actor["username"]))
            c.execute("INSERT INTO settings_audit(setting_key,old_value,new_value,changed_by) VALUES(?,?,?,?)",(k,ov,v,actor["username"]))
    return {"updated":True,"effective_within_seconds":60,"settings":updates}

BACKUP_DIR = Path("/data/minio-analytics/backups")

def _verify_actor_password(actor: dict, password: str) -> None:
    with transaction() as c:
        u = c.execute(
            "SELECT password_hash,is_active FROM users WHERE id=?",
            (actor["id"],),
        ).fetchone()
    if u is None or not u["is_active"] or not verify_password(password, u["password_hash"]):
        raise HTTPException(status_code=403, detail="Password confirmation failed")

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
    if not filename.endswith(".db") or Path(filename).name != filename or any(ch in filename for ch in ("/", "\\\\")):
        raise HTTPException(status_code=400, detail="Invalid backup filename")
    path = BACKUP_DIR / filename
    if not path.is_file() or path.is_symlink():
        raise HTTPException(status_code=404, detail="Backup not found")
    return FileResponse(path, media_type="application/vnd.sqlite3", filename=filename)
