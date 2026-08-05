from pathlib import Path

import streamlit as st

import api_client
from theme import apply_theme

st.set_page_config(page_title="Video Analysis", page_icon="🎬", layout="wide")
apply_theme()

st.title("🎬 Multimodal Semantic Analysis of a Music Video")
st.caption(
    "Extracts transcript (Whisper), music mood features (librosa), visual keyframes, then runs "
    "an agentic generate → critique → revise loop on the backend to synthesize a grounded "
    "semantic analysis (instead of a single one-shot prompt)."
)

source_mode = st.radio("Video source", ["Upload a file", "Paste a video link (YouTube, etc.)"])

uploaded = None
video_url = ""
if source_mode == "Upload a file":
    uploaded = st.file_uploader(
        "Upload a video",
        type=None,  # accept any file/format -- ffmpeg handles extraction regardless of extension
        help="Any video format is accepted; ffmpeg extracts the audio track server-side.",
    )
else:
    video_url = st.text_input(
        "Video URL",
        placeholder="https://www.youtube.com/watch?v=... (or any site yt-dlp supports)",
    )

title = st.text_input("Title for this video", value="")

LANGUAGE_HINTS = {
    "": "Auto-detect",
    "hi": "Hindi",
    "te": "Telugu",
    "ta": "Tamil",
    "pa": "Punjabi",
    "en": "English",
}
language_hint = st.selectbox(
    "Song language (optional)",
    list(LANGUAGE_HINTS.keys()),
    format_func=lambda c: LANGUAGE_HINTS[c],
    help="Whisper's own language auto-detection can confidently guess wrong on an isolated "
         "vocal track (seen in testing: it picked Punjabi, then English, for a Telugu song). "
         "If you already know the song's language, picking it here skips auto-detection.",
)

ready = uploaded is not None or bool(video_url.strip())

if ready and st.button("Analyze", type="primary"):
    if uploaded is not None:
        title_final = title.strip() or Path(uploaded.name).stem
        job_id = api_client.analyze_video(uploaded.getvalue(), uploaded.name, title_final, language_hint)
    else:
        job_id = api_client.analyze_video_url(video_url.strip(), title.strip(), language_hint)
    with st.spinner(f"Job #{job_id}: running full analysis pipeline (this can take a while)..."):
        job = api_client.wait_for_job(job_id, timeout=1800)

    if job["status"] == "error":
        st.error(f"Job failed: {job['error']}")
    else:
        result = job["result"]
        st.success("Analysis complete.")
        if result.get("cached"):
            st.info("Reused an existing analysis for this exact video — no re-processing or API calls made.")

        st.subheader("Lyrics")
        st.text(result["formatted_lyrics"])
        col_singer, col_genre = st.columns(2)
        with col_singer:
            st.metric("Singer / artist", result["singer"])
        with col_genre:
            st.metric("Genre / vibe", result["genre"])
        with st.expander("Raw ASR transcript (debug, pre-cleanup)"):
            st.text(result["transcript"] or "(no speech/vocals detected)")

        st.subheader("Music mood features")
        st.json(result["music_features"])
        st.caption(
            "tempo_bpm = beats per minute, energy_rms = loudness/intensity, brightness_hz = "
            "spectral centroid (higher = crisper/brighter timbre, lower = warmer/darker). "
            "Plain-English reading of these numbers:"
        )
        st.info(result["mood_hint"])

        st.subheader("Semantic analysis (final, after refine loop)")
        st.write(result["semantic_summary"])

        with st.expander(f"Refine loop trace ({len(result['refine_iterations'])} steps)"):
            for i, it in enumerate(result["refine_iterations"]):
                header = f"**Step {i + 1}: {it['step']}**"
                if it["score"] is not None:
                    header += f" — score: {it['score']}"
                st.markdown(header)
                st.text(it["content"])
                if it["critique"]:
                    st.caption(f"Critique: {it['critique']}")

st.divider()
st.subheader("Previously analyzed videos")
videos = api_client.list_videos()
if not videos:
    st.info("No videos analyzed yet.")
for video in videos:
    with st.expander(f"{video['title']} — uploaded {video['uploaded_at']}"):
        st.video(api_client.media_url(video["file_path"]))
        for a in api_client.list_analyses(video["id"]):
            st.markdown("**Lyrics**")
            st.text(a.get("formatted_lyrics") or a["transcript"] or "(none)")
            if a.get("singer") or a.get("genre"):
                st.caption(f"Singer: {a.get('singer') or '—'} · Genre: {a.get('genre') or '—'}")
            st.markdown("**Music features**")
            st.code(a["music_features_json"])
            if a.get("mood_hint"):
                st.caption(a["mood_hint"])
            st.markdown("**Semantic analysis**")
            st.write(a["semantic_summary"])
