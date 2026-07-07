# One-shot setup for Flow State.
# Creates the Python environment and downloads the speech models.
# Run from this folder:   powershell -ExecutionPolicy Bypass -File setup.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "==> Creating Python 3.12 virtual environment (.venv)..." -ForegroundColor Cyan
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv venv --python 3.12 .venv
    uv pip install --python .venv -r requirements.txt
} else {
    Write-Host "uv not found; falling back to the py launcher + pip." -ForegroundColor Yellow
    py -3.12 -m venv .venv
    & ".venv\Scripts\python.exe" -m pip install --upgrade pip
    & ".venv\Scripts\python.exe" -m pip install -r requirements.txt
}

if (-not (Test-Path "models")) { New-Item -ItemType Directory models | Out-Null }

$moonshine = "models\sherpa-onnx-moonshine-base-en-int8"
if (-not (Test-Path $moonshine)) {
    Write-Host "==> Downloading Moonshine speech model (~60 MB download)..." -ForegroundColor Cyan
    $url = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-moonshine-base-en-int8.tar.bz2"
    curl.exe -L -o "models\moonshine.tar.bz2" $url
    tar -xjf "models\moonshine.tar.bz2" -C "models"
    Remove-Item "models\moonshine.tar.bz2"
} else {
    Write-Host "==> Moonshine model already present, skipping." -ForegroundColor DarkGray
}

$vad = "models\silero_vad.onnx"
if (-not (Test-Path $vad)) {
    Write-Host "==> Downloading Silero VAD model..." -ForegroundColor Cyan
    $vurl = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"
    curl.exe -L -o $vad $vurl
} else {
    Write-Host "==> Silero VAD already present, skipping." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "Done. Start it with:  .\run.bat" -ForegroundColor Green
Write-Host "(Sound cues and the desktop icon are generated on first launch.)" -ForegroundColor DarkGray
