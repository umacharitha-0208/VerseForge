import json
import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile

from backend import db
from backend.config import GENERATED_DIR, VIDEOS_DIR
from backend.schemas import VideoAnalyzeUrlIn
from backend.services.jobs import run_job
from backend.services.video_analysis import analyze_video, interpret_mood
from backend.services.url_download import download_video_from_url

router = APIRouter(prefix="/api/videos", tags=["videos"])


def _do_analyze(
    dest_path: str, title: str, source_title: str | None = None, language: str | None = None
) -> dict:
    content_hash = db.hash_file(dest_path)
    # Skip the cache when a language override is given -- that's specifically for correcting a
    # bad auto-detect result, so it must always re-run rather than returning an old cached
    # (possibly wrong-language) analysis.
    cached_video = db.find_video_by_hash(content_hash) if not language else None
    if cached_video:
        analyses = db.list_analyses_for_video(cached_video["id"])
        if analyses:
            a = analyses[0]
            return {
                "video_id": cached_video["id"],
                "transcript": a["transcript"],
                "formatted_lyrics": a["formatted_lyrics"],
                "singer": a["singer"],
                "genre": a["genre"],
                "music_features": json.loads(a["music_features_json"]),
                "mood_hint": interpret_mood(json.loads(a["music_features_json"])),
                "semantic_summary": a["semantic_summary"],
                "refine_iterations": json.loads(a["refine_iterations_json"]) if a["refine_iterations_json"] else [],
                "cached": True,
            }

    audio_out = GENERATED_DIR / f"{Path(dest_path).stem}_audio.wav"
    result = analyze_video(Path(dest_path), audio_out, source_title=source_title, language=language or None)
    video_id = db.add_video(title, Path(dest_path).name, dest_path, content_hash=content_hash)
    db.add_video_analysis(
        video_id,
        result["transcript"],
        result["music_features_json"],
        result["semantic_summary"],
        json.dumps(result["refine_iterations"]),
        result["formatted_lyrics"],
        result["singer"],
        result["genre"],
    )
    return {
        "video_id": video_id,
        "transcript": result["transcript"],
        "formatted_lyrics": result["formatted_lyrics"],
        "singer": result["singer"],
        "genre": result["genre"],
        "music_features": result["music_features"],
        "mood_hint": result["mood_hint"],
        "semantic_summary": result["semantic_summary"],
        "refine_iterations": result["refine_iterations"],
        "cached": False,
    }


@router.post("/analyze")
async def analyze(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(""),
    language: str = Form(""),
    webhook_url: str | None = Form(None),
):
    title_final = title.strip() or Path(file.filename).stem
    dest_path = VIDEOS_DIR / file.filename
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    job_id = db.create_job("analyze_video", {"filename": file.filename, "title": title_final}, webhook_url)
    background_tasks.add_task(
        run_job, job_id, _do_analyze, str(dest_path), title_final, None, language or None, heavy=True
    )
    return {"job_id": job_id}


def _do_download_and_analyze(url: str, title: str, language: str | None = None) -> dict:
    dest_path, yt_title = download_video_from_url(url)
    title_final = title or yt_title or dest_path.stem
    return _do_analyze(str(dest_path), title_final, source_title=yt_title, language=language)


@router.post("/analyze-url")
def analyze_url(payload: VideoAnalyzeUrlIn, background_tasks: BackgroundTasks):
    """Accepts a YouTube link or any URL yt-dlp supports (hundreds of sites), downloads it,
    then runs it through the same analysis pipeline as an uploaded file."""
    title_final = payload.title.strip()
    job_id = db.create_job("analyze_video_url", {"url": payload.url, "title": title_final}, payload.webhook_url)
    background_tasks.add_task(
        run_job, job_id, _do_download_and_analyze, payload.url, title_final, payload.language or None, heavy=True
    )
    return {"job_id": job_id}


@router.get("")
def list_videos():
    return [dict(v) for v in db.list_videos()]


@router.get("/{video_id}/analyses")
def list_analyses(video_id: int):
    out = []
    for a in db.list_analyses_for_video(video_id):
        d = dict(a)
        try:
            d["mood_hint"] = interpret_mood(json.loads(d["music_features_json"]))
        except (json.JSONDecodeError, TypeError):
            d["mood_hint"] = None
        out.append(d)
    return out
