@echo off
chcp 65001 >nul
rem Build dist\KMuted\KMuted.exe with PyInstaller.
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto deps
call tools\find_python.bat
if not defined PY goto no_python
%PY% -m venv .venv
if errorlevel 1 goto fail

:deps
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --upgrade pip
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt -r requirements-dev.txt || goto fail
".venv\Scripts\python.exe" tools\build_exe.py || goto fail
echo.
echo Готово / Done: dist\KMuted\KMuted.exe
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
