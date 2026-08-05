import json

import streamlit as st

import api_client
from theme import apply_theme

st.set_page_config(page_title="Library", page_icon="📚", layout="wide")
apply_theme()

st.title("📚 Library")

summary = api_client.library_summary()
cols = st.columns(6)
labels = [
    ("Songs", "songs"), ("Stems", "stems"), ("Videos", "videos"),
    ("Lyrics", "lyrics"), ("Mixes", "mixes"), ("Instruments", "instruments"),
]
for col, (label, key) in zip(cols, labels):
    col.metric(label, summary[key])

tab_songs, tab_videos, tab_lyrics, tab_mixes, tab_instruments = st.tabs(
    ["Songs & Stems", "Video Analyses", "Lyrics", "Mixes", "Instruments"]
)

with tab_songs:
    songs = api_client.list_songs()
    if not songs:
        st.info("No songs stored yet.")
    for song in songs:
        st.write(f"**{song['title']}**")
        for stem in api_client.list_stems(song["id"]):
            cols = st.columns([1, 3])
            cols[0].caption(stem["stem_type"])
            with cols[1]:
                st.audio(api_client.media_url(stem["file_path"]))

with tab_videos:
    videos = api_client.list_videos()
    if not videos:
        st.info("No videos analyzed yet.")
    for v in videos:
        with st.expander(v["title"]):
            for a in api_client.list_analyses(v["id"]):
                st.caption("Semantic analysis")
                st.write(a["semantic_summary"])
                st.caption("Music features")
                st.code(a["music_features_json"])

with tab_lyrics:
    for l in api_client.list_lyrics():
        with st.expander(f"{l['title']} ({l['style']})"):
            st.text(l["generated_text"])

with tab_mixes:
    mixes = api_client.list_mixes()
    if not mixes:
        st.info("No mixes created yet.")
    for m in mixes:
        st.write(f"**{m['lyrics_title']}** over **{m['song_title']} / {m['stem_type']}** — mode: `{m['mode']}`")
        if m["file_path"]:
            st.audio(api_client.media_url(m["file_path"]))
        st.divider()

with tab_instruments:
    instruments = api_client.list_instruments()
    if not instruments:
        st.info("No instruments created yet.")
    for inst in instruments:
        with st.expander(f"{inst['title']} — {inst['created_at']}"):
            st.caption("Description")
            st.text(inst["description"])
            st.caption("Params")
            st.json(json.loads(inst["params_json"]))
