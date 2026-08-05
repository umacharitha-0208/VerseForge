import streamlit as st

import api_client
from theme import apply_theme

st.set_page_config(page_title="Lyrics Studio", page_icon="✍️", layout="wide")
apply_theme()

st.title("✍️ Lyrics Studio")
st.caption(
    "Turn plain text into poetry/lyrics via an agentic generate → critique → revise loop, "
    "edit or chat-refine the result, then pair or mix it with a stored instrumental."
)

options = api_client.get_lyrics_options()
STYLE_PRESETS = options["style_presets"]
LANGUAGES = options["languages"]  # {code: display_name}
LANGUAGE_VOICES = options["language_voices"]  # {code: [[voice, engine], ...]}
SCRIPTS = options["scripts"]  # {code: display_name}
EMOTIONS = options["emotions"]
QUICK_ACTIONS = options["quick_actions"]

st.subheader("1. Generate lyrics")
title = st.text_input("Title for this piece", value="")
input_text = st.text_area(
    "Input text",
    height=150,
    placeholder="Paste or write your text here... (any language), OR paste a YouTube/song "
                "link -- it will be downloaded and transcribed for real before generating.",
)
st.caption(
    "Pasting a link automatically downloads it, isolates vocals, and transcribes the actual "
    "song (same pipeline as Video Analysis) -- it doesn't just improvise from the URL text."
)
col_style, col_lang, col_script = st.columns(3)
with col_style:
    style = st.selectbox("Style", STYLE_PRESETS + ["custom..."])
    if style == "custom...":
        style = st.text_input("Describe the custom style", value="poetic lyrics")
with col_lang:
    lang_code = st.selectbox(
        "Output language", list(LANGUAGES.keys()), format_func=lambda c: LANGUAGES[c]
    )
with col_script:
    script_code = st.selectbox(
        "Script", list(SCRIPTS.keys()), format_func=lambda c: SCRIPTS[c],
        help="Romanized writes it phonetically in Latin letters (e.g. 'Namaste, aap kaise "
             "hain?') instead of the native script -- common for casual texting.",
    )

generated_text = st.session_state.get("generated_text")
lyrics_id = st.session_state.get("lyrics_id")
refine_iterations = st.session_state.get("refine_iterations")

if st.button("Generate lyrics", type="primary"):
    if not input_text.strip():
        st.error("Input text is empty.")
    else:
        title_final = title.strip() or "Untitled"
        job_id = api_client.generate_lyrics(input_text, style, title_final, lang_code, script_code)
        spinner_msg = (
            f"Job #{job_id}: downloading & transcribing the link, then running generate → "
            "critique → revise loop..."
            if input_text.strip().lower().startswith(("http://", "https://"))
            else f"Job #{job_id}: running generate → critique → revise loop..."
        )
        with st.spinner(spinner_msg):
            job = api_client.wait_for_job(job_id, timeout=600)
        if job["status"] == "error":
            st.error(f"Job failed: {job['error']}")
        else:
            result = job["result"]
            if result.get("resolved_from_url"):
                with st.expander("Transcribed from the link (used as input instead of the raw URL)"):
                    st.text(result["resolved_input_text"])
            generated_text = result["generated_text"]
            lyrics_id = result["lyrics_id"]
            refine_iterations = result["refine_iterations"]
            st.session_state["generated_text"] = generated_text
            st.session_state["lyrics_id"] = lyrics_id
            st.session_state["refine_iterations"] = refine_iterations
            st.session_state["lyrics_lang"] = lang_code
            st.session_state["lyrics_script"] = script_code
            if result.get("cached"):
                st.info(
                    "Reused a cached result for this exact input text + style + language + "
                    "script — no API calls made."
                )

if refine_iterations:
    with st.expander(f"Refine loop trace ({len(refine_iterations)} steps)"):
        for i, it in enumerate(refine_iterations):
            header = f"**Step {i + 1}: {it['step']}**"
            if it["score"] is not None:
                header += f" — score: {it['score']}"
            st.markdown(header)
            st.text(it["content"])
            if it["critique"]:
                st.caption(f"Critique: {it['critique']}")

if generated_text and lyrics_id:
    st.divider()
    st.subheader("2. Edit the lyrics")

    shown_lang = st.session_state.get("lyrics_lang", "same_as_input")
    shown_script = st.session_state.get("lyrics_script", "native")
    st.caption(
        f"Showing lyrics generated in: **{LANGUAGES.get(shown_lang, shown_lang)}** "
        f"({SCRIPTS.get(shown_script, shown_script)})"
    )
    if lang_code != shown_lang or script_code != shown_script:
        st.info(
            f"You've selected \"{LANGUAGES[lang_code]}\" / \"{SCRIPTS[script_code]}\" above, but "
            f"the lyrics shown below are still from the \"{LANGUAGES[shown_lang]}\" / "
            f"\"{SCRIPTS[shown_script]}\" generation. Click **Generate lyrics** again to apply "
            "the new settings."
        )

    edited = st.text_area("Lyrics (editable)", value=generated_text, height=220, key="lyrics_editor")
    if st.button("Save edits"):
        api_client.update_lyrics_text(lyrics_id, edited)
        st.session_state["generated_text"] = edited
        generated_text = edited
        st.success("Saved.")

    st.caption("Not happy with it? Use a quick action or tell the chatbot what to change:")
    chip_cols = st.columns(4)
    chip_clicked = None
    for i, action in enumerate(QUICK_ACTIONS):
        with chip_cols[i % 4]:
            if st.button(action, key=f"chip_{action}"):
                chip_clicked = action

    chat_instruction = st.text_input("Or describe a custom change", key="chat_instruction")
    send_chat = st.button("Send")

    instruction = chip_clicked or (chat_instruction.strip() if send_chat and chat_instruction.strip() else None)
    if instruction:
        with st.spinner("Revising..."):
            chat_result = api_client.chat_edit_lyrics(lyrics_id, instruction)
        st.session_state["generated_text"] = chat_result["generated_text"]
        generated_text = chat_result["generated_text"]
        st.rerun()

    chat_log = api_client.get_lyrics_chat(lyrics_id)
    if chat_log:
        with st.expander(f"Chat history ({len(chat_log)} messages)"):
            for m in chat_log:
                role = "You" if m["role"] == "user" else "Assistant"
                st.markdown(f"**{role}:** {m['content'] if m['role'] == 'user' else '(revised lyrics above)'}" )

st.divider()
st.subheader("3. Combine with a stored instrumental")

songs = api_client.list_songs()
songs_with_stems = [s for s in songs if api_client.list_stems(s["id"])]

if not songs_with_stems:
    st.info("No separated songs available yet. Go to 'Convert Songs to Stems' first.")
elif not generated_text:
    st.info("Generate lyrics above first.")
else:
    song_options = {s["title"]: s["id"] for s in songs_with_stems}
    song_label = st.selectbox("Pick a song's instrumental", list(song_options.keys()))
    song_id = song_options[song_label]

    mode = st.radio(
        "How should the lyrics combine with the instrumental?",
        ["Pair for playback (text + audio side by side)", "Spoken-word TTS overlay (mixed audio)"],
    )

    if mode.startswith("Pair"):
        if st.button("Create paired playback"):
            result = api_client.pair_mix(lyrics_id, song_id)
            st.success("Paired. Read the lyrics while the instrumental plays:")
            st.text(generated_text)
            st.audio(api_client.media_url(result["instrumental"]["file_path"]))
    else:
        voice_langs = [c for c in LANGUAGES if c != "same_as_input"]
        generated_lang = st.session_state.get("lyrics_lang", "english")
        default_voice_lang = generated_lang if generated_lang in voice_langs else "english"
        tts_lang = st.selectbox(
            "Voice language (pick whichever language the lyrics actually ended up in)",
            voice_langs,
            index=voice_langs.index(default_voice_lang),
            format_func=lambda c: LANGUAGES[c],
        )
        voice_choices = LANGUAGE_VOICES.get(tts_lang, LANGUAGE_VOICES["english"])
        voice_idx = st.selectbox(
            "Voice", range(len(voice_choices)), format_func=lambda i: voice_choices[i][2]
        )
        voice, engine, gender = voice_choices[voice_idx]

        if engine == "gtts":
            st.caption(
                "This language only has a gTTS voice available (Edge TTS has no Punjabi voice) "
                "-- lower quality, no male/female choice, and emotion/prosody control isn't "
                "available on gTTS."
            )
            emotion = "neutral"
        else:
            emotion = st.selectbox("Emotion (prosody-based: adjusts rate/pitch/volume)", EMOTIONS)
        st.caption(
            "Note: this is spoken-word TTS reciting the lyrics, not real singing synthesis -- "
            "there's no melody/rhythm model available in this environment. It does read each "
            "line with a slightly different pitch and a timed pause between lines (closer to "
            "sung phrasing than one flat paragraph), but it won't follow the song's actual "
            "melody or beat."
        )

        try:
            max_duration = api_client.get_instrumental_duration(song_id)
        except Exception:
            max_duration = 300.0

        col_start, col_inst_gain, col_tts_gain = st.columns(3)
        with col_start:
            start_sec = st.slider(
                "Start instrumental at (sec)", 0.0, max(max_duration - 1, 0.0), 0.0,
                help="Skip an intro or any section you don't want before the vocal overlay begins.",
            )
        with col_inst_gain:
            inst_gain = st.slider("Instrumental volume (dB)", -30, 6, -6)
        with col_tts_gain:
            tts_gain = st.slider("Voice volume (dB)", -30, 6, 0)

        if st.button("Synthesize + mix"):
            job_id = api_client.tts_overlay_mix(
                lyrics_id, song_id, voice, engine, emotion, start_sec, inst_gain, tts_gain
            )
            with st.spinner(f"Job #{job_id}: synthesizing speech and mixing (requires internet)..."):
                job = api_client.wait_for_job(job_id)
            if job["status"] == "error":
                st.error(f"Job failed: {job['error']}")
            else:
                st.success("Mixed track ready:")
                if job["result"].get("cached"):
                    st.info("Reused an existing mix for this exact lyrics + voice + mix settings — no re-synthesis.")
                st.audio(api_client.media_url(job["result"]["file_path"]))

st.divider()
st.subheader("Previously generated lyrics")
for l in api_client.list_lyrics():
    lang_display = LANGUAGES.get(l.get("output_language", "english"), l.get("output_language", "english"))
    script_display = SCRIPTS.get(l.get("script", "native"), l.get("script", "native"))
    with st.expander(f"{l['title']} — {l['style']} — {lang_display} ({script_display}) — {l['created_at']}"):
        st.caption("Input text")
        st.text(l["input_text"])
        st.caption("Generated lyrics")
        st.text(l["generated_text"])
