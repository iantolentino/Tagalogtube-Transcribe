"""Local speech-to-text with faster-whisper, plus TXT/SRT/VTT formatting and safe file saving.

Nothing in this module calls a paid API or a cloud service. Models are downloaded once
from Hugging Face on first use and cached in the project's models/ folder.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"            # cached Whisper models (travel with the project)
TRANSCRIPTS_DIR = BASE_DIR / "transcripts"  # default output folder

MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3"]
DEFAULT_MODEL = "small"

# Whisper uses the code "tl" for Tagalog. "Filipino" is not a separate Whisper language.
LANGUAGE_OPTIONS = {
    "Filipino/Tagalog": "tl",
    "English": "en",
    "Auto-detect": None,
}
LANGUAGE_NAMES = {"tl": "Filipino/Tagalog", "fil": "Filipino/Tagalog", "en": "English"}

# Light hint that nudges Whisper toward Taglish (Tagalog with English mixed in).
TAGLISH_PROMPT = "Ito ay usapan sa Tagalog na may halong English (Taglish)."

# Whisper writes sound tags such as [musika], [Music] or [Applause] when there is no speech.
_SOUND_TAG_RE = re.compile(r"\[[^\]]*\]")


def clean_segment_text(text: str) -> str:
    """Remove bracketed sound tags (e.g. [musika]) and tidy spacing. Returns "" if nothing is left."""
    text = _SOUND_TAG_RE.sub(" ", text or "")
    return re.sub(r"\s+", " ", text).strip()


class TranscriptionError(Exception):
    """Raised when audio cannot be transcribed into usable text."""


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptResult:
    segments: list = field(default_factory=list)
    language: str | None = None
    language_probability: float = 0.0
    duration: float = 0.0
    method: str = "Local transcription (faster-whisper)"

    @property
    def full_text(self) -> str:
        return " ".join(seg.text for seg in self.segments)


_model_cache: dict = {}


def language_name(code: str | None) -> str:
    if not code:
        return "Unknown"
    return LANGUAGE_NAMES.get(code, code)


def load_model(model_size: str = DEFAULT_MODEL, device: str = "auto"):
    """Load a faster-whisper model once per process. First use downloads it."""
    cache_key = (model_size, device)
    if cache_key not in _model_cache:
        from faster_whisper import WhisperModel  # imported lazily so the UI starts quickly

        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        _model_cache[cache_key] = WhisperModel(
            model_size,
            device=device,
            compute_type="int8",     # small memory footprint, works on CPU and GPU
            download_root=str(MODEL_DIR),
        )
    return _model_cache[cache_key]


def decode_audio_with_ffmpeg(audio_path, start=0.0, duration=None):
    """Decode a portion of any audio/video file to 16 kHz mono float32 samples.

    This avoids the PyAV (av) package entirely, which caused version errors on some PCs.
    """
    import shutil
    import subprocess

    import numpy as np

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise TranscriptionError(
            "FFmpeg was not found. Install it (winget install --id Gyan.FFmpeg -e), "
            "reopen this window, then try again."
        )
    args = [ffmpeg, "-nostdin", "-v", "error", "-i", str(audio_path), "-ss", str(start)]
    if duration is not None:
        args.extend(["-t", str(duration)])
    args.extend(["-f", "s16le", "-ac", "1", "-ar", "16000", "-"])
    proc = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0 or not proc.stdout:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise TranscriptionError(f"FFmpeg could not read this file. Details: {err or 'no audio found'}")
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe_audio(audio_path, language=None, model_size=DEFAULT_MODEL, progress=None, chunk_progress=None, _device="auto") -> TranscriptResult:
    """Transcribe a local audio or video file. `language` is "tl", "en" or None (auto-detect).

    `progress`, if given, is called with a fraction from 0.0 to 1.0 as segments are produced.
    """
    model = load_model(model_size, _device)
    prompt = TAGLISH_PROMPT if language == "tl" else None

    # Keep decoded audio bounded in memory. Whole-file decoding becomes expensive
    # for longer videos, particularly when the selected Whisper model is large.
    chunk_seconds = 5 * 60
    chunk_overlap = 2.0
    duration = _audio_duration(audio_path)
    segments = []
    offset = 0.0
    detected_language = None
    language_probability = 0.0
    while offset < duration - 0.25 or (offset == 0.0 and duration <= 0):
        chunk_duration = min(chunk_seconds, duration - offset) if duration > 0 else None
        decode_start = max(0.0, offset - chunk_overlap)
        decode_duration = chunk_duration + (offset - decode_start) if chunk_duration is not None else None
        if chunk_progress:
            chunk_progress(offset, duration, "Preparing 5-minute audio chunk")
        audio = decode_audio_with_ffmpeg(audio_path, start=decode_start, duration=decode_duration)
        if not len(audio):
            break
        segment_iter, info = model.transcribe(
            audio,
            language=language,
            task="transcribe",
            beam_size=1,             # greedy decoding is faster, especially on CPU
            vad_filter=True,          # skip long silences, reduces hallucinated text
            initial_prompt=prompt,
        )
        detected_language = detected_language or info.language
        language_probability = language_probability or float(info.language_probability or 0.0)
        chunk_length = len(audio) / 16000
        if chunk_progress:
            chunk_progress(offset, duration or chunk_length, "Transcribing chunk")
        try:
            for seg in segment_iter:
                absolute_start = decode_start + float(seg.start)
                absolute_end = decode_start + float(seg.end)
                # Overlap chunk reads to protect words at boundaries, then keep each
                # segment only in the chunk containing its midpoint.
                if offset > 0 and (absolute_start + absolute_end) / 2 < offset:
                    continue
                text = clean_segment_text(seg.text)
                if text:
                    segments.append(Segment(absolute_start, absolute_end, text))
                if progress and duration > 0:
                    progress(min(absolute_end / duration, 1.0))
        except RuntimeError as exc:
            message = str(exc).lower()
            if _device == "auto" and ("cublas" in message or "cuda" in message):
                if chunk_progress:
                    chunk_progress(0.0, duration, "GPU unavailable; restarting on CPU")
                return transcribe_audio(
                    audio_path, language, model_size, progress, chunk_progress, _device="cpu"
                )
            raise
        if chunk_duration is None:
            duration = float(info.duration or chunk_length)
        offset += chunk_duration if chunk_duration is not None else chunk_length
        if progress and duration > 0:
            progress(min(offset / duration, 1.0))

    if not segments:
        raise TranscriptionError("No speech was detected in this file, so no transcript was created.")

    return TranscriptResult(
        segments=segments,
        language=detected_language,
        language_probability=language_probability,
        duration=duration,
    )


def _audio_duration(audio_path) -> float:
    """Read media duration with ffprobe, returning 0 if it is unavailable."""
    import json
    import shutil
    import subprocess

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0.0
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(audio_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        return 0.0
    try:
        return max(0.0, float(json.loads(proc.stdout).get("format", {}).get("duration", 0)))
    except (ValueError, TypeError, json.JSONDecodeError):
        return 0.0


# ---------------------------------------------------------------- formatting

def _parts(seconds: float):
    total_ms = int(round(max(float(seconds), 0.0) * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1_000)
    return hours, minutes, secs, millis


def hms(seconds: float) -> str:
    h, m, s, _ = _parts(seconds)
    return f"{h:02d}:{m:02d}:{s:02d}"


def srt_time(seconds: float) -> str:
    h, m, s, ms = _parts(seconds)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def vtt_time(seconds: float) -> str:
    h, m, s, ms = _parts(seconds)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def build_txt(title, language_code, source, result: TranscriptResult, with_timestamps=True) -> str:
    """Build the primary plain-text transcript (UTF-8 text, returned as a Python string)."""
    lines = [
        f"Title: {title or 'Untitled'}",
        f"Language: {language_name(language_code or result.language)}",
        f"Source: {source}",
        f"Method: {result.method}",
        "",
        "TRANSCRIPT",
        "",
    ]
    for seg in result.segments:
        if with_timestamps:
            lines.append(f"[{hms(seg.start)}] {seg.text}")
        else:
            lines.append(seg.text)
    return "\n".join(lines) + "\n"


def build_srt(segments) -> str:
    blocks = []
    for i, seg in enumerate(segments, start=1):
        blocks.append(f"{i}\n{srt_time(seg.start)} --> {srt_time(seg.end)}\n{seg.text}\n")
    return "\n".join(blocks)


def build_vtt(segments) -> str:
    blocks = [f"{vtt_time(seg.start)} --> {vtt_time(seg.end)}\n{seg.text}\n" for seg in segments]
    return "WEBVTT\n\n" + "\n".join(blocks)


# ---------------------------------------------------------------- file saving

_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {
    f"LPT{i}" for i in range(1, 10)
}


def safe_filename(name: str, max_length: int = 120) -> str:
    """Make a filename that is valid on Windows and macOS/Linux. Tagalog letters are kept."""
    name = unicodedata.normalize("NFC", name or "")
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", name)   # characters Windows forbids
    name = re.sub(r"\s+", "_", name.strip())
    name = name.strip("._")
    if not name:
        name = "transcript"
    if name.upper() in _WINDOWS_RESERVED:
        name = f"_{name}"
    return name[:max_length].rstrip("._") or "transcript"


def save_transcript_files(folder, stem: str, files: dict) -> Path:
    """Save {extension: text} files sharing one unique stem. Never overwrites existing files.

    Files are written UTF-8. If a name clash happens, the stem gets _2, _3, ... appended.
    Returns the path of the .txt file. If anything fails, partly written files are removed.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    n = 1
    while True:
        candidate = stem if n == 1 else f"{stem}_{n}"
        paths = {ext: folder / f"{candidate}{ext}" for ext in files}
        if any(p.exists() for p in paths.values()):
            n += 1
            continue

        created = []
        try:
            for ext, content in files.items():
                with open(paths[ext], "x", encoding="utf-8") as fh:  # "x" = fail if exists
                    created.append(paths[ext])
                    fh.write(content)
        except FileExistsError:
            for p in created:
                p.unlink(missing_ok=True)
            n += 1
            continue
        except Exception:
            for p in created:
                p.unlink(missing_ok=True)
            raise
        return paths[".txt"]
