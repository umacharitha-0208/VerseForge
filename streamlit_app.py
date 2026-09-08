import streamlit as st

import api_client
from backend_runtime import ensure_backend
from theme import apply_theme

st.set_page_config(page_title="VerseForge", page_icon="🎵", layout="wide")
apply_theme()
try:
	ensure_backend(api_client.BASE_URL)
except Exception as exc:
	st.warning(f"The backend is unavailable: {exc}")

pages = [
	st.Page("frontend/pages/1_Convert_Songs_to_Stems.py", title="Convert Songs to Stems"),
	st.Page("frontend/pages/2_Video_Analysis.py", title="Video Analysis"),
	st.Page("frontend/pages/3_Lyrics_Studio.py", title="Lyrics Studio"),
	st.Page("frontend/pages/4_Library.py", title="Library"),
	st.Page("frontend/pages/6_GuitarGPT.py", title="GuitarGPT"),
]
navigation = st.navigation(pages)

st.title("🎵 VerseForge")
st.markdown("Turn songs and video into stems, lyrics, and playable instruments.")

with st.sidebar:
	st.header("Backend status")
	try:
		status = api_client.get_status()
		st.success(f"Backend reachable at {api_client.BASE_URL}")
		if status["llm_configured"]:
			st.success("Gemini API key detected.")
		else:
			st.warning("No GEMINI_API_KEY set.")
	except Exception as exc:
		st.error(f"Cannot reach backend: {exc}")

navigation.run()
