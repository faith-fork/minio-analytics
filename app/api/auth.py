from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth.dependencies import get_current_user
from app.auth.security import verify_password
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
