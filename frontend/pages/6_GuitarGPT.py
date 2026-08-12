from instrument_common import render_gpt_page

render_gpt_page(
    family="guitar",
    page_title="GuitarGPT",
    icon="🎸",
    tagline=(
        "Create playable guitars with words. Uses real sampled audio (FluidSynth + a General "
        "MIDI SoundFont) rather than synthesized approximation, so it actually sounds like "
        "the instrument described."
    ),
)
