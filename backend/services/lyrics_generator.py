from backend.services.agent_loop import RefineResult, refine_lyrics

# Sentinel style: skip the creative rewrite entirely and return the real, complete original
# song lyrics as-is (only meaningful when the input was a song link -- see lyrics.py router).
ORIGINAL_LYRICS_STYLE = "original lyrics (extract real song lyrics, no rewrite)"

STYLE_PRESETS = [
    ORIGINAL_LYRICS_STYLE,
    "poetic free verse",
    "pop song lyrics with verse/chorus/verse/chorus structure",
    "rap/hip-hop lyrics with strong rhythm and rhyme",
    "melancholic ballad lyrics",
    "upbeat anthemic lyrics",
]


def generate(
    input_text: str,
    style: str,
    output_language: str = "same_as_input",
    script: str = "native",
    max_iterations: int | None = None,
    score_threshold: int | None = None,
) -> RefineResult:
    if not input_text.strip():
        raise ValueError("Input text is empty.")
    kwargs = {}
    if max_iterations is not None:
        kwargs["max_iterations"] = max_iterations
    if score_threshold is not None:
        kwargs["score_threshold"] = score_threshold
    return refine_lyrics(input_text, style, output_language, script, **kwargs)
