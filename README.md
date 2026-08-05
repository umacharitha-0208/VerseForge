---
title: VerseForge
emoji: 🎵
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# VerseForge — AI Music Production, Localization & Generative Instrument Platform

Split songs into stems, analyze music videos across text/audio/visual modalities, generate and
localize lyrics, mix spoken-word vocal performances over instrumentals, and create playable
instruments from text descriptions.

See [docs/project_brief.md](docs/project_brief.md) for the full feature/architecture writeup.

## Required secret

This Space needs a `GEMINI_API_KEY` set under **Settings → Variables and secrets** to enable
lyrics generation, video semantic analysis, and instrument creation. Without it, source
separation (Demucs) and the rest of the UI still work; anything that calls the LLM will return
a clear "not configured" error instead of crashing.

## Notes on this deployment

- **CPU only** on the free tier -- Demucs/Whisper run slower than on a local GPU machine.
  Larger jobs (6-stem separation, video analysis) may take a few minutes.
- **Ephemeral storage** by default -- generated songs/stems/videos/instruments are stored on
  local disk inside the container and are lost on a Space restart, unless persistent storage
  is enabled in Space settings.
- Backend (FastAPI) and frontend (Streamlit) run as two processes in the same container
  (`start.sh`); only the frontend's port is exposed publicly.
