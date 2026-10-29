"""TagalogTube Transcriber: local Streamlit web app (http://localhost:8501).

Run with run_windows.bat, or manually:  streamlit run app.py
"""

from __future__ import annotations

import shutil
import tempfile
import threading
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

import streamlit as st

from transcriber import (
    DEFAULT_MODEL,
    LANGUAGE_OPTIONS,
    MODEL_DIR,
    MODEL_SIZES,
    TRANSCRIPTS_DIR,
    TranscriptionError,
    TranscriptResult,
    build_srt,
    build_txt,
    build_vtt,
    language_name,
    safe_filename,
    save_transcript_files,
    transcribe_audio,
)
from youtube_handler import (
    YouTubeError,
    download_audio,
    download_captions,
    fetch_video_info,
    is_youtube_url,
)

SUPPORTED_TYPES = [
    "mp3", "wav", "m4a", "aac", "ogg", "oga", "opus", "flac",
    "webm", "mp4", "m4v", "mov", "mkv",
]

st.set_page_config(page_title="TagalogTube Transcriber", page_icon="🎙️", layout="wide")

_active_temp_dirs: set[Path] = set()
_active_temp_dirs_lock = threading.Lock()


@contextmanager
def job_temp_dir():
    with tempfile.TemporaryDirectory(prefix="tagalogtube_") as tmp:
        path = Path(tmp).resolve()
        with _active_temp_dirs_lock:
            _active_temp_dirs.add(path)
        try:
            yield tmp
        finally:
            with _active_temp_dirs_lock:
                _active_temp_dirs.discard(path)


def abandoned_temp_dirs():
    """List completed or abandoned TagalogTube temporary folders."""
    with _active_temp_dirs_lock:
        active = set(_active_temp_dirs)
    return [path for path in Path(tempfile.gettempdir()).glob("tagalogtube_*")
            if path.is_dir() and path.resolve() not in active]


def folder_size(path: Path) -> int:
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())


def run_pipeline(kind: str, url: str | None, upload, opts: dict) -> None:
    """Run one transcription job. Saves the TXT only after a successful transcript exists."""
    language_code = LANGUAGE_OPTIONS[opts["language_label"]]
    out_dir = Path(opts["out_dir"]).expanduser()

    with st.status("Working on your transcript...", expanded=True) as status:
        try:
            with job_temp_dir() as tmp:
                audio_path = None
                bar = st.progress(0.0, text="Waiting...")
                progress_detail = st.empty()
                started_at = time.monotonic()

                def on_progress(fraction: float) -> None:
                    elapsed = int(time.monotonic() - started_at)
                    progress_detail.caption(
                        f"Audio processed: {fraction:.0%} • Elapsed: {elapsed // 60}m {elapsed % 60:02d}s"
                    )

                def on_chunk_progress(offset: float, duration: float, phase: str) -> None:
                    elapsed = int(time.monotonic() - started_at)
                    current = min(offset, duration)
                    chunk_number = int(offset // 300) + 1
                    chunk_count = max(1, int((duration + 299) // 300))
                    chunk_end = min(offset + 300, duration)
                    bar.progress(
                        min(current / duration, 1.0) if duration > 0 else 0.0,
                        text=f"{phase} {chunk_number}/{chunk_count}: {current / 60:.1f} / {duration / 60:.1f} min",
                    )
                    progress_detail.caption(
                        f"Audio processed: {current / duration:.0%} • Elapsed: {elapsed // 60}m {elapsed % 60:02d}s"
                        if duration > 0 else f"{phase} • Elapsed: {elapsed // 60}m {elapsed % 60:02d}s"
                    )
                    status.write(
                        f"{phase}: chunk {chunk_number}/{chunk_count}, "
                        f"{current / 60:.1f}–{chunk_end / 60:.1f} minutes. "
                        f"Source: {audio_path}. FFmpeg reads each chunk into memory; separate chunk files are not saved."
                    )

                def finish_progress() -> None:
                    bar.progress(1.0, text="Transcription complete")
                    elapsed = int(time.monotonic() - started_at)
                    progress_detail.caption(
                        f"Audio processed: 100% • Elapsed: {elapsed // 60}m {elapsed % 60:02d}s"
                    )

                def on_download_progress(event: dict) -> None:
                    if event.get("status") == "downloading":
                        downloaded = event.get("downloaded_bytes", 0)
                        total = event.get("total_bytes") or event.get("total_bytes_estimate")
                        if total:
                            fraction = min(downloaded / total, 1.0)
                            bar.progress(fraction, text=f"Downloading YouTube audio... {fraction:.0%}")
                            progress_detail.caption(
                                f"Downloaded {downloaded / 1_000_000:.1f} / {total / 1_000_000:.1f} MB"
                            )
                        else:
                            bar.progress(0.0, text="Downloading YouTube audio...")
                            progress_detail.caption(
                                f"Downloaded {downloaded / 1_000_000:.1f} MB"
                            )
                    elif event.get("status") == "finished":
                        bar.progress(1.0, text="YouTube audio downloaded")
                        progress_detail.caption("Download complete. Preparing 5-minute audio chunks...")

                if kind == "youtube":
                    status.write("Reading video information...")
                    info = fetch_video_info(url)
                    title, source = info["title"], info["url"]
                    result = None

                    if opts["use_captions"]:
                        status.write("Checking for existing captions...")
                        cap = download_captions(source, tmp, language_code)
                        if cap:
                            result = TranscriptResult(
                                segments=cap["segments"],
                                language=cap["language"],
                                method=f"YouTube {cap['kind']} captions",
                            )
                            status.write(f"Using {cap['kind']} captions.")

                    if result is None:
                        status.write("Downloading audio...")
                        audio_path = download_audio(source, tmp, on_download_progress)
                        status.write(f"YouTube audio downloaded to temporary file: {audio_path}")
                        status.write(
                            f"Chunk processing workspace: {Path(tmp)}. "
                            "FFmpeg extracts five-minute ranges from the downloaded audio into memory."
                        )
                        status.write("Loading the model and transcribing. The first run of a model downloads it.")
                        result = transcribe_audio(audio_path, language_code, opts["model"], on_progress, on_chunk_progress)
                        finish_progress()
                else:
                    title = Path(upload.name).stem
                    source = f"Uploaded file: {upload.name}"
                    audio_path = Path(tmp) / f"input{Path(upload.name).suffix.lower()}"
                    audio_path.write_bytes(upload.getvalue())
                    status.write(f"Uploaded media copied to temporary file: {audio_path}")
                    status.write(
                        f"Chunk processing workspace: {Path(tmp)}. "
                        "FFmpeg extracts five-minute ranges from the uploaded media into memory."
                    )
                    status.write("Loading the model and transcribing. The first run of a model downloads it.")
                    result = transcribe_audio(audio_path, language_code, opts["model"], on_progress, on_chunk_progress)
                    finish_progress()

                status.write("Saving files...")
                txt = build_txt(title, result.language, source, result, with_timestamps=opts["timestamps"])
                files = {".txt": txt}
                if opts["save_extra"]:
                    files[".srt"] = build_srt(result.segments)
                    files[".vtt"] = build_vtt(result.segments)

                txt_path = save_transcript_files(out_dir, safe_filename(title), files)

            st.session_state["result"] = {
                "title": title,
                "language": language_name(result.language),
                "method": result.method,
                "txt": txt,
                "txt_path": str(txt_path),
                "stem": txt_path.stem,
                "srt": files.get(".srt"),
                "vtt": files.get(".vtt"),
            }
            status.update(label="Transcript complete", state="complete", expanded=False)

        except (YouTubeError, TranscriptionError) as exc:
            st.session_state["result"] = None
            status.update(label="Could not finish", state="error")
            st.error(str(exc))
        except Exception as exc:  # unexpected: show a clear message and the details
            st.session_state["result"] = None
            status.update(label="Something went wrong", state="error")
            st.error(f"Unexpected error: {exc}")
            with st.expander("Technical details"):
                st.code(traceback.format_exc())


def render_result() -> None:
    result = st.session_state.get("result")
    if not result:
        return

    st.success(f"Saved to: {result['txt_path']}")
    st.subheader(result["title"])
    st.caption(f"Language: {result['language']}  •  Method: {result['method']}")
    st.text_area("Transcript", value=result["txt"], height=420)

    cols = st.columns(3)
    cols[0].download_button(
        "Download TXT",
        data=result["txt"].encode("utf-8"),
        file_name=f"{result['stem']}.txt",
        mime="text/plain; charset=utf-8",
        type="primary",
    )
    if result["srt"]:
        cols[1].download_button(
            "Download SRT",
            data=result["srt"].encode("utf-8"),
            file_name=f"{result['stem']}.srt",
            mime="application/x-subrip; charset=utf-8",
        )
    if result["vtt"]:
        cols[2].download_button(
            "Download VTT",
            data=result["vtt"].encode("utf-8"),
            file_name=f"{result['stem']}.vtt",
            mime="text/vtt; charset=utf-8",
        )


# ------------------------------------------------------------------ page layout

st.title("🎙️ TagalogTube Transcriber")
st.caption("Local transcription for Filipino/Tagalog, English and Taglish. No API keys, no cloud services.")

if st.session_state.get("result") and st.button("Transcribe a new video", type="primary", key="new_transcription"):
    st.session_state.pop("result", None)
    st.session_state.pop("youtube_url", None)
    st.session_state.pop("uploaded_media", None)
    st.rerun()

with st.sidebar:
    st.header("Settings")
    model_size = st.selectbox(
        "Whisper model",
        MODEL_SIZES,
        index=MODEL_SIZES.index(DEFAULT_MODEL),
        help="Larger models are more accurate but slower and need more memory. 'small' is a good starting point. "
             "Each model downloads once on first use.",
    )
    language_label = st.selectbox(
        "Language",
        list(LANGUAGE_OPTIONS),
        index=0,
        help="Filipino/Tagalog is the default. Auto-detect works for mixed or unknown audio.",
    )
    out_dir = st.text_input(
        "Output folder",
        value=str(TRANSCRIPTS_DIR),
        help="Where TXT files are saved. Relative paths are relative to the project folder. Created if missing.",
    )
    use_captions = st.checkbox(
        "Use YouTube captions when available",
        value=True,
        help="Faster and often more accurate. Used only when YouTube has a caption track for the chosen language.",
    )
    timestamps = st.checkbox("Include timestamps in the TXT", value=True)
    save_extra = st.checkbox("Also save SRT and VTT subtitle files", value=False)

    with st.expander("Temporary downloads and cache"):
        st.caption(f"Temporary video/audio files: {tempfile.gettempdir()}\\tagalogtube_*")
        st.caption("Job files are removed automatically when transcription ends. This button removes leftover job folders.")
        st.caption(f"Whisper models (kept for reuse): {MODEL_DIR}")
        stale_dirs = abandoned_temp_dirs()
        if stale_dirs:
            for folder in stale_dirs:
                size_mb = folder_size(folder) / (1024 * 1024)
                st.write(f"{folder} — {size_mb:.1f} MB")
            if st.button("Delete completed temporary files", key="cleanup_temp"):
                removed = 0
                for folder in stale_dirs:
                    try:
                        shutil.rmtree(folder)
                        removed += 1
                    except OSError as exc:
                        st.warning(f"Could not remove {folder}: {exc}")
                st.success(f"Deleted {removed} temporary folder(s). Whisper models and transcripts were kept.")
        else:
            st.caption("No completed temporary folders to delete.")

opts = {
    "model": model_size,
    "language_label": language_label,
    "out_dir": out_dir.strip() or str(TRANSCRIPTS_DIR),
    "use_captions": use_captions,
    "timestamps": timestamps,
    "save_extra": save_extra,
}

consent = st.checkbox(
    "I own this content or have permission to process it.",
    help="Only transcribe content you are allowed to process. Respect YouTube's Terms of Service and creators' rights.",
)
if not consent:
    st.info("Tick the permission box above to enable transcription.")

tab_yt, tab_file = st.tabs(["YouTube link", "Upload audio or video"])

with tab_yt:
    url = st.text_input("YouTube URL", placeholder="https://www.youtube.com/watch?v=...", key="youtube_url")
    if st.button("Transcribe YouTube video", type="primary", disabled=not consent, key="btn_yt"):
        if not url or not is_youtube_url(url):
            st.error("Please enter a valid YouTube link, for example https://www.youtube.com/watch?v=...")
        else:
            run_pipeline("youtube", url, None, opts)

with tab_file:
    upload = st.file_uploader("Audio or video file", type=SUPPORTED_TYPES, key="uploaded_media")
    if st.button(
        "Transcribe uploaded file",
        type="primary",
        disabled=(not consent) or upload is None,
        key="btn_file",
    ):
        run_pipeline("upload", None, upload, opts)

render_result()
