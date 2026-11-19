from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from app.database.database import transaction


def get_current_user(request: Request) -> dict:
    """Resolve the session user from SQLite on every authenticated request."""
    user_id = request.session.get("user_id")
    if not isinstance(user_id, int):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    with transaction() as connection:
        row = connection.execute(
            """
            SELECT id, username, role, is_active
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()

    if row is None or not row["is_active"]:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return dict(row)


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Require an authenticated administrator."""
    if user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required",
        )
    return user
