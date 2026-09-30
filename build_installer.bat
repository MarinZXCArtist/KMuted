@echo off
chcp 65001 >nul
rem Build dist\KMuted-Setup-<version>.exe (installs Inno Setup 6 with winget if it is missing).
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto inno
call tools\find_python.bat
if not defined PY goto no_python
%PY% -m venv .venv
if errorlevel 1 goto fail

:inno
set "HAVE_ISCC="
where iscc >nul 2>&1 && set "HAVE_ISCC=1"
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "HAVE_ISCC=1"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "HAVE_ISCC=1"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "HAVE_ISCC=1"
if defined HAVE_ISCC goto deps
where winget >nul 2>&1 || goto deps
echo [KMuted] Inno Setup 6 не найден - ставлю через winget... / Installing Inno Setup 6...
winget install -e --id JRSoftware.InnoSetup --silent --accept-package-agreements --accept-source-agreements

:deps
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --upgrade pip
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt -r requirements-dev.txt || goto fail
".venv\Scripts\python.exe" tools\build_installer.py || goto fail
pause
exit /b 0

:no_python
echo Python 3.10-3.13 не найден / not found: https://www.python.org/downloads/windows/
pause
exit /b 1

:fail
echo Сборка не удалась / Build failed.
pause
exit /b 1
