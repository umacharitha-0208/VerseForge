"""Chatbot-style manual refinement for lyrics: unlike the automated generate/agent_loop
critique loop, this is driven entirely by explicit user instructions (a quick-action preset
or freeform chat message) -- one LLM call per user turn, no automatic looping."""

from backend.services import llama_llm

QUICK_ACTIONS = [
    "Make it darker",
    "Make it softer",
    "Shorter",
    "Longer",
    "More rhythmic",
    "More emotional",
    "More hopeful",
    "Simpler language",
]


def chat_edit(current_text: str, instruction: str, style: str, output_language: str) -> str:
    prompt = (
        f"You are editing song lyrics (style: {style}, language: {output_language}) based on "
        f"a direct instruction from the songwriter. Apply this instruction:\n\n{instruction}\n\n"
        f"Current lyrics:\n{current_text}\n\n"
        f"Output ONLY the revised lyrics in {output_language}, no preamble or explanation."
    )
    return llama_llm.complete(prompt)
