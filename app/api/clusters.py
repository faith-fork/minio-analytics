from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import require_admin
from app.collectors.prometheus import PrometheusError
from app.collectors.prometheus_discovery import (
    build_prometheus_url,
    discover_minio_clusters,
)

router = APIRouter(prefix="/api/clusters", tags=["clusters"])


class PrometheusDiscoveryRequest(BaseModel):
    protocol: str = Field(default="http", min_length=4, max_length=5)
    hostname: str = Field(min_length=1, max_length=253)
    port: int = Field(default=9090, ge=1, le=65535)


@router.post("/discover")
def discover_cluster(
    payload: PrometheusDiscoveryRequest,
    _: dict = Depends(require_admin),
) -> dict:
    """Test a Prometheus endpoint and discover MinIO cluster identities.

    This endpoint is read-only: it never creates or updates SQLite records.
    """
    try:
        base_url = build_prometheus_url(
            payload.protocol, payload.hostname, payload.port
        )
        return discover_minio_clusters(base_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PrometheusError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
