# NOTE: Demucs/Whisper benefit heavily from CUDA. This image runs CPU-only unless you build
# from an nvidia/cuda base and install a CUDA-enabled torch wheel, and run the container with
# --gpus all (Linux) or the WSL2 GPU passthrough setup (Windows). For local development on this
# machine, running the backend natively (see ../run_backend.bat) is faster and simpler since it
# already has a CUDA-enabled torch installed.
FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
