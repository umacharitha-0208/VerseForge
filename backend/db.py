import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from backend.config import DB_PATH


def hash_file(path: str | Path) -> str:
    """sha256 of a file's bytes -- used to detect "is this the exact same audio/video I already
    processed" so expensive pipelines (Demucs/Whisper/Gemini) can be skipped on an identical
    repeat upload, the same way Lyrics Studio already skips the LLM on a repeat text input."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

SCHEMA = """
CREATE TABLE IF NOT EXISTS songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    duration_sec REAL,
    uploaded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    stem_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    uploaded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS video_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    transcript TEXT,
    music_features_json TEXT,
    semantic_summary TEXT,
    refine_iterations_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lyrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    input_text TEXT NOT NULL,
    style TEXT NOT NULL,
    output_language TEXT NOT NULL DEFAULT 'english',
    script TEXT NOT NULL DEFAULT 'native',
    generated_text TEXT NOT NULL,
    refine_iterations_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lyrics_chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lyrics_id INTEGER NOT NULL REFERENCES lyrics(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mixes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lyrics_id INTEGER NOT NULL REFERENCES lyrics(id) ON DELETE CASCADE,
    stem_id INTEGER NOT NULL REFERENCES stems(id) ON DELETE CASCADE,
    mode TEXT NOT NULL,
    file_path TEXT,
    voice TEXT,
    engine TEXT,
    emotion TEXT,
    instrumental_start_sec REAL,
    instrumental_gain_db REAL,
    tts_gain_db REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS instruments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    family TEXT NOT NULL DEFAULT 'generic',
    params_json TEXT NOT NULL,
    notes_dir TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    input_json TEXT,
    result_json TEXT,
    error TEXT,
    webhook_url TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Adds columns to tables that existed before that column was introduced. CREATE TABLE
    IF NOT EXISTS in SCHEMA only covers brand-new databases, not ones carried over from
    earlier in development."""
    migrations = [
        ("instruments", "family", "TEXT NOT NULL DEFAULT 'generic'"),
        ("lyrics", "refine_iterations_json", "TEXT"),
        ("lyrics", "output_language", "TEXT NOT NULL DEFAULT 'english'"),
        ("lyrics", "script", "TEXT NOT NULL DEFAULT 'native'"),
        ("video_analyses", "refine_iterations_json", "TEXT"),
        ("video_analyses", "formatted_lyrics", "TEXT"),
        ("video_analyses", "singer", "TEXT"),
        ("video_analyses", "genre", "TEXT"),
        ("songs", "content_hash", "TEXT"),
        ("songs", "stem_count", "TEXT"),
        ("videos", "content_hash", "TEXT"),
        ("mixes", "voice", "TEXT"),
        ("mixes", "engine", "TEXT"),
        ("mixes", "emotion", "TEXT"),
        ("mixes", "instrumental_start_sec", "REAL"),
        ("mixes", "instrumental_gain_db", "REAL"),
        ("mixes", "tts_gain_db", "REAL"),
    ]
    for table, column, ddl in migrations:
        cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


# --- songs / stems -----------------------------------------------------

def add_song(
    title: str,
    original_filename: str,
    file_path: str,
    duration_sec: float | None = None,
    content_hash: str | None = None,
    stem_count: str | None = None,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO songs (title, original_filename, file_path, duration_sec, content_hash,
               stem_count, uploaded_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (title, original_filename, file_path, duration_sec, content_hash, stem_count, _now()),
        )
        return cur.lastrowid


def find_song_by_hash(content_hash: str, stem_count: str):
    """A song already separated with this exact audio content + stem count -- lets the caller
    skip re-running Demucs entirely on a repeat upload/URL."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM songs WHERE content_hash = ? AND stem_count = ? ORDER BY uploaded_at DESC LIMIT 1",
            (content_hash, stem_count),
        ).fetchone()


def add_stem(song_id: int, stem_type: str, file_path: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO stems (song_id, stem_type, file_path, created_at) VALUES (?, ?, ?, ?)",
            (song_id, stem_type, file_path, _now()),
        )
        return cur.lastrowid


def get_song(song_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()


def list_songs():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM songs ORDER BY uploaded_at DESC").fetchall()


def list_stems_for_song(song_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM stems WHERE song_id = ? ORDER BY stem_type", (song_id,)
        ).fetchall()


def list_all_stems():
    with get_conn() as conn:
        return conn.execute(
            """SELECT stems.*, songs.title AS song_title
               FROM stems JOIN songs ON stems.song_id = songs.id
               ORDER BY stems.created_at DESC"""
        ).fetchall()


# --- videos / analyses ---------------------------------------------------

def add_video(title: str, original_filename: str, file_path: str, content_hash: str | None = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO videos (title, original_filename, file_path, content_hash, uploaded_at) VALUES (?, ?, ?, ?, ?)",
            (title, original_filename, file_path, content_hash, _now()),
        )
        return cur.lastrowid


def find_video_by_hash(content_hash: str):
    """A video with this exact content already analyzed at least once -- returns the video row
    so the caller can look up its most recent analysis and skip re-running extraction/
    transcription/Gemini entirely on a repeat upload/URL."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM videos WHERE content_hash = ? ORDER BY uploaded_at DESC LIMIT 1",
            (content_hash,),
        ).fetchone()


def add_video_analysis(
    video_id: int,
    transcript: str,
    music_features_json: str,
    semantic_summary: str,
    refine_iterations_json: str | None = None,
    formatted_lyrics: str | None = None,
    singer: str | None = None,
    genre: str | None = None,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO video_analyses
               (video_id, transcript, music_features_json, semantic_summary, refine_iterations_json,
                formatted_lyrics, singer, genre, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                video_id, transcript, music_features_json, semantic_summary, refine_iterations_json,
                formatted_lyrics, singer, genre, _now(),
            ),
        )
        return cur.lastrowid


def list_videos():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM videos ORDER BY uploaded_at DESC").fetchall()


def list_analyses_for_video(video_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM video_analyses WHERE video_id = ? ORDER BY created_at DESC", (video_id,)
        ).fetchall()


# --- lyrics / mixes -------------------------------------------------------

def add_lyrics(
    title: str,
    input_text: str,
    style: str,
    generated_text: str,
    output_language: str = "english",
    script: str = "native",
    refine_iterations_json: str | None = None,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO lyrics
               (title, input_text, style, output_language, script, generated_text, refine_iterations_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, input_text, style, output_language, script, generated_text, refine_iterations_json, _now()),
        )
        return cur.lastrowid


def get_lyrics(lyrics_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM lyrics WHERE id = ?", (lyrics_id,)).fetchone()


def find_lyrics_by_input(input_text: str, style: str, output_language: str = "english", script: str = "native"):
    """Most recent lyrics generated from this exact input_text + style + language + script, if
    any -- used to skip re-calling the LLM for a repeat request (e.g. re-testing the same
    prompt)."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM lyrics WHERE input_text = ? AND style = ? AND output_language = ? "
            "AND script = ? ORDER BY created_at DESC LIMIT 1",
            (input_text, style, output_language, script),
        ).fetchone()


def update_lyrics_text(lyrics_id: int, generated_text: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE lyrics SET generated_text = ? WHERE id = ?", (generated_text, lyrics_id))


def add_lyrics_chat_message(lyrics_id: int, role: str, content: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO lyrics_chat_messages (lyrics_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (lyrics_id, role, content, _now()),
        )
        return cur.lastrowid


def list_lyrics_chat_messages(lyrics_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM lyrics_chat_messages WHERE lyrics_id = ? ORDER BY created_at ASC", (lyrics_id,)
        ).fetchall()


def list_lyrics():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM lyrics ORDER BY created_at DESC").fetchall()


def get_stem(stem_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM stems WHERE id = ?", (stem_id,)).fetchone()


def add_mix(
    lyrics_id: int,
    stem_id: int,
    mode: str,
    file_path: str | None,
    voice: str | None = None,
    engine: str | None = None,
    emotion: str | None = None,
    instrumental_start_sec: float | None = None,
    instrumental_gain_db: float | None = None,
    tts_gain_db: float | None = None,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO mixes (lyrics_id, stem_id, mode, file_path, voice, engine, emotion,
               instrumental_start_sec, instrumental_gain_db, tts_gain_db, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lyrics_id, stem_id, mode, file_path, voice, engine, emotion,
                instrumental_start_sec, instrumental_gain_db, tts_gain_db, _now(),
            ),
        )
        return cur.lastrowid


def find_tts_mix(
    lyrics_id: int,
    stem_id: int,
    voice: str,
    engine: str,
    emotion: str,
    instrumental_start_sec: float,
    instrumental_gain_db: float,
    tts_gain_db: float,
):
    """A tts_overlay mix already produced with these EXACT lyrics/instrumental/voice/mix
    settings -- lets the caller skip re-synthesizing speech and re-mixing on a repeat request."""
    with get_conn() as conn:
        return conn.execute(
            """SELECT * FROM mixes WHERE lyrics_id = ? AND stem_id = ? AND mode = 'tts_overlay'
               AND voice = ? AND engine = ? AND emotion = ? AND instrumental_start_sec = ?
               AND instrumental_gain_db = ? AND tts_gain_db = ?
               ORDER BY created_at DESC LIMIT 1""",
            (lyrics_id, stem_id, voice, engine, emotion, instrumental_start_sec,
             instrumental_gain_db, tts_gain_db),
        ).fetchone()


def list_mixes():
    with get_conn() as conn:
        return conn.execute(
            """SELECT mixes.*, lyrics.title AS lyrics_title, stems.stem_type AS stem_type,
                      songs.title AS song_title
               FROM mixes
               JOIN lyrics ON mixes.lyrics_id = lyrics.id
               JOIN stems ON mixes.stem_id = stems.id
               JOIN songs ON stems.song_id = songs.id
               ORDER BY mixes.created_at DESC"""
        ).fetchall()


# --- instruments (Siren) ----------------------------------------------------

def add_instrument(title: str, description: str, family: str, params_json: str, notes_dir: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO instruments (title, description, family, params_json, notes_dir, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, description, family, params_json, notes_dir, _now()),
        )
        return cur.lastrowid


def update_instrument_notes_dir(instrument_id: int, notes_dir: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE instruments SET notes_dir = ? WHERE id = ?", (notes_dir, instrument_id))


def find_instrument_by_description(description: str, family: str):
    """An instrument already created from this exact description + family -- lets the caller
    skip re-calling the LLM and re-rendering all 60 notes on a repeat description."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM instruments WHERE description = ? AND family = ? ORDER BY created_at DESC LIMIT 1",
            (description, family),
        ).fetchone()


def get_instrument(instrument_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM instruments WHERE id = ?", (instrument_id,)).fetchone()


def list_instruments():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM instruments ORDER BY created_at DESC").fetchall()


# --- jobs ------------------------------------------------------------------

def create_job(job_type: str, input_data: dict, webhook_url: str | None = None) -> int:
    with get_conn() as conn:
        now = _now()
        cur = conn.execute(
            """INSERT INTO jobs (job_type, status, input_json, webhook_url, created_at, updated_at)
               VALUES (?, 'pending', ?, ?, ?, ?)""",
            (job_type, json.dumps(input_data), webhook_url, now, now),
        )
        return cur.lastrowid


def update_job(job_id: int, status: str, result: dict | None = None, error: str | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, result_json = ?, error = ?, updated_at = ? WHERE id = ?",
            (status, json.dumps(result) if result is not None else None, error, _now(), job_id),
        )


def get_job(job_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()


def list_jobs(limit: int = 50):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
