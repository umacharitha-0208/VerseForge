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
    # YouTube's default web client increasingly returns 403 on formats that need a PO token;
    # the android/ios clients serve formats that don't require one.
    "extractor_args": {"youtube": {"player_client": ["android", "ios", "web"]}},
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
        raise UrlDownloadError(f"Failed to download video from {url}: {e}") from e


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
        raise UrlDownloadError(f"Failed to download audio from {url}: {e}") from e
