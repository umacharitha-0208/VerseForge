import threading

import httpx

from backend import db

# Demucs/Whisper/FluidSynth can each pull several hundred MB-to-GB into memory while running.
# On a shared, memory-constrained host (e.g. HF Spaces' free 16GB instance) two of these
# stacking at once from concurrent requests is a real OOM risk that would crash the whole
# Space for every user, not just fail one job. This serializes only the heavy ML job types
# (separation, video analysis, instrument creation) so at most one runs at a time -- cheap
# jobs (lyrics generation/chat, which just call the Gemini API with no big local model) are
# NOT gated by this, so they aren't stuck waiting behind an unrelated heavy job.
_heavy_job_lock = threading.Semaphore(1)


def run_job(job_id: int, work_fn, *args, heavy: bool = False, **kwargs) -> None:
    """Executed in a FastAPI BackgroundTask: runs work_fn, updates the job row, and
    best-effort POSTs the outcome to the job's webhook_url (for n8n or other callers).

    heavy=True serializes this job against other heavy jobs (see _heavy_job_lock above) --
    set it for anything that loads a big local ML model (Demucs, Whisper, FluidSynth)."""
    db.update_job(job_id, status="running")
    job = db.get_job(job_id)
    webhook_url = job["webhook_url"] if job else None
    try:
        if heavy:
            with _heavy_job_lock:
                result = work_fn(*args, **kwargs)
        else:
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
