@echo off
rem Build the KMuted installer (needs Inno Setup 6: https://jrsoftware.org/isdl.php).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv 2>nul || python -m venv .venv
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt -r requirements-dev.txt || goto :fail
".venv\Scripts\python.exe" tools\build_installer.py || goto :fail
pause
exit /b 0
:fail
echo Build failed.
pause
exit /b 1
