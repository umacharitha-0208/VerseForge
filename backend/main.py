from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import GEMINI_API_KEY
from backend.db import init_db
from backend.routers import instruments, jobs, library, lyrics, mixes, songs, videos
from backend.services.url_download import youtube_cookies_configured

app = FastAPI(title="VerseForge API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

app.include_router(songs.router)
app.include_router(videos.router)
app.include_router(lyrics.router)
app.include_router(mixes.router)
app.include_router(jobs.router)
app.include_router(library.router)
app.include_router(instruments.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "verseforge-api"}


@app.get("/api/status")
def status():
    try:
        import torch
        gpu_available = torch.cuda.is_available()
    except ImportError:
        gpu_available = False
    return {
        "llm_configured": bool(GEMINI_API_KEY),
        "gpu_available": gpu_available,
        "youtube_cookies_configured": youtube_cookies_configured(),
    }
