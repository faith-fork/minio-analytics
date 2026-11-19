from __future__ import annotations
from datetime import datetime,timezone
from pydantic import BaseModel,Field
from fastapi import APIRouter,Depends,HTTPException
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
