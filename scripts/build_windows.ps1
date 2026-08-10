# JARVIS Windows build script.
# Run from PowerShell in the project root:
#     powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
#
# Produces dist\JARVIS\JARVIS.exe (or dist\JARVIS.exe for onefile builds).

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "==> JARVIS.exe build (Windows)"

# 1. Virtualenv ------------------------------------------------------------
$Venv = Join-Path $Root ".venv"
if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    Write-Host "==> Creating virtualenv"
    python -m venv $Venv
}
$Py = Join-Path $Venv "Scripts\python.exe"
& $Py -m pip install --upgrade pip --quiet

# 2. Dependencies -----------------------------------------------------------
Write-Host "==> Installing app dependencies"
& $Py -m pip install --quiet `
    PyQt6 pyinstaller fastapi "uvicorn[standard]" websockets python-dotenv `
    httpx requests SpeechRecognition notion-client `
    opencv-contrib-python mediapipe matplotlib

# Optional: pyaudio for microphone voice input (needs a wheel for your Python
# version; skip if it fails — STT still works via the chat window's mic).
& $Py -m pip install --quiet pyaudio 2>$null

# 3. Icons -------------------------------------------------------------------
Write-Host "==> Generating app icons"
& $Py -m jarvis.app.make_icon --ico

# 4. PyInstaller --------------------------------------------------------------
Write-Host "==> Running PyInstaller (this takes a while)"
& $Py -m PyInstaller --noconfirm --clean jarvis\jarvis-app-win.spec

Write-Host ""
Write-Host "==> Done. Run it with:"
Write-Host "    dist\JARVIS\JARVIS.exe"
