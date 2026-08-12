"""Shared renderer for text-to-instrument pages ('describe it, play it on a keyboard') --
currently only GuitarGPT uses this, but it's kept generic so a future instrument page just
fixes the synthesis family and its branding rather than duplicating this UI."""

import json

import streamlit as st
import streamlit.components.v1 as components

import api_client
from theme import apply_theme

KEY_ORDER = "1234567890QWERTYUIOPASDFGHJKLZXCVBNM"  # 36 keys = 3 octaves per window


def render_gpt_page(family: str, page_title: str, icon: str, tagline: str) -> None:
    st.set_page_config(page_title=page_title, page_icon=icon, layout="wide")
    apply_theme()

    st.title(f"{icon} {page_title}")
    st.caption(tagline)

    session_key = f"gpt_instrument_id_{family}"

    st.subheader("1. Describe an instrument")
    title = st.text_input("Title", value="", key=f"title_{family}")
    description = st.text_area(
        "Description",
        height=100,
        placeholder="Describe the sound you want...",
        key=f"description_{family}",
    )

    if st.button("Create Instrument", type="primary", key=f"create_{family}"):
        if not description.strip():
            st.error("Description is empty.")
        else:
            title_final = title.strip() or "Untitled Instrument"
            job_id = api_client.create_instrument(description.strip(), title_final, family=family)
            with st.spinner(f"Job #{job_id}: interpreting description and synthesizing notes..."):
                job = api_client.wait_for_job(job_id, timeout=120)
            if job["status"] == "error":
                st.error(f"Job failed: {job['error']}")
            else:
                st.session_state[session_key] = job["result"]["instrument_id"]
                st.success(f"Created '{title_final}'. Scroll down to play it.")
                if job["result"].get("cached"):
                    st.info("Reused an existing instrument for this exact description — no API call or re-render made.")

    st.divider()
    st.subheader("2. Play an instrument")

    all_instruments = api_client.list_instruments()
    instruments = [i for i in all_instruments if i.get("family", "generic") == family]

    if not instruments:
        st.info("No instruments created yet.")
    else:
        options = {f"{i['title']} (#{i['id']})": i["id"] for i in instruments}
        default_id = st.session_state.get(session_key)
        default_label = next((k for k, v in options.items() if v == default_id), list(options.keys())[0])
        label = st.selectbox(
            "Instrument", list(options.keys()), index=list(options.keys()).index(default_label), key=f"select_{family}"
        )
        instrument_id = options[label]

        data = api_client.get_instrument_notes(instrument_id)
        with st.expander("Synth parameters (interpreted from the description)"):
            st.json(json.loads(data["instrument"]["params_json"]))

        notes_map = {n["midi"]: api_client.media_url(n["file_path"]) for n in data["notes"]}
        midi_low, midi_high = data["midi_low"], data["midi_high"]

        html = f"""
        <div style="font-family: monospace; color: #eee; background:#111; padding: 16px; border-radius: 8px;">
          <div style="margin-bottom: 10px;">
            <button id="oct-down" style="padding:6px 14px; margin-right:8px;">Octave &minus;</button>
            <button id="oct-up" style="padding:6px 14px;">Octave +</button>
            <span id="oct-label" style="margin-left: 16px;"></span>
          </div>
          <div id="keyboard" style="display:flex; flex-wrap: wrap; gap: 4px;"></div>
          <div style="margin-top:10px; opacity:0.7; font-size: 12px;">
            Click this box, then play with your computer keyboard: 1-9 0 Q-P A-L Z-M.
          </div>
        </div>
        <script>
          const notesMap = {json.dumps(notes_map)};
          const keyOrder = "{KEY_ORDER}";
          const midiLow = {midi_low};
          const midiHigh = {midi_high};
          let baseMidi = midiLow;

          const noteNames = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"];
          function noteName(midi) {{
            return noteNames[midi % 12] + (Math.floor(midi / 12) - 1);
          }}

          const audioCache = {{}};
          function getAudio(midi) {{
            if (!notesMap[midi]) return null;
            if (!audioCache[midi]) {{
              audioCache[midi] = new Audio(notesMap[midi]);
            }}
            return audioCache[midi];
          }}

          function playMidi(midi) {{
            const a = getAudio(midi);
            if (!a) return;
            a.currentTime = 0;
            a.play();
            const el = document.getElementById("key-" + midi);
            if (el) {{
              el.style.background = "#e63946";
              setTimeout(() => {{ el.style.background = "#333"; }}, 150);
            }}
          }}

          function renderKeyboard() {{
            const kb = document.getElementById("keyboard");
            kb.innerHTML = "";
            for (let i = 0; i < keyOrder.length; i++) {{
              const midi = baseMidi + i;
              const key = keyOrder[i];
              const div = document.createElement("div");
              div.id = "key-" + midi;
              div.style = "width:52px; height:52px; background:#333; border-radius:6px; " +
                "display:flex; flex-direction:column; align-items:center; justify-content:center; " +
                "cursor:pointer; user-select:none;" + (midi > midiHigh || midi < midiLow ? "opacity:0.25;" : "");
              div.innerHTML = "<b>" + key + "</b><span style='font-size:10px;'>" +
                (midi >= midiLow && midi <= midiHigh ? noteName(midi) : "") + "</span>";
              if (midi >= midiLow && midi <= midiHigh) {{
                div.onclick = () => playMidi(midi);
              }}
              kb.appendChild(div);
            }}
            document.getElementById("oct-label").innerText =
              "Notes " + noteName(baseMidi) + " to " + noteName(Math.min(baseMidi + keyOrder.length - 1, midiHigh));
          }}

          document.getElementById("oct-up").onclick = () => {{
            baseMidi = Math.min(baseMidi + 12, midiHigh);
            renderKeyboard();
          }};
          document.getElementById("oct-down").onclick = () => {{
            baseMidi = Math.max(baseMidi - 12, midiLow);
            renderKeyboard();
          }};

          window.addEventListener("keydown", (e) => {{
            const idx = keyOrder.indexOf(e.key.toUpperCase());
            if (idx === -1) return;
            const midi = baseMidi + idx;
            if (midi >= midiLow && midi <= midiHigh) playMidi(midi);
          }});

          renderKeyboard();
        </script>
        """
        components.html(html, height=260, scrolling=False)

    st.divider()
    st.subheader("Previously created instruments")
    for inst in instruments:
        with st.expander(f"{inst['title']} — {inst['created_at']}"):
            st.caption("Description")
            st.text(inst["description"])
            st.caption("Params")
            st.json(json.loads(inst["params_json"]))
