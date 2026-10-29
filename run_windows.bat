@echo off
title TagalogTube Transcriber
set "PYTHONUTF8=1"
cd /d "%~dp0"
set "VENV_PY=%~dp0venv\Scripts\python.exe"

REM ---- 1. Is Python installed on this computer? ----
set "HAS_PY="
where py >nul 2>&1 && set "HAS_PY=1"
where python >nul 2>&1 && set "HAS_PY=1"
if not defined HAS_PY goto :no_python

REM ---- 2. Is the project's virtual environment present? ----
if not exist "%VENV_PY%" goto :not_setup

REM ---- 3. Can that environment still start? ----
"%VENV_PY%" -c "import sys" >nul 2>&1
if errorlevel 1 goto :broken_env

REM ---- 4. Are the required packages installed? ----
"%VENV_PY%" -c "import streamlit, faster_whisper, yt_dlp" >nul 2>&1
if errorlevel 1 goto :not_setup

REM ---- 5. Start the app with the project's Python ----
echo Starting TagalogTube Transcriber...
echo.
echo   The app opens at http://localhost:8501 in your browser.
echo   Keep this window open while you use the app.
echo   To stop the app, close this window or press Ctrl+C.
echo.
echo (Waiting for the server to start...)
timeout /t 6 /nobreak >nul
start "" http://localhost:8501
"%VENV_PY%" -m streamlit run "%~dp0app.py" --server.address localhost --server.port 8501 --server.headless true --browser.gatherUsageStats false
if errorlevel 1 (
    echo.
    echo [ERROR] The app stopped with an error. Read the messages above.
    echo If port 8501 is already in use, close the other program that uses it and try again.
)
pause
exit /b 0

:no_python
echo [ERROR] Python was not found on this computer.
echo.
echo   1. Install Python 3.11 or 3.12 from https://www.python.org/downloads/windows/
echo   2. Tick "Add python.exe to PATH" during installation.
echo   3. Double-click setup_windows.bat, then run_windows.bat.
echo.
pause
exit /b 1

:not_setup
echo [SETUP NEEDED] The project is not fully set up on this computer yet.
echo.
echo   Double-click setup_windows.bat once to create the environment and install
echo   the required packages. Then double-click run_windows.bat again.
echo.
pause
exit /b 1

:broken_env
echo [ERROR] The project's Python environment cannot start.
echo         Python may have been uninstalled or moved since setup.
echo.
echo   1. Make sure Python 3.11 or 3.12 is installed (tick "Add python.exe to PATH").
echo   2. Double-click setup_windows.bat to rebuild the environment.
echo.
pause
exit /b 1