#!/usr/bin/env bash
# Builds a double-clickable JARVIS.app for macOS.
#
#   ./jarvis/build_app.sh
#
# It repairs/creates the project virtualenv, installs dependencies,
# generates the icon, runs PyInstaller, and ad-hoc signs the bundle
# (required to run locally on Apple Silicon).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"

echo "==> JARVIS.app build"
echo "    project root : $ROOT"

# 1. Virtualenv --------------------------------------------------------------
if [ ! -x "$PY" ]; then
    echo "==> Creating virtualenv at $VENV"
    python3 -m venv "$VENV"
fi
"$PY" -m pip install --upgrade pip --quiet

# 2. Dependencies -------------------------------------------------------------
echo "==> Installing app dependencies"
"$PY" -m pip install --quiet \
    PyQt6 pyinstaller fastapi "uvicorn[standard]" websockets python-dotenv \
    httpx requests SpeechRecognition notion-client \
    opencv-contrib-python mediapipe matplotlib \
    pyobjc-framework-Quartz pyobjc-framework-AVFoundation pyobjc-framework-ApplicationServices \
    pyobjc-framework-Vision pyobjc-framework-Foundation
# Optional mic hardware (needs `brew install portaudio` on Apple Silicon):
if ! "$PY" -m pip install --quiet pyaudio 2>/dev/null; then
    echo "    note: pyaudio not installed — for voice, run: brew install portaudio"
fi

# 3. Icons --------------------------------------------------------------------
echo "==> Generating app icons"
(cd "$ROOT" && "$PY" -m jarvis.app.make_icon --icns)

# 4. PyInstaller --------------------------------------------------------------
echo "==> Running PyInstaller (this takes a while)"
(cd "$ROOT" && "$PY" -m PyInstaller --noconfirm --clean jarvis/jarvis-app.spec)

# 5. Sign --------------------------------------------------------------
# Sign with a STABLE identity so macOS permissions (Accessibility, Camera)
# survive rebuilds. Prefer an Apple Development cert from the keychain;
# fall back to ad-hoc signing.
APP="$ROOT/dist/JARVIS.app"
IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null | awk '/Apple Development:/{print $2; exit}')"
if [ -n "$IDENTITY" ]; then
    echo "==> Signing $APP with stable identity: $IDENTITY"
    codesign --force --deep --sign "$IDENTITY" "$APP"
else
    echo "==> No stable identity found — ad-hoc signing $APP (permissions reset each rebuild)"
    codesign --force --deep --sign - "$APP"
fi

cat <<EOF

✅ Built $APP
   - double-click to launch, or move it to /Applications
   - API keys: copy your .env to ~/.jarvis/.env (the app reads it there)
   - first run: grant Microphone / Accessibility / Automation permissions
     in System Settings → Privacy & Security when prompted
EOF
