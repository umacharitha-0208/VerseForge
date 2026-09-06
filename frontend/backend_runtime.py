import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests


def ensure_backend(base_url: str) -> None:
    """Start the local API for Streamlit Cloud when no external API is configured."""
    parsed = urlparse(base_url)
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        return

    try:
        requests.get(f"{base_url}/api/status", timeout=1).raise_for_status()
        return
    except requests.RequestException:
        pass

    if os.environ.get("START_LOCAL_BACKEND", "1").lower() in {"0", "false", "no"}:
        return

    port = str(parsed.port or 8000)
    project_root = Path(__file__).resolve().parent.parent
    log_path = Path(os.environ.get("BACKEND_LOG_PATH", "/tmp/verseforge-backend.log"))
    log_file = log_path.open("a", encoding="utf-8")
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", port],
        cwd=project_root,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )

    for _ in range(30):
        try:
            requests.get(f"{base_url}/api/status", timeout=1).raise_for_status()
            log_file.close()
            return
        except requests.RequestException:
            time.sleep(1)

    log_file.close()
    details = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
    raise RuntimeError(f"The local backend did not start at {base_url}. Backend log:\n{details}")