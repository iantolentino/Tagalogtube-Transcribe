@echo off
title TagalogTube Transcriber - Setup
set "PYTHONUTF8=1"
cd /d "%~dp0"
set "VENV_DIR=%~dp0venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "NEED_INSTALL=0"
set "PY_CMD="
set "AUTOMATED=0"
if /i "%~1"=="--install" set "AUTOMATED=1"

echo ==================================================
echo   TagalogTube Transcriber - First-time setup
echo ==================================================
echo.

REM ---- 1. Find Python 3.9 or newer ----
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if not errorlevel 1 set "PY_CMD=py -3"
if not defined PY_CMD (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY_CMD=python"
)
if not defined PY_CMD goto :no_python
for /f "delims=" %%v in ('%PY_CMD% --version 2^>^&1') do echo Found %%v
echo.
goto :check_venv

:no_python
echo [ERROR] Python 3.9 or newer was not found on this computer.
where winget >nul 2>&1
if errorlevel 1 goto :python_manual
echo Installing Python 3.12 for this Windows user with winget. This may take a few minutes...
winget install --id Python.Python.3.12 -e --scope user --source winget --silent --accept-package-agreements --accept-source-agreements
echo.
REM Refresh PATH for this process so a just-installed Python can be used now.
set "PATH=%LocalAppData%\Programs\Python\Python312;%LocalAppData%\Programs\Python\Python312\Scripts;%PATH%"
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=python"
    goto :check_venv
)
if "%AUTOMATED%"=="1" (
    echo [ERROR] Python installation finished, but Python 3.9+ was not found on PATH.
    echo Install Python from https://www.python.org/downloads/windows/ and rerun the installer.
    exit /b 1
)
echo Python was installed. Close this window and double-click setup_windows.bat again.
echo.
pause
exit /b 1

:python_manual
echo.
echo   1. Download Python 3.11 or 3.12 from https://www.python.org/downloads/windows/
echo   2. Run the installer and tick "Add python.exe to PATH".
echo   3. Close this window and double-click setup_windows.bat again.
echo.
pause
exit /b 1

:check_venv
REM ---- 2. Create or verify the project-local virtual environment ----
if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys" >nul 2>&1
    if errorlevel 1 (
        echo The existing virtual environment is broken. Rebuilding it...
        rmdir /s /q "%VENV_DIR%"
    )
)
if not exist "%VENV_PY%" (
    echo Creating virtual environment in the "venv" folder...
    %PY_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Could not create the virtual environment.
        if "%AUTOMATED%"=="0" pause
        exit /b 1
    )
    set "NEED_INSTALL=1"
)
if not exist "%VENV_DIR%\.deps_installed" set "NEED_INSTALL=1"
"%VENV_PY%" -c "import imageio_ffmpeg" >nul 2>&1
if errorlevel 1 set "NEED_INSTALL=1"
if /i "%~1"=="--reinstall" set "NEED_INSTALL=1"

REM ---- 3. Install dependencies only when needed (no reinstall on every launch) ----
if "%NEED_INSTALL%"=="1" goto :install
echo Dependencies already installed. Skipping install.
echo (To force a fresh install, run setup_windows.bat --reinstall from Command Prompt.)
goto :verify

:install
echo.
echo Installing dependencies from requirements.txt. This can take several minutes...
"%VENV_PY%" -m pip install --upgrade pip
"%VENV_PY%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo.
    echo [ERROR] Dependency installation failed. Check your internet connection and the messages above,
    echo         then double-click setup_windows.bat again.
    if "%AUTOMATED%"=="0" pause
    exit /b 1
)
echo Making sure PyAV (av) is up to date...
"%VENV_PY%" -m pip install -U "av>=13.0"
if errorlevel 1 (
    echo [ERROR] Could not upgrade PyAV. Check your internet connection and run setup again.
    if "%AUTOMATED%"=="0" pause
    exit /b 1
)
del /q "%VENV_DIR%\.deps_installed" >nul 2>&1
echo installed> "%VENV_DIR%\.deps_installed"

:verify
REM ---- 4. Verify the packages can be imported ----
"%VENV_PY%" -c "import streamlit, faster_whisper, yt_dlp, imageio_ffmpeg" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Some required packages could not be loaded.
    echo         Open Command Prompt in this folder and run: setup_windows.bat --reinstall
    if "%AUTOMATED%"=="0" pause
    exit /b 1
)
echo All Python packages are ready.

REM ---- 5. Verify bundled FFmpeg and update yt-dlp ----
"%VENV_PY%" -m pip install -U yt-dlp
"%VENV_PY%" -c "import imageio_ffmpeg, subprocess; subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)"
if errorlevel 1 (
    echo [ERROR] The bundled FFmpeg could not run. Check the Python package install output above.
    if "%AUTOMATED%"=="0" pause
    exit /b 1
)
echo Bundled FFmpeg is installed and working.
goto :folders

:folders
if not exist "%~dp0transcripts" mkdir "%~dp0transcripts"
if not exist "%~dp0models" mkdir "%~dp0models"

echo.
echo ==================================================
echo   Setup complete!
echo   Launch the app by double-clicking run_windows.bat
echo   The Whisper model downloads on your first transcription.
echo ==================================================
echo.
    if "%AUTOMATED%"=="0" pause
exit /b 0
