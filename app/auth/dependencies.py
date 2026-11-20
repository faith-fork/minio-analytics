from __future__ import annotations
from fastapi import Depends, HTTPException, Request, status
from app.database.database import transaction

def get_current_user(request: Request) -> dict:
    user_id=request.session.get("user_id")
    if not isinstance(user_id,int):
        raise HTTPException(status_code=401,detail="Authentication required")
    with transaction() as c:
        row=c.execute("SELECT id,username,role,is_active,is_master_admin FROM users WHERE id=?",(user_id,)).fetchone()
    if row is None or not row["is_active"]:
        request.session.clear()
        raise HTTPException(status_code=401,detail="Authentication required")
    return dict(row)

def require_admin(user: dict=Depends(get_current_user)) -> dict:
    if user["role"]!="admin":
        raise HTTPException(status_code=403,detail="Administrator role required")
    return user

def require_master_admin(user: dict=Depends(get_current_user)) -> dict:
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403,detail="Master Admin privileges required")
    return user
