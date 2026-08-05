# VerseForge — AI Music Production, Localization & Generative Instrument Platform

**Goal** Separate songs into stems, understand music videos across text/audio/visual
modalities, generate and localize lyrics across languages and scripts, synthesize
expressive vocal performances, and create custom playable instruments from text
descriptions — reflecting real-world creator-tooling pipelines used in music production,
song localization, and generative audio apps (e.g. Fadr, LALAL.AI).

## Input Sources

- File upload (any audio/video format — ffmpeg/Demucs handle extraction regardless of
  extension)
- Any URL yt-dlp supports (YouTube and hundreds of other sites) — no dataset training,
  everything runs on pretrained models against live user-supplied content

## Concepts & Models

- **Source separation**: Demucs `htdemucs` (4-stem: vocals/drums/bass/other) and
  `htdemucs_6s` (6-stem: +guitar/piano) — the most stems any open pretrained model
  provides
- **Lead vs. background vocal split**: pitch-salience harmonic masking (librosa `pyin`
  pitch tracking + binary harmonic-band masking) — a DSP heuristic, not a trained model
- **Transcription**: faster-whisper (GPU-accelerated)
- **Multimodal video semantic analysis**: keyframe sampling (OpenCV) + transcript +
  librosa audio features (tempo/energy/brightness) → Gemini multimodal synthesis
- **Agentic refine loop**: AutoGen (multi-agent framework) drives a generate → critique →
  revise loop for both lyrics and video analysis — replacing single-shot prompting with an
  Editor agent that self-scores and revises against a threshold, not open-ended free-form
  looping
- **Cross-lingual generation**: English / Hindi / Telugu / Punjabi, plus "same as input"
  auto-detection, with independent control over **script** (native Devanagari/Telugu/
  Gurmukhi vs. romanized/Latin phonetic transliteration)
- **Chatbot-style manual refinement**: quick-action presets (make it darker, shorter,
  more rhythmic...) + freeform chat, one LLM call per turn, separate from the automated
  critique loop
- **Text-to-instrument synthesis** (Siren / GuitarGPT / ViolinGPT): Gemini interprets a
  text description into synth parameters; additive oscillator + ADSR + filter + vibrato
  engine for generic/violin timbres, Karplus-Strong plucked-string physical model for
  guitar — rendered across a 5-octave note bank, played via an embedded QWERTY-keyboard
  web component
- **Emotional TTS**: prosody-based emotion presets (rate/pitch/volume) over Edge TTS
  neural voices; gTTS fallback for languages with no neural voice available (Punjabi)

## Tech Stack

- Python, FastAPI (backend), Streamlit (frontend)
- Demucs, faster-whisper, librosa, OpenCV, NumPy/SciPy (synthesis DSP), PyDub
- Google Gemini via `google-genai`, LlamaIndex (single-shot/multimodal calls), AutoGen /
  `ag2` (multi-agent critique loop) — Gemini reached through its OpenAI-compatible
  endpoint so AutoGen's native client works without a proxy
- edge-tts, gTTS, yt-dlp
- SQLite (persistence), FastAPI `BackgroundTasks` job queue
- n8n (workflow automation), Dockerfile + docker-compose (containerization-ready)

## Ops & Cost Involvement

*(no training pipeline, so MLflow/DVC don't apply here — the operational concerns are
inference-cost and job-orchestration, not experiment tracking)*

- **Job queue with status tracking**: `pending → running → done/error`, polled by the
  frontend, with optional `webhook_url` callbacks on completion for external automation
- **n8n integration**: backend exposes scan/inbox endpoints so n8n workflows stay to two
  node types (Schedule Trigger, HTTP Request) — all filesystem/business logic lives in
  the API, not in n8n nodes
- **LLM cost controls**: exact-match response caching (input + style + language + script)
  to skip redundant calls; merged critique+revise into one call per loop iteration
  (halves worst-case calls per generation); `REFINE_MAX_ITERATIONS=0` env var for
  single-shot mode
- **Model-availability resilience**: free-tier quota and model-deprecation issues
  surfaced and worked around live (`gemini-2.0-flash` → `gemini-flash-latest` →
  `gemini-3.1-flash-lite`) via a swappable `LLM_MODEL` env var
- **DB schema migrations**: additive column migrations (`PRAGMA table_info` diffing) so
  the SQLite schema evolves without wiping existing data

## Deliverables

- Song separation (4-stem / 6-stem) + lead/background vocal split, from file or link
- Multimodal video analysis: transcript + keyframes + music features → agentic,
  fact-checked semantic/sentiment summary
- Multi-language, multi-script lyrics generation with chatbot refinement and manual
  editing, cached for repeat requests
- Emotion-tunable TTS mixed with a song's instrumental (paired playback or spoken-word
  overlay)
- Siren / GuitarGPT / ViolinGPT: text-to-instrument playable virtual keyboard
- Full FastAPI backend + Streamlit frontend + n8n automation scaffold + Docker packaging
