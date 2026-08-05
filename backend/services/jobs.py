import httpx

from backend import db


def run_job(job_id: int, work_fn, *args, **kwargs) -> None:
    """Executed in a FastAPI BackgroundTask: runs work_fn, updates the job row, and
    best-effort POSTs the outcome to the job's webhook_url (for n8n or other callers)."""
    db.update_job(job_id, status="running")
    job = db.get_job(job_id)
    webhook_url = job["webhook_url"] if job else None
    try:
        result = work_fn(*args, **kwargs)
        db.update_job(job_id, status="done", result=result)
        _notify_webhook(webhook_url, {"job_id": job_id, "status": "done", "result": result})
    except Exception as e:
        db.update_job(job_id, status="error", error=str(e))
        _notify_webhook(webhook_url, {"job_id": job_id, "status": "error", "error": str(e)})


def _notify_webhook(url: str | None, payload: dict) -> None:
    if not url:
        return
    try:
        httpx.post(url, json=payload, timeout=10)
    except Exception:
        pass
