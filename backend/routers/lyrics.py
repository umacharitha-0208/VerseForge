import json

from fastapi import APIRouter, BackgroundTasks, HTTPException

from backend import db
from backend.config import EMOTION_PRESETS, LANGUAGE_VOICES, SUPPORTED_LANGUAGES
from backend.schemas import LyricsChatIn, LyricsGenerateIn, LyricsUpdateTextIn
from backend.services.agent_loop import RefineResult, identify_and_format_lyrics
from backend.services.jobs import run_job
from backend.services.lyrics_chat import QUICK_ACTIONS, chat_edit
from backend.services.lyrics_generator import ORIGINAL_LYRICS_STYLE, STYLE_PRESETS, generate
from backend.services.separation import separate_song
from backend.services.transcription import transcribe
from backend.services.url_download import download_audio_from_url

router = APIRouter(prefix="/api/lyrics", tags=["lyrics"])


def _is_url(text: str) -> bool:
    return text.strip().lower().startswith(("http://", "https://"))


def _resolve_input_text(input_text: str) -> tuple[str, bool, str | None]:
    """If input_text is a link, this used to be silently treated as literal text by the LLM
    (which just improvised something plausible-sounding around the URL string rather than
    using the real song) -- now it actually downloads, isolates vocals, and transcribes the
    real audio first, same pipeline as Video Analysis. Returns (resolved_text, was_url,
    source_title) -- source_title is the link's own title (e.g. YouTube's), used downstream to
    ground song identification the same way Video Analysis does."""
    if not _is_url(input_text):
        return input_text, False, None

    audio_path, source_title = download_audio_from_url(input_text.strip())
    stems = separate_song(audio_path, stem_count="4")
    transcript = transcribe(stems["vocals"], is_singing=True)
    if not transcript.strip():
        raise ValueError(
            "Couldn't transcribe any lyrics from that link -- the audio may be instrumental-only "
            "or too quiet/noisy for Whisper to pick up vocals."
        )
    return transcript, True, source_title


def _do_generate(
    input_text: str, style: str, output_language: str, script: str, title: str, max_iterations, score_threshold
) -> dict:
    resolved_text, was_url, source_title = _resolve_input_text(input_text)

    cached = db.find_lyrics_by_input(resolved_text, style, output_language, script)
    if cached:
        return {
            "lyrics_id": cached["id"],
            "generated_text": cached["generated_text"],
            "refine_iterations": json.loads(cached["refine_iterations_json"]) if cached["refine_iterations_json"] else [],
            "cached": True,
            "resolved_from_url": was_url,
            "resolved_input_text": resolved_text if was_url else None,
        }

    if style == ORIGINAL_LYRICS_STYLE:
        # Skip the creative rewrite loop entirely -- pull the real, complete published lyrics
        # (title-grounded, same approach as Video Analysis) instead of an AI reinterpretation.
        if was_url:
            lyrics_info = identify_and_format_lyrics([], resolved_text, source_title)
            final_text = lyrics_info["formatted_lyrics"]
        else:
            final_text = resolved_text
        result = RefineResult(final_text=final_text, iterations=[])
    else:
        result = generate(resolved_text, style, output_language, script, max_iterations, score_threshold)

    lyrics_id = db.add_lyrics(
        title, resolved_text, style, result.final_text, output_language, script, json.dumps(result.to_dicts())
    )
    return {
        "lyrics_id": lyrics_id,
        "generated_text": result.final_text,
        "refine_iterations": result.to_dicts(),
        "cached": False,
        "resolved_from_url": was_url,
        "resolved_input_text": resolved_text if was_url else None,
    }


@router.post("/generate")
def generate_lyrics(payload: LyricsGenerateIn, background_tasks: BackgroundTasks):
    title = payload.title.strip() or "Untitled"
    job_id = db.create_job("generate_lyrics", payload.model_dump(), payload.webhook_url)
    background_tasks.add_task(
        run_job,
        job_id,
        _do_generate,
        payload.input_text,
        payload.style,
        payload.output_language,
        payload.script,
        title,
        payload.max_iterations,
        payload.score_threshold,
    )
    return {"job_id": job_id}


@router.get("")
def list_lyrics():
    return [dict(l) for l in db.list_lyrics()]


@router.get("/options")
def options():
    return {
        "style_presets": STYLE_PRESETS,
        "languages": SUPPORTED_LANGUAGES,
        "language_voices": LANGUAGE_VOICES,
        # Both options keep the SAME language/meaning -- only the alphabet changes. Not
        # literally "English": romanized Telugu is still Telugu, just spelled with English
        # letters instead of Telugu script (e.g. "Namaste" instead of "नमस्ते").
        "scripts": {"native": "Original language", "romanized": "English letters (same language)"},
        "emotions": list(EMOTION_PRESETS.keys()),
        "quick_actions": QUICK_ACTIONS,
    }


@router.get("/{lyrics_id}/chat")
def get_chat(lyrics_id: int):
    return [dict(m) for m in db.list_lyrics_chat_messages(lyrics_id)]


@router.post("/{lyrics_id}/chat")
def post_chat(lyrics_id: int, payload: LyricsChatIn):
    """Single LLM call per turn -- chatbot-style manual refinement, distinct from the
    automated generate/critique loop. Not run as a background job since it's one fast call."""
    lyrics = db.get_lyrics(lyrics_id)
    if not lyrics:
        raise HTTPException(404, "Lyrics not found")

    revised = chat_edit(lyrics["generated_text"], payload.instruction, lyrics["style"], lyrics["output_language"])
    db.update_lyrics_text(lyrics_id, revised)
    db.add_lyrics_chat_message(lyrics_id, "user", payload.instruction)
    db.add_lyrics_chat_message(lyrics_id, "assistant", revised)

    return {"generated_text": revised, "chat": [dict(m) for m in db.list_lyrics_chat_messages(lyrics_id)]}


@router.put("/{lyrics_id}/text")
def update_text(lyrics_id: int, payload: LyricsUpdateTextIn):
    """Direct manual edit -- no LLM call, just overwrites the stored text with what the user
    typed."""
    lyrics = db.get_lyrics(lyrics_id)
    if not lyrics:
        raise HTTPException(404, "Lyrics not found")
    db.update_lyrics_text(lyrics_id, payload.generated_text)
    return {"lyrics_id": lyrics_id, "generated_text": payload.generated_text}
