import os
import subprocess
import sys
import time
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
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", port],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    for _ in range(30):
        try:
            requests.get(f"{base_url}/api/status", timeout=1).raise_for_status()
            return
        except requests.RequestException:
            time.sleep(1)

    raise RuntimeError(f"The local backend did not start at {base_url}")