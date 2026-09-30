@echo off
rem Build dist\KMuted\KMuted.exe with PyInstaller.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv 2>nul || python -m venv .venv
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt -r requirements-dev.txt || goto :fail
".venv\Scripts\python.exe" tools\build_exe.py || goto :fail
echo.
echo Done: dist\KMuted\KMuted.exe
pause
exit /b 0
:fail
echo Build failed.
pause
exit /b 1
