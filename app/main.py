from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException

from app.database.database import get_connection, initialize_database


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


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    try:
        with get_connection() as connection:
            connection.execute("SELECT 1").fetchone()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    return {"status": "ok", "database": "ok"}
