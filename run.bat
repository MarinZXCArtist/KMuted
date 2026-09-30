@echo off
chcp 65001 >nul
rem Start KMuted from source. The first start installs Python (if missing) and the libraries.
setlocal
cd /d "%~dp0"
set "VENV_PY=.venv\Scripts\python.exe"
if exist "%VENV_PY%" goto deps

echo [KMuted] Первый запуск: подготовка займёт 2-5 минут, дальше KMuted будет стартовать сразу.
echo [KMuted] First start: setup takes 2-5 minutes, later starts are instant.
call tools\find_python.bat
if not defined PY goto no_python
%PY% -m venv .venv
if errorlevel 1 goto venv_failed

:deps
rem install the libraries on the first start and whenever requirements.txt changes
fc /b requirements.txt .venv\installed-requirements.txt >nul 2>&1
if not errorlevel 1 goto launch
echo [KMuted] Устанавливаю библиотеки, нужен интернет... / Installing libraries...
"%VENV_PY%" -m pip install --disable-pip-version-check -q --upgrade pip
"%VENV_PY%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto deps_failed
copy /y requirements.txt .venv\installed-requirements.txt >nul
echo [KMuted] Готово! Запускаю... / Done! Starting...

:launch
start "" ".venv\Scripts\pythonw.exe" -m kmuted %*
exit /b 0

:no_python
echo.
echo [KMuted] Не нашёл Python 3.10-3.13 и не смог поставить его сам.
echo Скачайте Python 3.12 с python.org, при установке отметьте "Add python.exe to PATH",
echo потом снова запустите run.bat.
echo [KMuted] Python 3.10-3.13 not found. Install Python 3.12 from python.org,
echo tick "Add python.exe to PATH" and run run.bat again.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1

:venv_failed
echo [KMuted] Не удалось создать окружение Python. / Could not create the Python environment.
pause
exit /b 1

:deps_failed
echo.
echo [KMuted] Не удалось установить библиотеки. Проверьте интернет и запустите run.bat ещё раз.
echo [KMuted] Could not install the libraries. Check your internet and run run.bat again.
pause
exit /b 1
