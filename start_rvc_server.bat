@echo off
rem ------------------------------------------------------------------
rem  KMuted: local RVC server for custom voice-changer models (.pth)
rem  First start installs rvc-python into .\rvc_env (needs Python 3.10,
rem  downloads ~2-3 GB). Put each model in its own folder:
rem    %APPDATA%\KMuted\voices\rvc\<ModelName>\model.pth (+ .index)
rem ------------------------------------------------------------------
setlocal
cd /d "%~dp0"
set "MODELS=%APPDATA%\KMuted\voices\rvc"
if exist "%~dp0data\voices\rvc" set "MODELS=%~dp0data\voices\rvc"
if not exist "%MODELS%" mkdir "%MODELS%"
set "PY=rvc_env\Scripts\python.exe"

if not exist "%PY%" (
  echo [KMuted] Installing RVC server, this takes a while...
  py -3.10 -m venv rvc_env
  if errorlevel 1 (
    echo Python 3.10 is required: https://www.python.org/downloads/release/python-31011/
    pause
    exit /b 1
  )
  rem omegaconf 2.0.6, needed by fairseq, does not install with pip 24.1+
  "%PY%" -m pip install "pip<24.1"
  where nvidia-smi >nul 2>&1 && (
    echo [KMuted] NVIDIA GPU found: installing CUDA build of PyTorch
    "%PY%" -m pip install torch==2.1.1+cu118 torchaudio==2.1.1+cu118 --index-url https://download.pytorch.org/whl/cu118
  )
  "%PY%" -m pip install rvc-python
  if errorlevel 1 (
    echo rvc-python installation failed. See the messages above.
    pause
    exit /b 1
  )
)

set "DEVICE=cpu:0"
"%PY%" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" >nul 2>&1 && set "DEVICE=cuda:0"
echo [KMuted] Models folder: %MODELS%
echo [KMuted] Device: %DEVICE%   Keep this window open while using RVC voices.
"%PY%" -m rvc_python api -p 5050 -md "%MODELS%" -de %DEVICE%
pause
