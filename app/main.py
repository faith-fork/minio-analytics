from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.api.auth import router as auth_router
from app.api.tenants import router as tenant_router
from app.database.database import get_connection, initialize_database


def _session_secret() -> str:
    secret = os.getenv("MINIO_ANALYTICS_SESSION_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError(
            "MINIO_ANALYTICS_SESSION_SECRET must be set to at least 32 characters"
        )
    return secret


def _cookie_secure() -> bool:
    value = os.getenv("MINIO_ANALYTICS_COOKIE_SECURE", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    initialize_database()
    yield


app = FastAPI(
    title="MinIO Multi-Tenant Analytics",
    description="Analytics API for multi-location MinIO environments.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret(),
    session_cookie="minio_analytics_session",
    max_age=8 * 60 * 60,
    same_site="lax",
    https_only=_cookie_secure(),
)

app.include_router(auth_router)
app.include_router(tenant_router)


@app.get("/health", tags=["health"])
@app.get("/healthz", tags=["health"])
def health() -> dict[str, str]:
    connection = get_connection()
    try:
        connection.execute("SELECT 1").fetchone()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    finally:
        connection.close()

    return {"status": "ok", "database": "ok"}
