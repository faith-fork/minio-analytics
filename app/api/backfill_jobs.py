from __future__ import annotations

from datetime import date
from pydantic import BaseModel, Field, model_validator
from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import require_master_admin
from app.services.backfill_jobs import create_job, get_job, list_jobs, transition_job

router = APIRouter(prefix="/api/master-admin/backfill-jobs", tags=["master administration"])


class BackfillJobInput(BaseModel):
    location_id: str = Field(min_length=1, max_length=128)
    cluster_id: str = Field(min_length=1, max_length=128)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_range(self):
        if self.end_date < self.start_date:
            raise ValueError("End date must be on or after start date")
        if (self.end_date - self.start_date).days >= 60:
            raise ValueError("A backfill job may cover at most 60 calendar days")
        return self


class JobAction(BaseModel):
    action: str = Field(pattern="^(pause|resume|cancel)$")


@router.get("")
def get_jobs(_: dict = Depends(require_master_admin)):
    items = list_jobs()
    return {"items": items, "count": len(items)}


@router.post("", status_code=201)
def start_job(payload: BackfillJobInput, actor: dict = Depends(require_master_admin)):
    try:
        item = create_job(location_id=payload.location_id, cluster_id=payload.cluster_id,
                          start_date=payload.start_date, end_date=payload.end_date,
                          requested_by=actor["username"])
        return {"job": item}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{job_id}")
def job_status(job_id: str, _: dict = Depends(require_master_admin)):
    item = get_job(job_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Backfill job not found")
    return {"job": item}


@router.post("/{job_id}/action")
def job_action(job_id: str, payload: JobAction, actor: dict = Depends(require_master_admin)):
    try:
        return {"job": transition_job(job_id, payload.action, actor["username"])}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
