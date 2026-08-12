from pathlib import Path

import streamlit as st

import api_client
from theme import apply_theme

st.set_page_config(page_title="Convert Songs to Stems", page_icon="🎚️", layout="wide")
apply_theme()

st.title("🎚️ Convert Songs into Stems")
st.caption("Powered by Demucs, run as a background job on the FastAPI backend.")

source_mode = st.radio("Song source", ["Upload a file", "Paste a link (YouTube, etc.)"])

uploaded = None
song_url = ""
if source_mode == "Upload a file":
    uploaded = st.file_uploader(
        "Upload a song",
        type=None,  # accept any file/format -- ffmpeg/Demucs handle extraction regardless of extension
        help="Any audio (or video) format is accepted.",
    )
else:
    song_url = st.text_input(
        "Song URL",
        placeholder="https://www.youtube.com/watch?v=... (or any site yt-dlp supports)",
    )

title = st.text_input("Title for this song", value="")

stem_mode = st.radio(
    "How many stems?",
    ["4 (vocals/drums/bass/other) — faster, lighter (default)", "6 (vocals/drums/bass/guitar/piano/other) — as many as possible"],
)
stem_count = "6" if stem_mode.startswith("6") else "4"
st.caption(
    "4-stem uses a smaller model -- less memory and time per job, which is why it's the "
    "default on a shared/memory-constrained deployment. Pick 6-stem if you specifically need "
    "guitar/piano isolated. 6-stem is the most any public separation model offers -- finer "
    "categories (choir, brass, synth, sitar, etc.) aren't achievable with open tools."
)

ready = uploaded is not None or bool(song_url.strip())

if ready and st.button("Separate", type="primary"):
    if uploaded is not None:
        title_final = title.strip() or Path(uploaded.name).stem
        job_id = api_client.separate_song(uploaded.getvalue(), uploaded.name, title_final, stem_count)
    else:
        title_final = title.strip() or "Untitled"
        job_id = api_client.separate_song_url(song_url.strip(), title.strip(), stem_count)
    with st.spinner(f"Job #{job_id}: running Demucs source separation (first run downloads the model)..."):
        job = api_client.wait_for_job(job_id)

    if job["status"] == "error":
        st.error(f"Job failed: {job['error']}")
    else:
        result = job["result"]
        stems = result["stems"]
        individual_stems = {k: v for k, v in stems.items() if k != "instrumental"}
        st.success(f"Separated '{title_final}' into {len(individual_stems)} stems.")
        if result.get("cached"):
            st.info("Reused an existing separation for this exact audio + stem count — Demucs was not re-run.")
        cols = st.columns(len(individual_stems))
        for col, (stem_type, path) in zip(cols, individual_stems.items()):
            with col:
                st.subheader(stem_type.capitalize())
                st.audio(api_client.media_url(path))

        if "instrumental" in stems:
            st.divider()
            st.subheader("🎵 Complete Background Music")
            st.caption("Every non-vocal stem summed into one track -- the full instrumental, not just one instrument.")
            st.audio(api_client.media_url(stems["instrumental"]))

st.divider()
st.subheader("Previously separated songs")
songs = api_client.list_songs()
if not songs:
    st.info("No songs separated yet.")
for song in songs:
    with st.expander(f"{song['title']} — uploaded {song['uploaded_at']}"):
        stems = api_client.list_stems(song["id"])
        individual = [s for s in stems if s["stem_type"] != "instrumental"]
        combined = next((s for s in stems if s["stem_type"] == "instrumental"), None)

        cols = st.columns(max(len(individual), 1))
        for col, stem in zip(cols, individual):
            with col:
                st.caption(stem["stem_type"].capitalize())
                st.audio(api_client.media_url(stem["file_path"]))

        if combined:
            st.caption("🎵 Complete Background Music (all non-vocal stems combined)")
            st.audio(api_client.media_url(combined["file_path"]))

        stem_types = {s["stem_type"] for s in stems}
        if "vocals" in stem_types and "lead_vocals" not in stem_types:
            st.caption(
                "Split into lead vs. background vocals (heuristic pitch-based separation -- "
                "works best with one clear dominant vocal line)."
            )
            if st.button("Split lead/background vocals", key=f"split_{song['id']}"):
                job_id = api_client.split_vocals(song["id"])
                with st.spinner(f"Job #{job_id}: splitting vocals..."):
                    job = api_client.wait_for_job(job_id, timeout=300)
                if job["status"] == "error":
                    st.error(f"Job failed: {job['error']}")
                else:
                    st.success("Done.")
                    st.audio(api_client.media_url(job["result"]["lead_vocals"]))
                    st.audio(api_client.media_url(job["result"]["background_vocals"]))
