import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
STEMS_DIR = STORAGE_DIR / "stems"
VIDEOS_DIR = STORAGE_DIR / "videos"
GENERATED_DIR = STORAGE_DIR / "generated"

for d in (UPLOADS_DIR, STEMS_DIR, VIDEOS_DIR, GENERATED_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Directories the media-serving endpoint is allowed to read from.
MEDIA_ALLOWED_ROOTS = [STORAGE_DIR]

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "app.db"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-flash-latest")

# Gemini's OpenAI-compatible endpoint, used so AutoGen (which speaks the OpenAI client
# protocol) can call Gemini directly without a separate proxy.
GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

DEMUCS_MODEL = os.environ.get("DEMUCS_MODEL", "htdemucs")
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "base")

# Portable FluidSynth binary + General MIDI SoundFont, used for GuitarGPT's sample-based
# instrument synthesis -- real recorded samples instead of hand-rolled DSP, since the latter
# can't produce a convincingly realistic instrument timbre on its own.
FLUIDSYNTH_DLL_DIR = BASE_DIR / ".tools" / "fluidsynth" / "fluidsynth-v2.5.7-win10-x64-cpp11" / "bin"
SOUNDFONT_PATH = BASE_DIR / ".tools" / "soundfonts" / "FluidR3_GM.sf2"

STEM_NAMES = ["vocals", "drums", "bass", "other"]

# htdemucs_6s additionally isolates guitar and piano -- the most stems any open pretrained
# model provides. Finer categories (brass, strings, synth, choir, sitar, etc.) aren't
# available from any public model; that granularity is proprietary tech.
DEMUCS_MODELS = {
    "4": {"name": "htdemucs", "stems": ["vocals", "drums", "bass", "other"]},
    "6": {"name": "htdemucs_6s", "stems": ["vocals", "drums", "bass", "guitar", "piano", "other"]},
}
# 4-stem (htdemucs) instead of 6-stem (htdemucs_6s) by default -- smaller model, less memory
# and compute per job, which matters on a memory-constrained shared host (e.g. HF Spaces' free
# tier). Users who want guitar/piano stems can still explicitly pick "6" per request.
DEFAULT_STEM_COUNT = "4"

# Agentic refine-loop defaults
REFINE_MAX_ITERATIONS = int(os.environ.get("REFINE_MAX_ITERATIONS", "3"))
REFINE_SCORE_THRESHOLD = int(os.environ.get("REFINE_SCORE_THRESHOLD", "8"))

BACKEND_HOST = os.environ.get("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8000"))
BACKEND_BASE_URL = os.environ.get("BACKEND_BASE_URL", f"http://{BACKEND_HOST}:{BACKEND_PORT}")

# Folder n8n's schedule-triggered workflow watches for new songs to auto-separate.
N8N_INBOX_DIR = BASE_DIR / "n8n_inbox"
N8N_INBOX_SONGS_DIR = N8N_INBOX_DIR / "songs"
N8N_INBOX_SONGS_PROCESSED_DIR = N8N_INBOX_DIR / "songs_processed"
for d in (N8N_INBOX_SONGS_DIR, N8N_INBOX_SONGS_PROCESSED_DIR):
    d.mkdir(parents=True, exist_ok=True)

# --- Lyrics: languages, voices, emotion ------------------------------------------------

SUPPORTED_LANGUAGES = {
    "same_as_input": "Same as input language",
    "english": "English",
    "hindi": "Hindi (हिन्दी)",
    "telugu": "Telugu (తెలుగు)",
    "punjabi": "Punjabi (ਪੰਜਾਬੀ)",
}

# Each voice is (voice_id, engine, gender). Deliberately just ONE curated voice per gender per
# language -- not a technical voice-ID picker -- since the app only needs "male" or "female",
# not a menu of regional variants. Edge-TTS has no Punjabi voice at all, so Punjabi falls back
# to gTTS -- lower quality, and gTTS has no rate/pitch/volume controls (no emotion presets) or
# separate male/female voice choice.
#
# Note: these are generic neural TTS voices, not any real singer's voice -- labeling a
# synthetic voice with a real person's name (e.g. a specific celebrity singer) would be
# misleading, so voices are only ever labeled by gender in the UI.
LANGUAGE_VOICES = {
    "english": [("en-US-GuyNeural", "edge", "Male"), ("en-US-JennyNeural", "edge", "Female")],
    "hindi": [("hi-IN-MadhurNeural", "edge", "Male"), ("hi-IN-SwaraNeural", "edge", "Female")],
    "telugu": [("te-IN-MohanNeural", "edge", "Male"), ("te-IN-ShrutiNeural", "edge", "Female")],
    "punjabi": [("pa", "gtts", "Default")],
}

# Prosody-based emotion approximation (rate/volume/pitch) for edge-tts. This is not true
# emotional TTS (no emotion-conditioned model is available in this environment) -- it's a
# documented heuristic: speeding up + raising pitch reads as "happy/excited", slowing down +
# lowering pitch reads as "sad/calm", etc. Only applies to the "edge" engine; gTTS ignores it.
EMOTION_PRESETS = {
    "neutral": {"rate": "+0%", "volume": "+0%", "pitch": "+0Hz"},
    "happy": {"rate": "+10%", "volume": "+0%", "pitch": "+15Hz"},
    "sad": {"rate": "-15%", "volume": "-10%", "pitch": "-15Hz"},
    "angry": {"rate": "+15%", "volume": "+10%", "pitch": "+5Hz"},
    "excited": {"rate": "+20%", "volume": "+5%", "pitch": "+20Hz"},
    "calm": {"rate": "-10%", "volume": "-5%", "pitch": "-5Hz"},
}
