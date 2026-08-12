import os
import time
import urllib.parse

import requests

BASE_URL = os.environ.get("BACKEND_BASE_URL", "http://127.0.0.1:8000")


def _url(path: str) -> str:
    return f"{BASE_URL}{path}"


def get_status() -> dict:
    r = requests.get(_url("/api/status"), timeout=5)
    r.raise_for_status()
    return r.json()


# --- songs -----------------------------------------------------------------

def separate_song(file_bytes: bytes, filename: str, title: str, stem_count: str = "6") -> int:
    files = {"file": (filename, file_bytes)}
    data = {"title": title, "stem_count": stem_count}
    r = requests.post(_url("/api/songs/separate"), files=files, data=data)
    r.raise_for_status()
    return r.json()["job_id"]


def separate_song_url(url: str, title: str, stem_count: str = "6") -> int:
    r = requests.post(
        _url("/api/songs/separate-url"), json={"url": url, "title": title, "stem_count": stem_count}
    )
    r.raise_for_status()
    return r.json()["job_id"]


def list_songs() -> list:
    r = requests.get(_url("/api/songs"))
    r.raise_for_status()
    return r.json()


def list_stems(song_id: int) -> list:
    r = requests.get(_url(f"/api/songs/{song_id}/stems"))
    r.raise_for_status()
    return r.json()


def split_vocals(song_id: int) -> int:
    r = requests.post(_url(f"/api/songs/{song_id}/split-vocals"), json={})
    r.raise_for_status()
    return r.json()["job_id"]


# --- videos ------------------------------------------------------------------

def analyze_video(file_bytes: bytes, filename: str, title: str, language: str = "") -> int:
    files = {"file": (filename, file_bytes)}
    data = {"title": title, "language": language}
    r = requests.post(_url("/api/videos/analyze"), files=files, data=data)
    r.raise_for_status()
    return r.json()["job_id"]


def analyze_video_url(url: str, title: str, language: str = "") -> int:
    r = requests.post(_url("/api/videos/analyze-url"), json={"url": url, "title": title, "language": language})
    r.raise_for_status()
    return r.json()["job_id"]


def list_videos() -> list:
    r = requests.get(_url("/api/videos"))
    r.raise_for_status()
    return r.json()


def list_analyses(video_id: int) -> list:
    r = requests.get(_url(f"/api/videos/{video_id}/analyses"))
    r.raise_for_status()
    return r.json()


# --- lyrics --------------------------------------------------------------

def get_lyrics_options() -> dict:
    r = requests.get(_url("/api/lyrics/options"))
    r.raise_for_status()
    return r.json()


def generate_lyrics(
    input_text: str, style: str, title: str, output_language: str = "same_as_input", script: str = "native"
) -> int:
    r = requests.post(
        _url("/api/lyrics/generate"),
        json={
            "input_text": input_text,
            "style": style,
            "title": title,
            "output_language": output_language,
            "script": script,
        },
    )
    r.raise_for_status()
    return r.json()["job_id"]


def list_lyrics() -> list:
    r = requests.get(_url("/api/lyrics"))
    r.raise_for_status()
    return r.json()


def get_lyrics_chat(lyrics_id: int) -> list:
    r = requests.get(_url(f"/api/lyrics/{lyrics_id}/chat"))
    r.raise_for_status()
    return r.json()


def chat_edit_lyrics(lyrics_id: int, instruction: str) -> dict:
    r = requests.post(_url(f"/api/lyrics/{lyrics_id}/chat"), json={"instruction": instruction})
    r.raise_for_status()
    return r.json()


def update_lyrics_text(lyrics_id: int, generated_text: str) -> dict:
    r = requests.put(_url(f"/api/lyrics/{lyrics_id}/text"), json={"generated_text": generated_text})
    r.raise_for_status()
    return r.json()


# --- mixes -----------------------------------------------------------------

def pair_mix(lyrics_id: int, song_id: int) -> dict:
    r = requests.post(_url("/api/mixes/pair"), json={"lyrics_id": lyrics_id, "song_id": song_id})
    r.raise_for_status()
    return r.json()


def tts_overlay_mix(
    lyrics_id: int,
    song_id: int,
    voice: str,
    engine: str = "edge",
    emotion: str = "neutral",
    instrumental_start_sec: float = 0.0,
    instrumental_gain_db: float = -6.0,
    tts_gain_db: float = 0.0,
) -> int:
    r = requests.post(
        _url("/api/mixes/tts-overlay"),
        json={
            "lyrics_id": lyrics_id,
            "song_id": song_id,
            "voice": voice,
            "engine": engine,
            "emotion": emotion,
            "instrumental_start_sec": instrumental_start_sec,
            "instrumental_gain_db": instrumental_gain_db,
            "tts_gain_db": tts_gain_db,
        },
    )
    r.raise_for_status()
    return r.json()["job_id"]


def get_instrumental_duration(song_id: int) -> float:
    r = requests.get(_url(f"/api/mixes/instrumental-duration/{song_id}"))
    r.raise_for_status()
    return r.json()["duration_sec"]


def list_mixes() -> list:
    r = requests.get(_url("/api/mixes"))
    r.raise_for_status()
    return r.json()


# --- instruments (GuitarGPT) ---------------------------------------------------

def create_instrument(description: str, title: str, family: str = "generic") -> int:
    r = requests.post(
        _url("/api/instruments/create"),
        json={"description": description, "title": title, "family": family},
    )
    r.raise_for_status()
    return r.json()["job_id"]


def list_instruments() -> list:
    r = requests.get(_url("/api/instruments"))
    r.raise_for_status()
    return r.json()


def get_instrument_notes(instrument_id: int) -> dict:
    r = requests.get(_url(f"/api/instruments/{instrument_id}/notes"))
    r.raise_for_status()
    return r.json()


# --- jobs --------------------------------------------------------------------

def get_job(job_id: int) -> dict:
    r = requests.get(_url(f"/api/jobs/{job_id}"))
    r.raise_for_status()
    return r.json()


def wait_for_job(job_id: int, poll_interval: float = 1.5, timeout: float = 1800) -> dict:
    start = time.time()
    while True:
        job = get_job(job_id)
        if job["status"] in ("done", "error"):
            return job
        if time.time() - start > timeout:
            raise TimeoutError(f"Job {job_id} timed out waiting for completion")
        time.sleep(poll_interval)


# --- media ---------------------------------------------------------------

def media_url(path: str) -> str:
    return _url("/api/media") + "?path=" + urllib.parse.quote(path)


def library_summary() -> dict:
    r = requests.get(_url("/api/library/summary"))
    r.raise_for_status()
    return r.json()
