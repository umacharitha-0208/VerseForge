"""Iterative generate -> critique-and-revise loop, replacing a single one-shot prompt for
lyrics generation and video semantic analysis.

Split of responsibilities:
- LlamaIndex (`llama_llm.py`) makes the initial single-shot call: the first lyrics draft, and
  the multimodal (text + keyframe images) video analysis draft.
- AutoGen drives the loop itself: one Editor agent, backed by Gemini through AutoGen's own
  OpenAI-compatible client, scores the current draft AND produces a revision in the same
  response, stopping once its self-reported score clears the threshold or max_iterations is
  reached.

Cost note: this used to be a two-agent Writer<->Critic conversation (a separate critique call,
then a separate revise call, each iteration) -- a more genuine multi-agent negotiation, but
2x the API calls per iteration. It was collapsed to one combined-response agent to cut calls
per iteration in half (worst case at default settings: 7 calls -> 4). Set
REFINE_MAX_ITERATIONS=0 in .env for single-shot generation (1 call, no loop at all).

The video loop is text-only (transcript + music features + current draft) -- the keyframe
images inform the initial LlamaIndex draft but aren't re-sent on every revision turn.
"""

import json
import re
from dataclasses import asdict, dataclass, field

from autogen import ConversableAgent

from backend.config import (
    GEMINI_API_KEY,
    GEMINI_OPENAI_BASE_URL,
    LLM_MODEL,
    REFINE_MAX_ITERATIONS,
    REFINE_SCORE_THRESHOLD,
    SUPPORTED_LANGUAGES,
)
from backend.services import llama_llm
from backend.services.llama_llm import LLMNotConfiguredError


def _autogen_llm_config() -> dict:
    if not GEMINI_API_KEY:
        raise LLMNotConfiguredError("GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.")
    return {
        "config_list": [{"model": LLM_MODEL, "api_key": GEMINI_API_KEY, "base_url": GEMINI_OPENAI_BASE_URL}],
        "temperature": 0.8,
    }


def _agent_reply(agent: ConversableAgent, message: str) -> str:
    reply = agent.generate_reply(messages=[{"role": "user", "content": message}])
    if isinstance(reply, dict):
        return (reply.get("content") or "").strip()
    return str(reply).strip()


def _extract_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


@dataclass
class RefineIteration:
    step: str  # "draft" or "revision"
    content: str
    critique: str | None = None
    score: int | None = None


@dataclass
class RefineResult:
    final_text: str
    iterations: list = field(default_factory=list)

    def to_dicts(self):
        return [asdict(it) for it in self.iterations]


def _run_editor_loop(
    editor: ConversableAgent,
    initial_content: str,
    max_iterations: int,
    score_threshold: int,
) -> RefineResult:
    iterations = [RefineIteration(step="draft", content=initial_content)]
    current = initial_content

    for _ in range(max_iterations):
        reply = _agent_reply(editor, f"Current content:\n{current}")
        parsed = _extract_json(reply)
        score = int(parsed.get("score", 0)) if parsed else score_threshold
        issues = parsed.get("issues", []) if parsed else []
        revised = (parsed.get("revised_text") or current).strip() if parsed else current

        iterations[-1].critique = json.dumps({"score": score, "issues": issues})
        iterations[-1].score = score

        if score >= score_threshold or not issues:
            break

        current = revised
        iterations.append(RefineIteration(step="revision", content=current))

    return RefineResult(final_text=current, iterations=iterations)


def refine_lyrics(
    input_text: str,
    style: str,
    output_language: str = "same_as_input",
    script: str = "native",
    max_iterations: int = REFINE_MAX_ITERATIONS,
    score_threshold: int = REFINE_SCORE_THRESHOLD,
) -> RefineResult:
    if output_language == "same_as_input":
        language_clause = (
            "Detect the language the input text is written in (regardless of what script it's "
            "typed in) and write the output ENTIRELY in that SAME language. Do not translate to "
            "a different language."
        )
    else:
        language_name = SUPPORTED_LANGUAGES.get(output_language, output_language)
        language_clause = (
            f"Write the output ENTIRELY in {language_name}. The input may be in a different "
            "language than the requested output -- translate and adapt the meaning."
        )

    if script == "romanized":
        script_clause = (
            "Write using the Roman/Latin alphabet (phonetic transliteration), the way it's "
            "commonly typed in casual texting -- e.g. Hindi 'नमस्ते, आप कैसे हैं?' should become "
            "'Namaste, aap kaise hain?', NOT native script. This applies no matter which "
            "language is being written."
        )
    else:
        script_clause = (
            "Write using the language's proper native script (e.g. Devanagari for Hindi, "
            "Telugu script for Telugu, Gurmukhi for Punjabi), not a Roman/Latin transliteration."
        )

    language_rule = f"{language_clause} {script_clause}"

    draft = llama_llm.complete(
        f"Rewrite the following text as {style}. Preserve meaning and key details, make it "
        f"rhythmic, singable, with line breaks and verse/chorus structure where appropriate. "
        f"{language_rule} Output only the lyrics, no preamble.\n\n---\n{input_text}\n---"
    )

    if max_iterations <= 0:
        return RefineResult(final_text=draft, iterations=[RefineIteration(step="draft", content=draft)])

    editor = ConversableAgent(
        name="LyricsEditor",
        system_message=(
            f"You are an expert lyricist and critical editor working in the style: {style}. "
            f"{language_rule} Evaluate the given lyrics for meaning preservation, rhyme/rhythm "
            f"quality, singability, and style fit against this original text:\n\n{input_text}\n\n"
            'Respond with ONLY a JSON object: {"score": <1-10 integer>, "issues": '
            f'["issue1", ...], "revised_text": "<if score is below {score_threshold}, an '
            'improved version fixing the issues; otherwise repeat the current lyrics '
            'unchanged>"}.'
        ),
        llm_config=_autogen_llm_config(),
        human_input_mode="NEVER",
    )

    return _run_editor_loop(editor, draft, max_iterations, score_threshold)


def identify_and_format_lyrics(
    frames_b64: list[str], raw_transcript: str, source_title: str | None = None
) -> dict:
    """Whisper's raw ASR output is often garbled ('My heart is difficult' instead of the real
    line) and, for non-Latin-script languages, is transcribed in the native script rather than
    the Roman/Latin lyrics-site style most users expect. This asks Gemini to produce a cleaned,
    properly line-broken, ROMANIZED lyrics block -- using its own knowledge to correct obvious
    ASR errors if it recognizes the actual song, but staying grounded in the transcript (not
    inventing new lines) if it doesn't -- plus a best-effort singer and genre/vibe guess, each
    explicitly allowed to say "unable to identify" rather than confidently fabricate.

    source_title, when available (e.g. the YouTube video's own title, which for music videos
    often literally is "Song Name | Movie | Singer1, Singer2, Composer"), is a far more
    reliable identity signal than guessing from keyframes/ASR alone -- if it names the real
    song, that unlocks recalling its actual full published lyrics/singer instead of limping
    along on noisy ASR text.

    Returns {"formatted_lyrics": str, "singer": str, "genre": str}, falling back to the raw
    transcript / "Unable to identify" if the LLM call or JSON parsing fails.
    """
    fallback = {
        "formatted_lyrics": raw_transcript or "(no speech/vocals detected)",
        "singer": "Unable to identify with confidence.",
        "genre": "Unable to identify with confidence.",
    }
    if not raw_transcript:
        return fallback

    title_clause = (
        f"The video's own source title/metadata (often contains the real song name, movie, "
        f"and singer/composer credits for music videos): \"{source_title}\"\n\n"
        if source_title else ""
    )

    reply = llama_llm.complete_with_images(
        "Here is a raw ASR (speech-to-text) transcript of a song's sung vocals -- it may "
        "contain significant transcription errors (mangled words, wrong words entirely), and "
        f"is in whatever script the language was detected in:\n\n{raw_transcript}\n\n"
        + title_clause +
        "Using all of the above (transcript, source title if given, and the attached video "
        "keyframes, if any), do three things:\n"
        "1. Identify the real song if you can, using the source title/credits as the primary "
        "signal (trust it over the noisy ASR) plus any lyrics fragments and visuals you "
        "recognize. If you identify it with reasonable confidence, output its ACTUAL COMPLETE "
        "published lyrics -- every verse/chorus/bridge of the FULL song from your own "
        "knowledge, the way a lyrics site (e.g. Genius) would show it, NOT limited to just the "
        "portion that happens to match the given (possibly short/partial) ASR transcript or "
        "video clip. The ASR transcript is only a hint for identification, not a length cap -- "
        "if you know the real song has more verses than what's in the transcript, include "
        "them. If you cannot identify the song with reasonable confidence, don't guess a full "
        "song's worth of lyrics; fall back to cleaning up/romanizing only the given ASR "
        "transcript without inventing new lines.\n"
        "2. Either way, write the final lyrics in the Roman/Latin alphabet (phonetic "
        "transliteration, the way lyrics sites display non-English songs) -- e.g. 'Tu safar "
        "mera, hai tu hi meri manzil', not native script and not an English translation of the "
        "meaning -- with proper line breaks and verse/chorus structure.\n"
        "3. Give the singer/original artist. If a source title/credits line was given, prefer "
        "the actual singer(s) named there over a visual guess of who appears on-screen "
        "(actors in a music video are frequently not the singers). If you still aren't "
        "reasonably confident after considering the title, respond with exactly 'Unable to "
        "identify with confidence.' instead of guessing a name.\n"
        "4. Give a short colloquial genre/vibe label the way listeners casually describe a "
        "song (e.g. 'breakup song', 'love song', 'party/mass song', 'devotional song', "
        "'sad song', 'wedding song') -- 1-4 words, no explanation.\n\n"
        'Respond with ONLY a JSON object: {"formatted_lyrics": "...", "singer": "...", '
        '"genre": "..."}.',
        frames_b64,
    )
    parsed = _extract_json(reply)
    if not parsed or not parsed.get("formatted_lyrics"):
        return fallback
    return {
        "formatted_lyrics": parsed.get("formatted_lyrics") or fallback["formatted_lyrics"],
        "singer": parsed.get("singer") or fallback["singer"],
        "genre": parsed.get("genre") or fallback["genre"],
    }


def refine_video_analysis(
    frames_b64: list[str],
    transcript: str,
    music_features: dict,
    max_iterations: int = REFINE_MAX_ITERATIONS,
    score_threshold: int = REFINE_SCORE_THRESHOLD,
) -> RefineResult:
    base_context = (
        f"Transcript / lyrics:\n{transcript or '(no speech/vocals detected)'}\n\n"
        f"Music features (from audio analysis): {music_features}\n"
    )

    draft = llama_llm.complete_with_images(
        "You are analyzing a music video across three modalities: lyrics/transcript, the visual "
        "keyframes attached, and the audio's musical characteristics.\n\n" + base_context +
        "\nWrite a semantic/sentiment analysis (250-350 words total) using EXACTLY this "
        "markdown structure -- these four numbered headings verbatim (as '### 1. Overall Mood "
        "and Theme' etc.), each followed by a short paragraph, nothing before the first "
        "heading or after the last paragraph:\n\n"
        "### 1. Overall Mood and Theme\n"
        "(the overall mood/theme conveyed by the lyrics and visuals together)\n\n"
        "### 2. Lyrical Alignment\n"
        "(how the visuals relate to or contrast with the lyrics)\n\n"
        "### 3. Musical Characteristics and Energy\n"
        "(how the music's tempo/energy/brightness from the given features aligns with the "
        "visual and lyrical content)\n\n"
        "### 4. Overall Sentiment Verdict\n"
        "(a concise overall sentiment verdict, 2-3 sentences)",
        frames_b64,
    )

    if max_iterations <= 0:
        return RefineResult(final_text=draft, iterations=[RefineIteration(step="draft", content=draft)])

    editor = ConversableAgent(
        name="VideoFactEditor",
        system_message=(
            "You are a meticulous fact-checking editor for a music video's semantic analysis. "
            "Check whether the given analysis is grounded in the transcript and music features "
            f"below (no hallucinated claims), and whether it uses EXACTLY this four-section "
            "markdown structure with these headings verbatim -- '### 1. Overall Mood and "
            "Theme', '### 2. Lyrical Alignment', '### 3. Musical Characteristics and Energy', "
            f"'### 4. Overall Sentiment Verdict':\n\n{base_context}\n"
            'Respond with ONLY a JSON object: {"score": <1-10 integer>, "issues": '
            f'["issue1", ...], "revised_text": "<if score is below {score_threshold}, a '
            "revised analysis fixing the issues while preserving the exact four-section "
            "markdown heading structure, staying grounded in the transcript/features (you do "
            'not have access to the original images); otherwise repeat the current analysis '
            'unchanged>"}.'
        ),
        llm_config=_autogen_llm_config(),
        human_input_mode="NEVER",
    )

    return _run_editor_loop(editor, draft, max_iterations, score_threshold)
