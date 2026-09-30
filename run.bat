@echo off
rem Start KMuted from source (creates .venv on first run).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [KMuted] First run: creating virtual environment...
  py -3.12 -m venv .venv 2>nul || python -m venv .venv
  if errorlevel 1 (
    echo Python 3.10+ not found. Install it from https://www.python.org/downloads/
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Dependency installation failed.
    pause
    exit /b 1
  )
)
start "" ".venv\Scripts\pythonw.exe" -m kmuted %*
