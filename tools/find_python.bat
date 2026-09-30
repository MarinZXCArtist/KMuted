@echo off
rem Sets PY to a command that runs Python 3.10-3.13; installs Python 3.12 with winget if none is found.
rem Used by run.bat, build.bat and build_installer.bat:  call tools\find_python.bat
set "PY="
call :search
if defined PY goto :eof
where winget >nul 2>&1
if errorlevel 1 goto :eof
echo [KMuted] Python не найден - ставлю Python 3.12 через winget, это пара минут...
echo [KMuted] Python not found - installing Python 3.12 with winget...
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
call :search
goto :eof

:search
for %%V in (3.12 3.11 3.13 3.10) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=py -%%V"
  )
)
if defined PY goto :eof
rem freshly installed Python is not on PATH until the next login: look in the usual folders
for %%D in ("%LOCALAPPDATA%\Programs\Python\Python312" "%LOCALAPPDATA%\Programs\Python\Python311" "%LOCALAPPDATA%\Programs\Python\Python313" "%LOCALAPPDATA%\Programs\Python\Python310" "%ProgramFiles%\Python312" "%ProgramFiles%\Python311") do (
  if not defined PY if exist "%%~D\python.exe" set PY="%%~D\python.exe"
)
if defined PY goto :eof
rem "python" on PATH, but not the Microsoft Store placeholder
python -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=python"
goto :eof
