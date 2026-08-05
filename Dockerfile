# Hugging Face Spaces (Docker SDK) image -- runs the FastAPI backend and Streamlit frontend
# together in one container, since a Space only exposes a single public port. The frontend
# (public, port 7860) talks to the backend (internal, port 8000) over localhost -- see
# start.sh and frontend/api_client.py's BACKEND_BASE_URL.
#
# CPU-only: HF Spaces' free tier has no GPU, so Demucs/Whisper run on CPU here (see
# backend/config.py's cuda-availability check) -- correct, just slower than local GPU dev.
FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fluidsynth \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Real General MIDI SoundFont for GuitarGPT's sample-based synthesis (see
# backend/services/soundfont_synth.py) -- same source used and verified during development.
# ~148MB; fetched at build time rather than committed to the repo.
RUN mkdir -p .tools/soundfonts && \
    curl -L -o .tools/soundfonts/FluidR3_GM.sf2 \
    https://github.com/pianobooster/fluid-soundfont/releases/download/v3.1/FluidR3_GM.sf2

COPY backend/ backend/
COPY frontend/ frontend/
COPY .streamlit/ .streamlit/
COPY start.sh .

# HF Spaces containers run as a non-root user by convention; make sure app-writable dirs exist
# and are owned correctly regardless of who the runtime user ends up being.
RUN mkdir -p data storage/uploads storage/stems storage/videos storage/generated && \
    chmod -R 777 data storage .tools && \
    chmod +x start.sh

EXPOSE 7860
CMD ["./start.sh"]
