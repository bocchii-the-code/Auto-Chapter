@echo off
setlocal

REM Switch to this script's directory
cd /d %~dp0

REM If a virtual environment .venv exists, activate it
if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
)

REM Start local Web UI (FastAPI backend + browser)
python run_web_ui.py

pause
