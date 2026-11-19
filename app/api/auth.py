from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request, status
from typing import Literal

from app.auth.dependencies import get_current_user, require_admin
from app.auth.security import hash_password, verify_password
from app.database.database import transaction

router = APIRouter(prefix="/api/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


def _public_user(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
    }


@router.post("/login")
def login(payload: LoginRequest, request: Request) -> dict:
    username = payload.username.strip().lower()
    with transaction() as connection:
        row = connection.execute(
            """
            SELECT id, username, password_hash, role, is_active
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()

    if (
        row is None
        or not row["is_active"]
        or not verify_password(payload.password, row["password_hash"])
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    request.session.clear()
    request.session["user_id"] = row["id"]
    return {"authenticated": True, "user": _public_user(row)}


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"authenticated": False}


@router.get("/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    return {"authenticated": True, "user": {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
    }}


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=12, max_length=1024)
    role: Literal["admin", "viewer"] = "viewer"


class UpdateUserRequest(BaseModel):
    role: Literal["admin", "viewer"]


class ResetPasswordRequest(BaseModel):
    password: str = Field(min_length=12, max_length=1024)


@router.get("/users")
def list_users(_: dict = Depends(require_admin)) -> dict:
    with transaction() as connection:
        rows = connection.execute(
            """
            SELECT id, username, role, is_active, created_at, updated_at
            FROM users ORDER BY username COLLATE NOCASE
            """
        ).fetchall()
    return {"items": [dict(row) for row in rows], "count": len(rows)}


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(payload: CreateUserRequest, _: dict = Depends(require_admin)) -> dict:
    username = payload.username.strip()
    if len(username) < 3:
        raise HTTPException(status_code=422, detail="Username must contain at least 3 characters")
    password_hash = hash_password(payload.password)
    with transaction() as connection:
        try:
            cursor = connection.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, password_hash, payload.role),
            )
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise HTTPException(status_code=409, detail="Username already exists") from exc
            raise
        row = connection.execute(
            "SELECT id, username, role, is_active, created_at FROM users WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return dict(row)


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    payload: UpdateUserRequest,
    actor: dict = Depends(require_admin),
) -> dict:
    with transaction() as connection:
        target = connection.execute(
            "SELECT id, username, role, is_active FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        if target["role"] == "admin" and payload.role != "admin" and target["is_active"]:
            admins = connection.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1"
            ).fetchone()[0]
            if admins <= 1:
                raise HTTPException(status_code=409, detail="Cannot demote the last active administrator")
        connection.execute(
            "UPDATE users SET role = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            (payload.role, user_id),
        )
    return {"id": user_id, "role": payload.role}


@router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    payload: ResetPasswordRequest,
    _: dict = Depends(require_admin),
) -> dict:
    password_hash = hash_password(payload.password)
    with transaction() as connection:
        cursor = connection.execute(
            "UPDATE users SET password_hash = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            (password_hash, user_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
    return {"id": user_id, "password_reset": True}


@router.post("/users/{user_id}/active")
def set_user_active(
    user_id: int,
    payload: dict,
    actor: dict = Depends(require_admin),
) -> dict:
    active = payload.get("is_active")
    if not isinstance(active, bool):
        raise HTTPException(status_code=422, detail="is_active must be true or false")
    if user_id == actor["id"] and not active:
        raise HTTPException(status_code=409, detail="You cannot deactivate your own account")
    with transaction() as connection:
        target = connection.execute(
            "SELECT id, role, is_active FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        if target["role"] == "admin" and target["is_active"] and not active:
            admins = connection.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1"
            ).fetchone()[0]
            if admins <= 1:
                raise HTTPException(status_code=409, detail="Cannot deactivate the last active administrator")
        connection.execute(
            "UPDATE users SET is_active = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            (int(active), user_id),
        )
    return {"id": user_id, "is_active": active}
