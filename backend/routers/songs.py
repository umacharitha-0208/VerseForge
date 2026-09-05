import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend import db
from backend.config import (
    DEFAULT_STEM_COUNT,
    GENERATED_DIR,
    UPLOADS_DIR,
)
from backend.schemas import SongSeparateUrlIn
from backend.services.audio_mix import get_or_create_instrumental
from backend.services.jobs import run_job
from backend.services.separation import separate_song
from backend.services.url_download import download_audio_from_url
from backend.services.vocal_split import split_lead_background

router = APIRouter(prefix="/api/songs", tags=["songs"])

def _do_separate(dest_path: str, title: str, stem_count: str = DEFAULT_STEM_COUNT) -> dict:
    content_hash = db.hash_file(dest_path)
    cached_song = db.find_song_by_hash(content_hash, stem_count)
    if cached_song:
        existing_stems = db.list_stems_for_song(cached_song["id"])
        if existing_stems and all(Path(s["file_path"]).exists() for s in existing_stems):
            all_stems = {s["stem_type"]: s["file_path"] for s in existing_stems}
            return {"song_id": cached_song["id"], "stems": all_stems, "cached": True}

    stems = separate_song(Path(dest_path), stem_count=stem_count)
    song_id = db.add_song(title, Path(dest_path).name, dest_path, content_hash=content_hash, stem_count=stem_count)
    for stem_type, path in stems.items():
        db.add_stem(song_id, stem_type, str(path))
    # Also build the full combined background music track (every non-vocal stem summed into
    # one file) right away, rather than only lazily on first TTS-mix request -- so it shows up
    # alongside the individual instrument stems immediately after separation.
    instrumental = get_or_create_instrumental(song_id)
    all_stems = {**{k: str(v) for k, v in stems.items()}, "instrumental": instrumental["file_path"]}
    return {"song_id": song_id, "stems": all_stems, "cached": False}


@router.post("/separate")
async def separate(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(""),
    stem_count: str = Form(DEFAULT_STEM_COUNT),
    webhook_url: str | None = Form(None),
):
    title_final = title.strip() or Path(file.filename).stem
    dest_path = UPLOADS_DIR / file.filename
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    job_id = db.create_job(
        "separate_song", {"filename": file.filename, "title": title_final, "stem_count": stem_count}, webhook_url
    )
    background_tasks.add_task(run_job, job_id, _do_separate, str(dest_path), title_final, stem_count, heavy=True)
    return {"job_id": job_id}


def _do_download_and_separate(url: str, title: str, stem_count: str = DEFAULT_STEM_COUNT) -> dict:
    dest_path, yt_title = download_audio_from_url(url)
    title_final = title or yt_title or dest_path.stem
    return _do_separate(str(dest_path), title_final, stem_count)


@router.post("/separate-url")
def separate_url(payload: SongSeparateUrlIn, background_tasks: BackgroundTasks):
    """Accepts a YouTube link or any URL yt-dlp supports, downloads the audio, then runs it
    through the same separation pipeline as an uploaded file."""
    title_final = payload.title.strip()
    job_id = db.create_job(
        "separate_song_url",
        {"url": payload.url, "title": title_final, "stem_count": payload.stem_count},
        payload.webhook_url,
    )
    background_tasks.add_task(
        run_job, job_id, _do_download_and_separate, payload.url, title_final, payload.stem_count, heavy=True
    )
    return {"job_id": job_id}


class SplitVocalsIn(BaseModel):
    webhook_url: str | None = None


def _do_split_vocals(song_id: int) -> dict:
    stems = {s["stem_type"]: s for s in db.list_stems_for_song(song_id)}
    if "vocals" not in stems:
        raise ValueError(f"No 'vocals' stem found for song_id={song_id}. Separate the song first.")
    vocals_path = Path(stems["vocals"]["file_path"])
    out_dir = GENERATED_DIR / "vocal_splits" / str(song_id)
    result = split_lead_background(vocals_path, out_dir)
    lead_id = db.add_stem(song_id, "lead_vocals", str(result["lead_vocals"]))
    background_id = db.add_stem(song_id, "background_vocals", str(result["background_vocals"]))
    return {
        "song_id": song_id,
        "lead_vocals_stem_id": lead_id,
        "background_vocals_stem_id": background_id,
        "lead_vocals": str(result["lead_vocals"]),
        "background_vocals": str(result["background_vocals"]),
    }


@router.post("/{song_id}/split-vocals")
def split_vocals(song_id: int, payload: SplitVocalsIn, background_tasks: BackgroundTasks):
    """Splits the song's existing 'vocals' stem into an estimated lead vs. background vocal
    track (DSP heuristic -- see vocal_split.py for how and its limitations)."""
    job_id = db.create_job("split_vocals", {"song_id": song_id}, payload.webhook_url)
    background_tasks.add_task(run_job, job_id, _do_split_vocals, song_id)
    return {"job_id": job_id}


@router.get("")
def list_songs():
    return [dict(s) for s in db.list_songs()]


@router.get("/{song_id}/stems")
def list_stems(song_id: int):
    return [dict(s) for s in db.list_stems_for_song(song_id)]


@router.get("/{song_id}/instrumental")
def instrumental(song_id: int):
    try:
        stem = get_or_create_instrumental(song_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return dict(stem)
