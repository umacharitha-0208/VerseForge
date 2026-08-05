"""Single-shot LLM calls (initial drafts, multimodal keyframe analysis) via LlamaIndex's
Gemini wrapper. The iterative critique/revise loop itself is driven by AutoGen agents
(see agent_loop.py) that also call Gemini, but through AutoGen's own OpenAI-compatible
client rather than through this module."""

import base64

from llama_index.core.llms import ChatMessage, ImageBlock, TextBlock
from llama_index.llms.google_genai import GoogleGenAI

from backend.config import GEMINI_API_KEY, LLM_MODEL

_llm: GoogleGenAI | None = None


class LLMNotConfiguredError(RuntimeError):
    pass


def _get_llm() -> GoogleGenAI:
    global _llm
    if _llm is None:
        if not GEMINI_API_KEY:
            raise LLMNotConfiguredError(
                "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        _llm = GoogleGenAI(model=LLM_MODEL, api_key=GEMINI_API_KEY)
    return _llm


def complete(prompt: str) -> str:
    llm = _get_llm()
    response = llm.complete(prompt)
    return str(response).strip()


def complete_with_images(text_prompt: str, frames_b64: list[str]) -> str:
    llm = _get_llm()
    blocks = [TextBlock(text=text_prompt)]
    for frame_b64 in frames_b64:
        blocks.append(ImageBlock(image=base64.b64decode(frame_b64), image_mimetype="image/jpeg"))
    message = ChatMessage(role="user", blocks=blocks)
    response = llm.chat([message])
    return (response.message.content or "").strip()
