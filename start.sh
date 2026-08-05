#!/bin/sh
# Runs both halves of the app in one container (required by HF Spaces, which exposes only one
# public port). Backend stays internal on 8000; frontend is the public-facing process on 7860.
set -e

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

# Give the backend a moment to bind before the frontend's first status check, rather than
# racing it -- api_client.py retries on failure anyway, but this avoids a guaranteed first-load
# error message.
sleep 3

python -m streamlit run frontend/app.py \
    --server.address 0.0.0.0 \
    --server.port 7860 \
    --server.headless true

# If Streamlit exits, bring the backend down too instead of leaving an orphaned process.
kill "$BACKEND_PID" 2>/dev/null || true
