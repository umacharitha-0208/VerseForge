import base64
import json
import subprocess
from pathlib import Path

import cv2
import librosa
import numpy as np

from backend.services.agent_loop import identify_and_format_lyrics, refine_video_analysis
from backend.services.separation import SeparationError, separate_song
from backend.services.transcription import transcribe


def extract_keyframes(video_path: Path, num_frames: int = 6) -> list[str]:
    """Sample num_frames evenly across the video, return list of base64 JPEG strings."""
    cap = cv2.VideoCapture(str(video_path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames_b64 = []
    if total <= 0:
        cap.release()
        return frames_b64
    idxs = np.linspace(0, max(total - 1, 0), num_frames).astype(int)
    for idx in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if not ok:
            continue
        frame = cv2.resize(frame, (512, 288))
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if ok:
            frames_b64.append(base64.b64encode(buf).decode("ascii"))
    cap.release()
    return frames_b64


def extract_audio(video_path: Path, out_audio_path: Path) -> Path:
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(out_audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed:\n{result.stderr}")
    return out_audio_path


def compute_music_features(audio_path: Path) -> dict:
    y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    if y.size == 0:
        return {"tempo_bpm": None, "energy_rms": None, "brightness_hz": None}
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    rms = float(np.mean(librosa.feature.rms(y=y)))
    centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    tempo_val = float(tempo) if np.isscalar(tempo) else float(tempo[0])
    return {
        "tempo_bpm": round(tempo_val, 1),
        "energy_rms": round(rms, 4),
        "brightness_hz": round(centroid, 1),
    }


def interpret_mood(features: dict) -> str:
    """Plain-English gloss of the raw DSP numbers -- tempo/energy/brightness are acoustic
    measurements, not emotion labels; this is a simple rule-of-thumb reading of them, not a
    genre/emotion classifier. The semantic analysis (which also reads the actual lyrics) is
    the more reliable source for something like "sad song" or "breakup song" -- this is just
    a quick sanity-check translation of the numbers themselves."""
    tempo = features.get("tempo_bpm")
    energy = features.get("energy_rms")
    brightness = features.get("brightness_hz")
    if tempo is None or energy is None or brightness is None:
        return "Not enough audio to estimate."

    pace = "slow" if tempo < 90 else ("moderate" if tempo < 120 else "fast")
    power = "soft/subdued" if energy < 0.06 else ("moderate" if energy < 0.12 else "powerful/intense")
    tone = "warm/dark" if brightness < 1500 else ("balanced" if brightness < 2500 else "bright/crisp")

    if pace == "slow" and power == "soft/subdued":
        lean = "often associated with ballads, ambient, or melancholic/sad songs"
    elif pace == "fast" and power == "powerful/intense":
        lean = "often associated with upbeat, energetic, or dance/party tracks"
    elif pace == "moderate" and power == "moderate":
        lean = "a fairly typical mid-tempo pop/romantic song pace"
    else:
        lean = "doesn't fit a single obvious category from tempo/energy alone"

    return f"{pace.capitalize()} pace, {power} energy, {tone} tone -- {lean}."


def _isolate_vocals_for_transcription(audio_out_path: Path) -> Path:
    """Whisper transcribes singing over instrumentation badly -- it's tuned for speech, and
    a full band mix (drums/bass/melody under the vocal) causes it to pick up only fragments
    or hallucinate. Running our own Demucs separation first and transcribing the isolated
    vocals stem instead fixes this; falls back to the raw mixed audio if separation fails
    for any reason (e.g. a genuinely non-musical/speech-only video)."""
    try:
        stems = separate_song(audio_out_path, stem_count="4")
        return stems["vocals"]
    except (SeparationError, Exception):
        return audio_out_path


def analyze_video(
    video_path: Path,
    audio_out_path: Path,
    num_frames: int = 6,
    source_title: str | None = None,
    language: str | None = None,
) -> dict:
    """Full pipeline: extract audio, transcribe, compute music features, extract frames,
    then run the agentic generate->critique->revise loop to synthesize a semantic analysis
    across all three modalities.

    source_title (the YouTube video's own title, when analysis came from a URL) is passed
    through to identify_and_format_lyrics as a strong identity signal -- see its docstring.

    language, when given, overrides Whisper's own language auto-detection -- see
    transcribe()'s docstring for why that matters (auto-detect can confidently pick the wrong
    language on an isolated vocal stem)."""
    extract_audio(video_path, audio_out_path)
    vocals_path = _isolate_vocals_for_transcription(audio_out_path)
    # Native transcription (not Whisper's translate task) -- translate produces a rough,
    # often garbled English *meaning* paraphrase ("The journey is mine...") instead of the
    # song's real lyrics. identify_and_format_lyrics below turns this raw ASR text into a
    # cleaned, ROMANIZED (Latin-script) lyrics block instead, which is what's actually wanted.
    transcript = transcribe(vocals_path, is_singing=True, language=language)
    # Music features are computed on the full mix, not the isolated vocals -- tempo/energy/
    # brightness should reflect the whole song, not just the vocal track.
    music_features = compute_music_features(audio_out_path)
    mood_hint = interpret_mood(music_features)
    frames_b64 = extract_keyframes(video_path, num_frames=num_frames)

    lyrics_info = identify_and_format_lyrics(frames_b64, transcript, source_title)
    refine_result = refine_video_analysis(frames_b64, transcript, music_features)

    return {
        "transcript": transcript,
        "formatted_lyrics": lyrics_info["formatted_lyrics"],
        "singer": lyrics_info["singer"],
        "genre": lyrics_info["genre"],
        "music_features": music_features,
        "mood_hint": mood_hint,
        "semantic_summary": refine_result.final_text,
        "music_features_json": json.dumps(music_features),
        "refine_iterations": refine_result.to_dicts(),
        "frames_b64": frames_b64,
    }
