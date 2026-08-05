from pydantic import BaseModel

from backend.config import DEFAULT_STEM_COUNT


class JobOut(BaseModel):
    id: int
    job_type: str
    status: str
    result: dict | None = None
    error: str | None = None
    created_at: str
    updated_at: str


class LyricsGenerateIn(BaseModel):
    input_text: str
    style: str = "poetic free verse"
    title: str = ""
    output_language: str = "same_as_input"
    script: str = "native"  # "native" or "romanized"
    max_iterations: int | None = None
    score_threshold: int | None = None
    webhook_url: str | None = None


class LyricsChatIn(BaseModel):
    instruction: str


class LyricsUpdateTextIn(BaseModel):
    generated_text: str


class VideoAnalyzeUrlIn(BaseModel):
    url: str
    title: str = ""
    # Whisper language code (e.g. "hi", "te", "en"), or "" for auto-detect. Auto-detection can
    # confidently guess the wrong language on isolated vocal stems -- letting the user override
    # it fixes that when they already know the song's language.
    language: str = ""
    webhook_url: str | None = None


class SongSeparateUrlIn(BaseModel):
    url: str
    title: str = ""
    stem_count: str = DEFAULT_STEM_COUNT
    webhook_url: str | None = None


class PairMixIn(BaseModel):
    lyrics_id: int
    song_id: int


class TTSMixIn(BaseModel):
    lyrics_id: int
    song_id: int
    voice: str = "en-US-GuyNeural"
    engine: str = "edge"
    emotion: str = "neutral"
    instrumental_start_sec: float = 0.0
    instrumental_gain_db: float = -6.0
    tts_gain_db: float = 0.0
    webhook_url: str | None = None
