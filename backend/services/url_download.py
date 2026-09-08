"""Downloads media from a URL (YouTube and hundreds of other sites via yt-dlp), so a link can
be fed through the same pipelines as an uploaded file: full video for analyze_video, or
audio-only for separate_song."""

import base64
import os
import tempfile
from pathlib import Path

import yt_dlp

from backend.config import UPLOADS_DIR, VIDEOS_DIR

_COMMON_OPTS = {
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "progress_hooks": [],
    "noprogress": True,
    # Let the installed yt-dlp release select its current compatible YouTube clients.
    # Hard-coding clients becomes brittle as YouTube changes player responses.
    "retries": 3,
    "fragment_retries": 3,
}


def _youtube_options() -> dict:
    """Add an optional private Netscape cookie file supplied through deployment secrets."""
    options = dict(_COMMON_OPTS)
    encoded_cookies = os.environ.get("YOUTUBE_COOKIES_B64", "").strip()
    if encoded_cookies:
        try:
            cookie_path = Path(tempfile.gettempdir()) / "verseforge-youtube-cookies.txt"
            cookie_path.write_bytes(base64.b64decode(encoded_cookies, validate=True))
            options["cookiefile"] = str(cookie_path)
        except (ValueError, OSError) as exc:
            raise UrlDownloadError("YOUTUBE_COOKIES_B64 is not valid base64 cookie data") from exc
    return options


class UrlDownloadError(RuntimeError):
    pass


def download_video_from_url(url: str) -> tuple[Path, str]:
    """Returns (file_path, title). The source title (often "Song Name | Movie | Singer1,
    Singer2, Composer" for music videos) is a much more reliable identity signal than trying
    to recognize the song purely from keyframes/ASR -- callers should pass it through to the
    lyrics/singer identification step instead of discarding it."""
    ydl_opts = {
        **_youtube_options(),
        "outtmpl": str(VIDEOS_DIR / "%(id)s.%(ext)s"),
        # Do not require MP4/M4A streams: YouTube may expose only webm or separate
        # adaptive streams for the selected player client.
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            dest_path = Path(ydl.prepare_filename(info))
            if not dest_path.exists():
                dest_path = dest_path.with_suffix(".mp4")
            if not dest_path.exists():
                raise UrlDownloadError(f"Downloaded file not found at expected path: {dest_path}")
            return dest_path, (info.get("title") or "")
    except yt_dlp.utils.DownloadError as e:
        raise UrlDownloadError(
            "YouTube requires bot verification for this server. Configure a valid private "
            "YOUTUBE_COOKIES_B64 secret on the backend, or upload the audio/video file instead. "
            f"Details: {e}"
        ) from e


def download_audio_from_url(url: str) -> tuple[Path, str]:
    """Downloads best-quality audio only (no video track) as a .wav file, for song separation.
    Returns (file_path, title) -- see download_video_from_url's docstring on why the title
    matters for identification."""
    ydl_opts = {
        **_youtube_options(),
        "outtmpl": str(UPLOADS_DIR / "%(id)s.%(ext)s"),
        "format": "bestaudio/best",
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            dest_path = Path(ydl.prepare_filename(info)).with_suffix(".wav")
            if not dest_path.exists():
                raise UrlDownloadError(f"Downloaded file not found at expected path: {dest_path}")
            return dest_path, (info.get("title") or "")
    except yt_dlp.utils.DownloadError as e:
        raise UrlDownloadError(
            "YouTube requires bot verification for this server. Configure a valid private "
            "YOUTUBE_COOKIES_B64 secret on the backend, or upload the audio file instead. "
            f"Details: {e}"
        ) from e
