import json

from fastapi import APIRouter, HTTPException

from backend import db
from backend.schemas import JobOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _job_to_out(job) -> JobOut:
    return JobOut(
        id=job["id"],
        job_type=job["job_type"],
        status=job["status"],
        result=json.loads(job["result_json"]) if job["result_json"] else None,
        error=job["error"],
        created_at=job["created_at"],
        updated_at=job["updated_at"],
    )


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_to_out(job)


@router.get("", response_model=list[JobOut])
def list_jobs(limit: int = 50):
    return [_job_to_out(j) for j in db.list_jobs(limit)]
