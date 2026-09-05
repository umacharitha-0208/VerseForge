FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fluidsynth \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p .tools/soundfonts && \
    curl -L --fail -o .tools/soundfonts/FluidR3_GM.sf2 \
    https://github.com/pianobooster/fluid-soundfont/releases/download/v3.1/FluidR3_GM.sf2

COPY backend/ backend/
COPY frontend/ frontend/
COPY .streamlit/ .streamlit/
COPY README.md .env.example ./
COPY start.sh .

RUN mkdir -p data storage/uploads storage/stems storage/videos storage/generated && \
    chmod -R 777 data storage .tools && \
    chmod +x start.sh

EXPOSE 7860
CMD ["./start.sh"]