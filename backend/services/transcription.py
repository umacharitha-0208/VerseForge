import re
from pathlib import Path

import torch
from faster_whisper import WhisperModel

from backend.config import WHISPER_MODEL_SIZE

_model: WhisperModel | None = None

# Whisper emits placeholder segments like "...", "..", "-", or music-note glyphs for stretches
# it can't confidently transcribe (typically instrumental/background-music sections, not
# speech) -- these aren't real lyrics and were leaking into downstream lyrics cleanup as junk
# noise (seen as stray repeated fragments and odd symbols in the final output).
_FILLER_ONLY_RE = re.compile(r"^[.\s…\-–—♪♫♪♫]*$")


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        _model = WhisperModel(WHISPER_MODEL_SIZE, device=device, compute_type=compute_type)
    return _model


def transcribe(
    audio_path: Path,
    is_singing: bool = False,
    translate_to_english: bool = False,
    language: str | None = None,
) -> str:
    """Transcribe an audio file (ideally an isolated vocals stem, not a full instrumental
    mix -- see video_analysis._isolate_vocals_for_transcription) into plain text lyrics.

    is_singing=True applies decoding params tuned for song lyrics: condition_on_previous_text
    disabled (singing's non-linear phrasing otherwise compounds hallucinations across
    segments), a higher beam size, and an initial_prompt nudging Whisper toward lyrical
    transcription rather than treating pauses/melisma as non-speech.

    translate_to_english=True uses Whisper's built-in translate task (not a separate
    translation step) -- it transcribes directly into English regardless of the sung
    language, rather than transcribing in the original language/script and leaving
    translation to something else.

    language, when given (a Whisper language code like "hi", "te", "en"), skips Whisper's own
    language auto-detection. Auto-detection runs on the first ~30s and can be unreliable on
    isolated vocal stems -- confirmed on one real song where it guessed Punjabi at 29%
    confidence then English at 55% on the same audio (neither correct; the song was Telugu
    with a Hindi hook line), producing transcription in the wrong script entirely. Passing the
    known language when the caller has one (e.g. a user-supplied hint) avoids that failure mode.
    """
    model = _get_model()
    kwargs = {"vad_filter": True}
    if translate_to_english:
        kwargs["task"] = "translate"
    if language:
        kwargs["language"] = language
    if is_singing:
        kwargs.update(
            beam_size=5,
            condition_on_previous_text=False,
            initial_prompt="The following is a transcription of song lyrics being sung.",
            vad_parameters={"min_silence_duration_ms": 300},
        )
    segments, _info = model.transcribe(str(audio_path), **kwargs)
    lines = [
        seg.text.strip() for seg in segments
        if seg.text.strip() and not _FILLER_ONLY_RE.match(seg.text.strip())
    ]
    return "\n".join(lines)
