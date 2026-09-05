# VerseForge

VerseForge is a multimodal AI music production platform for creators who want to separate
songs, understand music videos, generate and localize lyrics, create spoken-word mixes, and
play AI-designed instruments in one workspace.

The project combines a Streamlit user interface with a FastAPI application layer. Streamlit is
the public entrypoint. It communicates with the backend through HTTP, while the backend
coordinates audio/video processing, Gemini-powered generation, SQLite persistence, and generated
media delivery.

## What the platform does

### 1. Convert songs to stems

- Accepts uploaded audio/video files or supported URLs.
- Uses Demucs to separate vocals, drums, bass, and other instruments.
- Supports the six-stem model for vocals, drums, bass, guitar, piano, and other.
- Builds a complete instrumental mix from non-vocal stems.
- Can split an existing vocal stem into estimated lead and background vocals with pitch-aware DSP.
- Caches repeated separations using the input file hash and selected stem count.

### 2. Analyze music videos

- Accepts uploaded videos or supported video URLs.
- Extracts audio and video features from the source.
- Transcribes speech and lyrics with faster-whisper.
- Computes tempo, energy, and brightness with librosa.
- Samples visual keyframes with OpenCV.
- Sends grounded multimodal context to Gemini for singer, genre, mood, lyrics, and semantic
	interpretation.
- Uses a generate, critique, and revise loop for more consistent analysis.

### 3. Lyrics Studio

- Generates lyrics from an idea, theme, or existing text.
- Supports English, Hindi, Telugu, Punjabi, and same-as-input language generation.
- Supports native scripts and romanized output where applicable.
- Provides conversational editing for requests such as making lyrics darker, shorter, or more
	rhythmic.
- Stores generated lyrics and chat history in SQLite.
- Caches matching generation requests to reduce repeated Gemini calls.

### 4. Audio mixing and vocal performance

- Pairs generated lyrics with an existing song or instrumental.
- Converts lyrics to speech with Edge TTS or gTTS fallback.
- Provides voice, emotion, timing, and gain controls.
- Supports prosody-based emotion presets such as happy, sad, angry, excited, and calm.
- Renders a spoken vocal overlay over the instrumental with PyDub and FFmpeg-compatible tools.

### 5. GuitarGPT instrument creation

- Converts a natural-language instrument description into a playable instrument patch.
- Uses Gemini to interpret instrument family and sound characteristics.
- Renders a five-octave note bank with FluidSynth and the FluidR3 General MIDI SoundFont.
- Presents generated notes through a browser keyboard interface.
- Stores generated instruments and note files for later playback from the Library.

## How the complete system works

```text
Browser
	|
	v
Streamlit frontend (frontend/app.py and frontend/pages/)
	|
	| HTTP requests through frontend/api_client.py
	v
FastAPI backend (backend/main.py)
	|
	+--> Routers: songs, videos, lyrics, mixes, instruments, jobs, library
	|
	+--> Services: Demucs, Whisper, librosa, OpenCV, Gemini, TTS, FluidSynth
	|
	+--> SQLite database in data/app.db
	|
	+--> Uploaded and generated media in storage/
```

### Complete project flow diagram

The common path for every feature is simple: Streamlit collects input, the API creates and
tracks work, specialized services process the request, SQLite records metadata, storage holds
generated files, and Streamlit renders the completed result. A simplified visual version is
available at [verseforge_simple_flow.png](verseforge_simple_flow.png).

### Audio and video intelligence

- Demucs for source separation
- faster-whisper for transcription
- librosa for audio analysis and pitch-related processing
- OpenCV for video frame sampling
- NumPy, SoundFile, PyDub, and FFmpeg-compatible tools for media processing

### Generative AI and language

- Google Gemini API for lyrics, multimodal video analysis, and instrument interpretation
- LlamaIndex Google GenAI integration for model access
- `ag2` for the generate, critique, and revise workflow
- python-dotenv for environment configuration

### Speech and synthesis

- Edge TTS for neural text-to-speech voices
- gTTS fallback for languages without a configured Edge voice
- FluidSynth and FluidR3 GM SoundFont for sampled instrument rendering

## AI orchestration and optimization

VerseForge uses a layered orchestration design rather than sending every request directly to a
single model call:

- **LlamaIndex** manages the initial Gemini calls for single-shot text generation and
	multimodal video analysis with transcript, audio features, and keyframe images.
- **AG2 / AutoGen** drives the iterative editor workflow. An editor agent evaluates the current
	lyrics or video analysis, returns a score and issues, and produces a revision when the score is
	below the configured threshold.
- **Google Gemini** provides the language and multimodal reasoning behind the LlamaIndex and
	AutoGen calls. AutoGen reaches Gemini through its OpenAI-compatible endpoint.
- **FastAPI background jobs** coordinate these model calls with local Demucs, Whisper, TTS,
	FluidSynth, and media-processing tasks.

The orchestration is optimized to reduce unnecessary model traffic:

- Critique and revision are combined into one AutoGen response instead of using separate Critic
	and Writer calls. With the default refinement settings, the worst-case loop is reduced from
	7 calls to 4, which is approximately a 40% reduction in API calls.
- Exact-match caching reuses existing lyrics, video analyses, song separations, instrument note
	banks, and TTS mixes when the input and relevant settings are unchanged.
- Video keyframes are sent to Gemini for the initial multimodal draft, then the refinement loop
	uses the transcript, audio features, and current draft without repeatedly sending the images.
- `REFINE_MAX_ITERATIONS=0` enables single-shot generation when the faster and lower-cost path
	is preferred.

The actual savings depend on cache hit rate, selected workflow, and the number of refinement
iterations. The approximately 40% figure describes the implemented critique/revision reduction,
not a guaranteed percentage for every workload.

### Deployment

- Streamlit Community Cloud as the primary deployment target
- `packages.txt` for FFmpeg and FluidSynth system packages
- Docker is not required for this project or its Streamlit Cloud deployment.

## Project structure

```text
project2/
├── backend/
│   ├── main.py                 FastAPI application and router registration
│   ├── config.py               Environment, storage, model, and voice configuration
│   ├── db.py                   SQLite schema and persistence helpers
│   ├── schemas.py              Request and response models
│   ├── routers/                API endpoints grouped by feature
│   └── services/               Audio, video, AI, TTS, and job implementations
├── frontend/
│   ├── app.py                  Streamlit home page and backend startup
│   ├── api_client.py           Frontend-to-backend HTTP client
│   ├── backend_runtime.py      Local API bootstrap helper
│   ├── theme.py                Shared Streamlit styling
│   └── pages/                  Streamlit feature pages
├── data/                       Runtime SQLite database, created automatically
├── storage/                    Runtime uploads and generated media
├── .streamlit/config.toml      Streamlit UI configuration
├── packages.txt               Streamlit Cloud system packages
├── requirements.txt            Python dependencies
├── .env.example                Local environment template
└── README.md                   Project documentation
```

`data/` and `storage/` are runtime directories. Generated media and the SQLite database are
deployment-specific and are not source code.

## Configuration

Create a local `.env` file from `.env.example`:

```env
GEMINI_API_KEY=your-google-ai-studio-key
LLM_MODEL=gemini-flash-latest
```

Important optional settings include:

```env
BACKEND_BASE_URL=http://127.0.0.1:8000
START_LOCAL_BACKEND=1
DEMUCS_MODEL=htdemucs
WHISPER_MODEL_SIZE=base
REFINE_MAX_ITERATIONS=3
REFINE_SCORE_THRESHOLD=8
```

The Gemini key is required for lyrics generation, video semantic analysis, and instrument
creation. Song separation and other local processing can run without it.

## Run locally

From the repository root:

```bash
pip install -r requirements.txt
streamlit run frontend/app.py
```

Open `http://127.0.0.1:8501`. The Streamlit process automatically starts the FastAPI backend
on `http://127.0.0.1:8000`. The backend status endpoint is available at `/api/status` and
reports whether Gemini is configured and whether CUDA is available.

## Deploy on Streamlit Community Cloud

This project is deployed directly with Streamlit Cloud. It does not use Docker, a separate
FastAPI server, or additional launch scripts. The Streamlit entrypoint starts the FastAPI
backend internally through `frontend/backend_runtime.py`.

1. Push the repository to GitHub.
2. Open [share.streamlit.io](https://share.streamlit.io).
3. Create a new app from the repository.
4. Set the main file to `frontend/app.py`.
5. Add `GEMINI_API_KEY` under **App settings -> Secrets**.
6. Deploy the app.

No separate backend URL is required for the default deployment. The Streamlit process starts
the FastAPI backend locally in the same environment. Set `BACKEND_BASE_URL` only if the API is
hosted as a separate service.

## Project brief

### Goal

VerseForge separates songs into stems, understands music videos across text, audio, and visual
modalities, generates and localizes lyrics across languages and scripts, synthesizes expressive
vocal performances, and creates custom playable instruments from text descriptions. It is built
around real creator-tool workflows for music production, song localization, and generative audio.

### Input sources

- Uploaded audio or video files. FFmpeg and Demucs handle supported format conversion.
- URLs supported by yt-dlp, including YouTube and other compatible sites.
- No training dataset is required; the application runs pretrained models against user-supplied
	content.

### Core concepts and models

- **Source separation:** Demucs `htdemucs` provides four stems, while `htdemucs_6s` adds guitar
	and piano for six stems.
- **Vocal splitting:** librosa pitch tracking and harmonic masking estimate lead versus
	background vocals. This is a DSP heuristic, not a trained classifier.
- **Transcription:** faster-whisper transcribes speech and sung vocals.
- **Video analysis:** OpenCV keyframes, Whisper transcripts, and librosa tempo, energy, and
	brightness features are combined for Gemini multimodal synthesis.
- **Agentic refinement:** AutoGen drives a generate, critique, and revise loop with an editor
	agent that scores its output against a configured threshold.
- **Cross-language generation:** English, Hindi, Telugu, Punjabi, and same-as-input generation
	are supported with native-script or romanized output.
- **Manual refinement:** Lyrics can be edited through quick actions or free-form chat.
- **Instrument synthesis:** Gemini interprets the instrument description, then FluidSynth renders
	a five-octave note bank from the FluidR3 General MIDI SoundFont.
- **Emotional TTS:** Edge TTS uses prosody presets for rate, pitch, and volume, with gTTS as a
	fallback where a neural voice is unavailable.

### Operations and cost controls

- Background jobs move through `pending`, `running`, `done`, or `error` states while the
	frontend polls for completion.
- Optional webhook callbacks can notify external callers when jobs finish.
- Exact-match caching skips repeated work for unchanged inputs and settings.
- Critique and revision are combined into one model response, reducing the default worst-case
	refinement loop from seven calls to four, approximately 40% fewer calls.
- `REFINE_MAX_ITERATIONS=0` enables lower-cost single-shot generation.
- The `LLM_MODEL` environment variable allows the Gemini model to be changed without code
	changes as quotas and model availability evolve.
- SQLite schema migrations are additive, so new columns can be introduced without deleting
	existing application data.

### Deliverables

- Four- or six-stem song separation with lead/background vocal splitting.
- Multimodal video analysis with transcript, keyframes, music features, and semantic summary.
- Multilingual, multi-script lyrics generation with chat refinement and caching.
- Emotion-tunable TTS paired with an instrumental or mixed as a spoken-word overlay.
- GuitarGPT text-to-instrument generation with a playable virtual keyboard.
- FastAPI backend, Streamlit frontend, and direct Streamlit Community Cloud deployment.

## Runtime and deployment limitations

- Streamlit Community Cloud is CPU-only for this workload, so Demucs and Whisper may be slow.
- The first use of a model can download model weights and take longer than later requests.
- Uploaded media, generated files, and SQLite data are ephemeral on Streamlit Cloud.
- Large audio/video files can exceed free-tier memory, storage, or execution limits.
- Heavy jobs are serialized to reduce memory pressure, so simultaneous users may wait in line.
- Gemini workflows return a configuration error when `GEMINI_API_KEY` is not set.

## Safety and data handling

VerseForge processes user-provided media within the running application environment, then stores
job metadata and output paths in SQLite. Generated media is kept under `storage/`. Deployments
that require durable media should move file storage and database persistence to managed external
services.
