from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from backend import db
from backend.config import MEDIA_ALLOWED_ROOTS

router = APIRouter(prefix="/api", tags=["library"])


@router.get("/media")
def get_media(path: str = Query(...)):
    resolved = Path(path).resolve()
    if not any(resolved.is_relative_to(root) for root in MEDIA_ALLOWED_ROOTS):
        raise HTTPException(403, "Access to this path is not allowed")
    if not resolved.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(resolved)


@router.get("/library/summary")
def library_summary():
    return {
        "songs": len(db.list_songs()),
        "stems": len(db.list_all_stems()),
        "videos": len(db.list_videos()),
        "lyrics": len(db.list_lyrics()),
        "mixes": len(db.list_mixes()),
        "instruments": len(db.list_instruments()),
    }
