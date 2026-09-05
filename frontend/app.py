import streamlit as st

import api_client
from backend_runtime import ensure_backend
from theme import apply_theme

st.set_page_config(page_title="VerseForge", page_icon="🎵", layout="wide")
apply_theme()
ensure_backend(api_client.BASE_URL)

st.title("🎵 VerseForge")
st.markdown(
    """
Turn songs and video into stems, lyrics, and playable instruments.

1. **🎚️ Convert Songs to Stems** — split a song into vocals/drums/bass/other.
2. **🎬 Video Analysis** — transcribe, analyze mood, and summarize a music video.
3. **✍️ Lyrics Studio** — write, refine, and voice lyrics over an instrumental.
4. **🎸 GuitarGPT** — describe a guitar sound, play it on a virtual keyboard.
5. **📚 Library** — everything you've generated, in one place.

Use the sidebar to get started.
"""
)

with st.sidebar:
    st.header("Backend status")
    try:
        status = api_client.get_status()
        st.success(f"Backend reachable at {api_client.BASE_URL}")
        if status["llm_configured"]:
            st.success("Gemini API key detected.")
        else:
            st.error("No GEMINI_API_KEY set on the backend. Copy .env.example to .env "
                      "and add your key to use lyrics generation, video semantic analysis, "
                      "and instrument creation.")
        if status["gpu_available"]:
            st.success("GPU detected — Demucs/Whisper will run on CUDA.")
        else:
            st.warning("No GPU detected — Demucs/Whisper will run on CPU (slower).")
    except Exception as e:
        st.error(f"Cannot reach backend at {api_client.BASE_URL}. Is it running? ({e})")
