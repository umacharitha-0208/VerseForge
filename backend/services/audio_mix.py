import asyncio
import shutil
from pathlib import Path

from pydub import AudioSegment

from backend import db
from backend.config import EMOTION_PRESETS, GENERATED_DIR

DEFAULT_VOICE = "en-US-GuyNeural"
DEFAULT_ENGINE = "edge"

# Small per-line pitch offsets (Hz) cycled across lyric lines so consecutive lines don't come
# out as one flat monotone read -- a cheap approximation of a singer's melodic phrasing.
LINE_PITCH_CONTOUR_HZ = [0, 4, -3, 6, -4, 2]
LINE_PAUSE_MS = 380


async def _synthesize_edge(text: str, out_path: Path, voice: str, emotion: str, pitch_hz: int | None = None) -> None:
    import edge_tts

    preset = EMOTION_PRESETS.get(emotion, EMOTION_PRESETS["neutral"])
    pitch = f"{pitch_hz:+d}Hz" if pitch_hz is not None else preset["pitch"]
    communicate = edge_tts.Communicate(
        text, voice, rate=preset["rate"], volume=preset["volume"], pitch=pitch
    )
    await communicate.save(str(out_path))


def _synthesize_gtts(text: str, out_path: Path, lang: str) -> None:
    from gtts import gTTS

    gTTS(text=text, lang=lang).save(str(out_path))


async def _synthesize_edge_lines(lines: list[str], voice: str, emotion: str, tmp_dir: Path) -> list[Path]:
    import edge_tts

    preset = EMOTION_PRESETS.get(emotion, EMOTION_PRESETS["neutral"])
    base_pitch = int(preset["pitch"].replace("Hz", ""))
    paths = []
    for i, line in enumerate(lines):
        pitch = f"{base_pitch + LINE_PITCH_CONTOUR_HZ[i % len(LINE_PITCH_CONTOUR_HZ)]:+d}Hz"
        out = tmp_dir / f"line_{i}.mp3"
        communicate = edge_tts.Communicate(line, voice, rate=preset["rate"], volume=preset["volume"], pitch=pitch)
        await communicate.save(str(out))
        paths.append(out)
    return paths


def synthesize_tts(
    text: str,
    out_path: Path,
    voice: str = DEFAULT_VOICE,
    engine: str = DEFAULT_ENGINE,
    emotion: str = "neutral",
) -> Path:
    """engine="edge" uses Microsoft Edge TTS (voice e.g. "hi-IN-SwaraNeural"; supports the
    emotion presets via rate/pitch/volume). engine="gtts" uses Google Translate TTS (voice is
    a language code like "pa" for Punjabi -- the only option for languages Edge TTS has no
    voice for at all; no emotion/prosody control available on this engine). Both require
    internet access.

    For multi-line lyrics on the edge engine, each line is synthesized separately with a
    small alternating pitch offset and joined with a timed pause -- this is still spoken-word
    TTS (no melody/rhythm synthesis model is available in this environment), but the per-line
    pitch contour and phrasing pauses make it read more like sung phrasing than one flat,
    continuously-read paragraph.
    """
    out_path = Path(out_path)
    if engine == "gtts":
        _synthesize_gtts(text, out_path, voice)
        return out_path

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) <= 1:
        asyncio.run(_synthesize_edge(text, out_path, voice, emotion))
        return out_path

    tmp_dir = out_path.parent / f".tts_lines_{out_path.stem}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        line_paths = asyncio.run(_synthesize_edge_lines(lines, voice, emotion, tmp_dir))
        pause = AudioSegment.silent(duration=LINE_PAUSE_MS)
        combined = AudioSegment.empty()
        for i, p in enumerate(line_paths):
            combined += AudioSegment.from_file(p)
            if i < len(line_paths) - 1:
                combined += pause
        combined.export(out_path, format="mp3")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return out_path


def overlay_tts_on_instrumental(
    instrumental_path: Path,
    tts_path: Path,
    out_path: Path,
    instrumental_gain_db: float = -6.0,
    tts_gain_db: float = 0.0,
    instrumental_start_sec: float = 0.0,
) -> Path:
    """Loop/trim the instrumental to match the spoken-word length, then overlay the TTS on
    top. instrumental_start_sec skips an intro (or any unwanted section) by starting playback
    from that point in the instrumental before the loop/trim/overlay logic runs."""
    instrumental = AudioSegment.from_file(instrumental_path) + instrumental_gain_db
    speech = AudioSegment.from_file(tts_path) + tts_gain_db

    start_ms = max(int(instrumental_start_sec * 1000), 0)
    if start_ms < len(instrumental):
        instrumental = instrumental[start_ms:]

    if len(instrumental) < len(speech):
        loops = int(len(speech) / max(len(instrumental), 1)) + 1
        instrumental = instrumental * loops
    instrumental = instrumental[: len(speech)]

    mixed = instrumental.overlay(speech)
    out_path = Path(out_path)
    mixed.export(out_path, format="mp3")
    return out_path


def get_audio_duration_sec(path: Path) -> float:
    return len(AudioSegment.from_file(path)) / 1000.0


NON_VOCAL_STEM_TYPES = ("drums", "bass", "guitar", "piano", "other")


def get_or_create_instrumental(song_id: int):
    """Return the 'instrumental' stem (every non-vocal stem summed -- drums/bass/other for a
    4-stem separation, plus guitar/piano too for a 6-stem one), creating and caching it on
    first request for this song."""
    stems = {s["stem_type"]: s for s in db.list_stems_for_song(song_id)}

    if "instrumental" in stems and Path(stems["instrumental"]["file_path"]).exists():
        return stems["instrumental"]

    parts = [t for t in NON_VOCAL_STEM_TYPES if t in stems]
    if not parts:
        raise ValueError(f"No non-vocal stems found for song_id={song_id}")

    mix = AudioSegment.from_file(stems[parts[0]]["file_path"])
    for t in parts[1:]:
        mix = mix.overlay(AudioSegment.from_file(stems[t]["file_path"]))

    out_path = GENERATED_DIR / f"song{song_id}_instrumental.wav"
    mix.export(out_path, format="wav")

    stem_id = db.add_stem(song_id, "instrumental", str(out_path))
    return next(s for s in db.list_stems_for_song(song_id) if s["id"] == stem_id)
