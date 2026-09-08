"""Downloads media from a URL (YouTube and hundreds of other sites via yt-dlp), so a link can
be fed through the same pipelines as an uploaded file: full video for analyze_video, or
audio-only for separate_song."""

from pathlib import Path

import yt_dlp

from backend.config import UPLOADS_DIR, VIDEOS_DIR

_COMMON_OPTS = {
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "progress_hooks": [],
    "noprogress": True,
    # Prefer clients that do not require browser cookies or a PO token on public videos.
    "extractor_args": {"youtube": {"player_client": ["web_safari", "tv_embedded"]}},
    "retries": 3,
    "fragment_retries": 3,
}


class UrlDownloadError(RuntimeError):
    pass


def download_video_from_url(url: str) -> tuple[Path, str]:
    """Returns (file_path, title). The source title (often "Song Name | Movie | Singer1,
    Singer2, Composer" for music videos) is a much more reliable identity signal than trying
    to recognize the song purely from keyframes/ASR -- callers should pass it through to the
    lyrics/singer identification step instead of discarding it."""
    ydl_opts = {
        **_COMMON_OPTS,
        "outtmpl": str(VIDEOS_DIR / "%(id)s.%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
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
            "YouTube blocked this request from the Streamlit Cloud server. "
            "Try uploading the audio/video file instead, or use a publicly accessible URL. "
            f"Details: {e}"
        ) from e


def download_audio_from_url(url: str) -> tuple[Path, str]:
    """Downloads best-quality audio only (no video track) as a .wav file, for song separation.
    Returns (file_path, title) -- see download_video_from_url's docstring on why the title
    matters for identification."""
    ydl_opts = {
        **_COMMON_OPTS,
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
            "YouTube blocked this request from the Streamlit Cloud server. "
            "Try uploading the audio file instead, or use a publicly accessible URL. "
            f"Details: {e}"
        ) from e
