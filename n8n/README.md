# n8n automation

n8n orchestrates background/batch work by calling the FastAPI backend — it does not do any
file handling itself. All filesystem work (scanning folders, downloading URLs, moving files)
happens in Python on the backend, so each n8n workflow only needs the two most stable core
node types: **Schedule Trigger** and **HTTP Request** (plus **Webhook** for completion
callbacks).

## Running n8n

```
run_n8n.bat
```

n8n requires Node.js <=22; this machine's system Node is v25 (too new), so `run_n8n.bat` runs
n8n through a **portable Node 22 runtime** at `.tools/node-v22.23.2-win-x64/` with n8n
installed locally into `.tools/n8n-app/` — no admin rights or system Node changes needed.
Sets `N8N_USER_MANAGEMENT_DISABLED=true` (skips the owner-account setup wall for this
personal/local instance). Open http://localhost:5678 once it's up.

## Importing the example workflows

```
.tools\node-v22.23.2-win-x64\node.exe .tools\n8n-app\node_modules\n8n\bin\n8n import:workflow --input=n8n/workflows/auto_separate_songs.json
.tools\node-v22.23.2-win-x64\node.exe .tools\n8n-app\node_modules\n8n\bin\n8n import:workflow --input=n8n/workflows/on_song_separation_complete.json
```

Workflow JSON files must be a top-level array (even for one workflow) with `active` set
explicitly — n8n's CLI import is strict about both. Then open the n8n UI and toggle each
workflow **Active**, or flip the `active` column directly in
`~/.n8n/database.sqlite`'s `workflow_entity` table and restart n8n — CLI import itself
doesn't activate triggers.

**Verified**: both workflows were imported and workflow 1 was activated and left running
unattended; its real Schedule Trigger fired on its own 2-minute interval, called the backend,
and a test file placed in `n8n_inbox/songs/` was picked up, separated, and moved to
`songs_processed/` — with zero manual API calls. This is genuine working automation, not
just an importable JSON file.

## Workflow 1: Auto-Separate Songs from Inbox

- **Trigger**: Schedule Trigger, every 2 minutes.
- **Action**: `POST http://127.0.0.1:8000/api/songs/separate-from-inbox` with body
  `{"webhook_url": "http://127.0.0.1:5678/webhook/song-separated"}`.

The backend scans `n8n_inbox/songs/` for audio files, kicks off a Demucs separation job for
each one found, moves the file to `n8n_inbox/songs_processed/`, and (if a job finishes) POSTs
the result to `webhook_url`.

**Usage**: drop an audio file into `n8n_inbox/songs/` and wait for the next scheduled run (or
trigger the endpoint manually with curl to test immediately).

## Workflow 2: On Song Separation Complete

- **Trigger**: Webhook, path `song-separated`.
- **Action**: a placeholder `Set` node formats a message from the payload
  (`{job_id, status, result}`). Attach a Slack/Email/Discord node after this to actually notify
  someone — this workflow is intentionally left as a stub since notification destinations are
  user-specific.

## Extending to video analysis

The backend now also exposes:
- `POST /api/videos/analyze` — upload a video file.
- `POST /api/videos/analyze-url` — `{"url": "...", "title": "..."}`, downloads via yt-dlp
  (YouTube and hundreds of other sites) then runs the same analysis pipeline.
- `POST /api/songs/separate-url` — same pattern for audio-only separation from a link.

To build a "Scheduled Video Analysis" workflow, duplicate workflow 1 and swap the HTTP
Request's URL/body for `/api/videos/analyze-url` with the link(s) you want processed — the
orchestration pattern (Schedule Trigger -> HTTP Request -> Webhook receiver) is identical.

## Every job supports webhook callbacks

Every job-creating endpoint (`/api/songs/separate`, `/api/songs/separate-url`,
`/api/songs/separate-from-inbox`, `/api/videos/analyze`, `/api/videos/analyze-url`,
`/api/lyrics/generate`, `/api/mixes/tts-overlay`) accepts an optional `webhook_url`. When the
background job finishes, the backend POSTs `{"job_id": ..., "status": "done"|"error", "result"
or "error": ...}` to that URL — point it at any n8n Webhook node to react to completions.
