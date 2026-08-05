import hashlib
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException

from backend import db
from backend.config import GENERATED_DIR
from backend.schemas import PairMixIn, TTSMixIn
from backend.services.audio_mix import (
    get_audio_duration_sec,
    get_or_create_instrumental,
    overlay_tts_on_instrumental,
    synthesize_tts,
)
from backend.services.jobs import run_job

router = APIRouter(prefix="/api/mixes", tags=["mixes"])


@router.post("/pair")
def pair_mix(payload: PairMixIn):
    instrumental = get_or_create_instrumental(payload.song_id)
    mix_id = db.add_mix(payload.lyrics_id, instrumental["id"], "paired", instrumental["file_path"])
    return {"mix_id": mix_id, "instrumental": dict(instrumental)}


def _do_tts_mix(
    lyrics_id: int,
    song_id: int,
    voice: str,
    engine: str,
    emotion: str,
    instrumental_start_sec: float,
    instrumental_gain_db: float,
    tts_gain_db: float,
) -> dict:
    lyrics = db.get_lyrics(lyrics_id)
    if not lyrics:
        raise ValueError(f"Lyrics {lyrics_id} not found")
    instrumental = get_or_create_instrumental(song_id)

    cached = db.find_tts_mix(
        lyrics_id, instrumental["id"], voice, engine, emotion,
        instrumental_start_sec, instrumental_gain_db, tts_gain_db,
    )
    if cached and cached["file_path"] and Path(cached["file_path"]).exists():
        return {"mix_id": cached["id"], "file_path": cached["file_path"], "cached": True}

    # Filename must vary with every mix param, not just lyrics_id+song_id -- previously a
    # different voice/emotion/gain combo for the same lyrics+song silently overwrote the
    # earlier mix's file on disk (while old `mixes` DB rows kept pointing at that now-changed
    # path), and it made param-aware caching impossible in the first place.
    params_key = f"{voice}|{engine}|{emotion}|{instrumental_start_sec}|{instrumental_gain_db}|{tts_gain_db}"
    params_hash = hashlib.sha1(params_key.encode()).hexdigest()[:10]
    tts_path = GENERATED_DIR / f"lyrics{lyrics_id}_tts_{params_hash}.mp3"
    synthesize_tts(lyrics["generated_text"], tts_path, voice=voice, engine=engine, emotion=emotion)
    mix_path = GENERATED_DIR / f"lyrics{lyrics_id}_song{song_id}_mix_{params_hash}.mp3"
    overlay_tts_on_instrumental(
        Path(instrumental["file_path"]),
        tts_path,
        mix_path,
        instrumental_gain_db=instrumental_gain_db,
        tts_gain_db=tts_gain_db,
        instrumental_start_sec=instrumental_start_sec,
    )
    mix_id = db.add_mix(
        lyrics_id, instrumental["id"], "tts_overlay", str(mix_path),
        voice=voice, engine=engine, emotion=emotion,
        instrumental_start_sec=instrumental_start_sec,
        instrumental_gain_db=instrumental_gain_db, tts_gain_db=tts_gain_db,
    )
    return {"mix_id": mix_id, "file_path": str(mix_path), "cached": False}


@router.post("/tts-overlay")
def tts_overlay(payload: TTSMixIn, background_tasks: BackgroundTasks):
    job_id = db.create_job("tts_overlay_mix", payload.model_dump(), payload.webhook_url)
    background_tasks.add_task(
        run_job,
        job_id,
        _do_tts_mix,
        payload.lyrics_id,
        payload.song_id,
        payload.voice,
        payload.engine,
        payload.emotion,
        payload.instrumental_start_sec,
        payload.instrumental_gain_db,
        payload.tts_gain_db,
    )
    return {"job_id": job_id}


@router.get("")
def list_mixes():
    return [dict(m) for m in db.list_mixes()]


@router.get("/instrumental-duration/{song_id}")
def instrumental_duration(song_id: int):
    """So the frontend can bound the 'start instrumental at' slider to the track's actual
    length."""
    try:
        instrumental = get_or_create_instrumental(song_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    duration = get_audio_duration_sec(Path(instrumental["file_path"]))
    return {"duration_sec": duration}
