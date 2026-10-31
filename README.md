# TagalogTube Transcriber

A free, local Windows app for transcribing YouTube videos and audio/video files. It runs transcription on your computer with faster-whisper and saves transcripts as plain text. No API key or cloud transcription account is needed.

## Quick install on Windows

Open **Command Prompt** and paste this command:

```powershell
curl.exe -fsSL https://raw.githubusercontent.com/iantolentino/Tagalogtube-Transcribe/main/install.ps1 -o "%TEMP%\tagalogtube-install.ps1" && powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%TEMP%\tagalogtube-install.ps1"
``` 

The installer downloads the app into `%USERPROFILE%\Tagalogtube-Transcribe`, installs Python for the current Windows user with WinGet if needed, installs the app's dependencies (including a bundled FFmpeg executable), waits for the local server, and then opens <http://localhost:8501> in your browser. FFmpeg does not require WinGet or a system PATH change. Administrator access is not normally required. Keep the terminal window open while using the app. The first setup and first model download can take a while. The landing page's **USE THE TOOL** button copies this same command.

To install manually, download this repository, run `setup_windows.bat` once, then run `run_windows.bat`.

## Deploy the landing page to Vercel

The landing page and matching microphone favicon are in `public/`. The root `vercel.json` forces the **Other** framework preset, disables the build step, and serves only the static files in `public/`, so Vercel does not run the Python transcription app. Import the repository with the Root Directory set to `./` (the repository root); no subfolder selection is needed. The **USE THE TOOL** button copies the Windows installer command and explains how to run it in Command Prompt.

## Use the app

1. Choose a Whisper model and language in the sidebar. **tiny** and **base** are faster; larger models may be more accurate but take longer and use more memory.
2. Confirm that you own the content or have permission to process it.
3. Paste a YouTube URL, or upload an audio/video file.
4. Select **Transcribe** and wait for the download and transcription progress.
5. Download the transcript from the page. TXT is saved to `transcripts` by default; SRT and VTT can be enabled in the sidebar.

YouTube captions can be used when available. If YouTube rate-limits caption requests, the app attempts local audio transcription instead. This fallback takes longer.

## Supported inputs

YouTube video links, or uploaded files in MP3, WAV, M4A, AAC, OGG, OPUS, FLAC, WEBM, MP4, M4V, MOV, and MKV formats.

The local transcription path decodes audio in five-minute chunks, uses a small overlap at chunk boundaries, and combines the timestamps into one transcript. Speed depends on your computer, selected model, and whether a working compatible GPU is available. Tiny is the fastest model, with lower accuracy than larger models.

## Files, downloads, and cache

- Transcripts are saved in `transcripts` (or the output folder selected in the sidebar).
- Downloaded Whisper models are kept in `models` so they do not need to be downloaded each time.
- YouTube audio and uploaded media are placed in a temporary `tagalogtube_*` folder and normally deleted automatically when the transcription job ends.
- The sidebar's **Temporary downloads and cache** section shows locations and provides **Delete completed temporary files** for leftover job folders. Active transcription folders are protected from this cleanup. Whisper models and transcripts are not deleted by that button.
- Streamlit's **Clear cache** command clears Streamlit-managed cache. It does not remove Whisper models or transcripts.

## Requirements

- Windows 10 or later
- Python 3.9 or newer (Python 3.11 or 3.12 recommended)
- FFmpeg (bundled with the `imageio-ffmpeg` Python package)
- Internet access for initial dependency/model downloads and YouTube processing

## Troubleshooting

| Issue | What to try |
|---|---|
| Setup says Python is missing | Install Python and enable **Add Python to PATH**, then run setup again. |
| FFmpeg is missing | Run `setup_windows.bat` again. It installs and verifies the bundled FFmpeg dependency without WinGet. |
| YouTube returns HTTP 429 | YouTube is rate-limiting requests. Wait before retrying, or disable caption lookup and use local audio transcription. |
| GPU error mentions `cublas64_12.dll` | The app retries on CPU. This works more slowly; choose tiny or base for speed. |
| Transcription appears slow | Check the displayed stage and chunk progress. Long videos on CPU may take a long time even with tiny. |
| Port 8501 is already in use | Close the other app using that port, then restart TagalogTube. |

## Responsible use

Only transcribe content you own or have permission to process, and follow the relevant platform terms and copyright rules. Spotify offline downloads are encrypted and are not supported as input files; use an audio file provided for download by the podcast publisher instead.

## Project files

- `app.py` — Streamlit user interface
- `transcriber.py` — faster-whisper processing and transcript formats
- `youtube_handler.py` — YouTube metadata, captions, and audio download
- `setup_windows.bat` — first-time environment setup
- `run_windows.bat` — launches the local app
- `install.ps1` — one-command Windows installer used by the curl command above
