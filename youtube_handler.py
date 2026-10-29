"""YouTube helpers built on yt-dlp: video info, existing captions, and audio download.

Use this only with videos you own or have permission to process. Captions are preferred
when YouTube provides them, because they are faster and are already provided by the creator
or by YouTube.
"""

from __future__ import annotations

import glob
import html
import os
import re
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadError

from transcriber import Segment

_YT_RE = re.compile(
    r"^(https?://)?((www|m|music)\.)?(youtube\.com/(watch|shorts|live|embed)|youtu\.be/)",
    re.IGNORECASE,
)
# Caption languages to request, in order of preference, for each language choice.
_CAPTION_LANGS = {"tl": ("tl", "fil"), "en": ("en",), None: ("tl", "fil", "en")}
_TIMING_RE = re.compile(
    r"(\d{1,2}:)?(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{1,2}:)?(\d{2}):(\d{2})[.,](\d{3})"
)
_TAG_RE = re.compile(r"<[^>]+>")


class YouTubeError(Exception):
    """Raised for problems reading or downloading a YouTube video."""


def is_youtube_url(url: str) -> bool:
    return bool(_YT_RE.match((url or "").strip()))


def _clean(exc: Exception) -> str:
    return str(exc).replace("ERROR: ", "").strip()


def _opts(**extra) -> dict:
    base = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,      # a single video even if the link includes a playlist
        "skip_download": True,
    }
    base.update(extra)
    return base


def fetch_video_info(url: str) -> dict:
    """Return the video's id, title and canonical URL without downloading anything."""
    try:
        with yt_dlp.YoutubeDL(_opts()) as ydl:
            info = ydl.extract_info(url.strip(), download=False)
    except DownloadError as exc:
        raise YouTubeError(
            "Could not read this YouTube link. Check that the video is public and the link is correct. "
            f"Details: {_clean(exc)}"
        ) from exc
    if not info:
        raise YouTubeError("YouTube returned no information for this link.")
    return {
        "id": info.get("id") or "video",
        "title": info.get("title") or info.get("id") or "untitled",
        "duration": info.get("duration"),
        "url": info.get("webpage_url") or url.strip(),
    }


def parse_vtt(text: str) -> list:
    """Convert WebVTT caption text into Segment objects.

    Automatic captions repeat text as lines roll in. Exact repeats and rolling
    extensions are merged so the transcript stays readable.
    """
    segments: list = []
    start = None
    end = None
    lines: list = []

    def commit():
        if start is None:
            return
        cleaned = html.unescape(_TAG_RE.sub("", " ".join(lines)))
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            return
        if segments:
            prev = segments[-1]
            if cleaned == prev.text or prev.text.startswith(cleaned):
                return
            if cleaned.startswith(prev.text):
                segments[-1] = Segment(prev.start, end, cleaned)
                return
        segments.append(Segment(start, end, cleaned))

    def to_seconds(h, m, s, ms):
        hours = int(h[:-1]) if h else 0
        return hours * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    for raw in text.splitlines():
        line = raw.strip()
        match = _TIMING_RE.search(line)
        if match:
            commit()
            start = to_seconds(match.group(1), match.group(2), match.group(3), match.group(4))
            end = to_seconds(match.group(5), match.group(6), match.group(7), match.group(8))
            lines = []
        elif not line:
            commit()
            start = None
            lines = []
        elif start is not None:
            lines.append(line)
    commit()
    return segments


def download_captions(url: str, out_dir, language=None):
    """Try to fetch existing captions for the requested language.

    Returns a dict {"language", "kind", "segments"} or None if no usable captions exist.
    Manual captions are preferred over automatic ones.
    """
    langs = _CAPTION_LANGS.get(language, _CAPTION_LANGS[None])
    out_dir = Path(out_dir)
    opts = _opts(
        writesubtitles=True,
        writeautomaticsub=True,
        subtitleslangs=list(langs),
        subtitlesformat="vtt",
        outtmpl=str(out_dir / "%(id)s.%(ext)s"),
    )
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url.strip(), download=True)
    except DownloadError:
        return None
    if not info:
        return None

    manual = set(info.get("subtitles") or {})
    requested = info.get("requested_subtitles") or {}

    candidates = []
    for lang in langs:
        path = (requested.get(lang) or {}).get("filepath")
        if path and os.path.exists(path):
            rank = 0 if lang in manual else 1
            candidates.append((rank, langs.index(lang), lang, path))

    if not candidates:  # fallback: look for any VTT file that was written
        for path in glob.glob(str(out_dir / "*.vtt")):
            parts = Path(path).suffixes
            lang = parts[-2][1:] if len(parts) >= 2 else "unknown"
            candidates.append((2, 0, lang, path))
    if not candidates:
        return None

    _, _, lang, path = min(candidates)
    with open(path, encoding="utf-8", errors="replace") as fh:
        segments = parse_vtt(fh.read())
    if not segments:
        return None
    return {
        "language": lang,
        "kind": "manual" if lang in manual else "automatic",
        "segments": segments,
    }


def download_audio(url: str, out_dir, progress=None) -> Path:
    """Download the best audio-only stream into out_dir and return its path.

    No conversion is done here. faster-whisper decodes the original container itself.
    """
    opts = _opts(
        skip_download=False,
        format="bestaudio/best",
        outtmpl=str(Path(out_dir) / "%(id)s.%(ext)s"),
        progress_hooks=[lambda event: progress(event) if progress else None],
    )
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url.strip(), download=True)
            downloaded = info.get("requested_downloads") or []
            paths = [Path(item["filepath"]) for item in downloaded if item.get("filepath")]
            path = next((candidate for candidate in paths if candidate.exists()), None)
            if path is None:
                path = Path(ydl.prepare_filename(info))
    except DownloadError as exc:
        raise YouTubeError(
            "Could not download the audio for this video. Make sure it is public and not age- or region-restricted. "
            f"Details: {_clean(exc)}"
        ) from exc
    if not path.exists():
        raise YouTubeError("The audio download finished, but the file could not be found.")
    if path.stat().st_size == 0:
        raise YouTubeError(f"The downloaded audio file is empty: {path}")
    return path
