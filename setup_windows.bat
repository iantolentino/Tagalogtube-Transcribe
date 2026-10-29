@echo off
title TagalogTube Transcriber - Setup
set "PYTHONUTF8=1"
cd /d "%~dp0"
set "VENV_DIR=%~dp0venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "NEED_INSTALL=0"
set "PY_CMD="

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
echo Installing Python 3.12 with winget. This may take a few minutes...
winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
echo.
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
        pause
        exit /b 1
    )
    set "NEED_INSTALL=1"
)
if not exist "%VENV_DIR%\.deps_installed" set "NEED_INSTALL=1"
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
    pause
    exit /b 1
)
echo Making sure PyAV (av) is up to date...
"%VENV_PY%" -m pip install -U "av>=13.0"
if errorlevel 1 (
    echo [ERROR] Could not upgrade PyAV. Check your internet connection and run setup again.
    pause
    exit /b 1
)
del /q "%VENV_DIR%\.deps_installed" >nul 2>&1
echo installed> "%VENV_DIR%\.deps_installed"

:verify
REM ---- 4. Verify the packages can be imported ----
"%VENV_PY%" -c "import streamlit, faster_whisper, yt_dlp" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Some required packages could not be loaded.
    echo         Open Command Prompt in this folder and run: setup_windows.bat --reinstall
    pause
    exit /b 1
)
echo All Python packages are ready.

REM ---- 5. Update yt-dlp and install FFmpeg and Node.js if missing ----
"%VENV_PY%" -m pip install -U yt-dlp
call :ensure_tool ffmpeg Gyan.FFmpeg "FFmpeg"
call :ensure_tool node OpenJS.NodeJS.LTS "Node.js"
goto :folders

:ensure_tool
REM %~1 = command name, %~2 = winget package id, %~3 = display name
where %~1 >nul 2>&1
if not errorlevel 1 (
    echo %~3 found.
    goto :eof
)
where winget >nul 2>&1
if errorlevel 1 (
    echo [WARNING] %~3 was not found, and winget is not available on this computer.
    echo   Install %~3 manually, then run setup_windows.bat again.
    goto :eof
)
echo %~3 was not found. Installing it with winget. Windows may ask for permission...
winget install --id %~2 -e --silent --accept-package-agreements --accept-source-agreements
where %~1 >nul 2>&1
if errorlevel 1 (
    echo [WARNING] %~3 was installed, but this window cannot see it yet.
    echo   Close this window, then run setup_windows.bat again.
) else (
    echo %~3 installed.
)
goto :eof

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
pause