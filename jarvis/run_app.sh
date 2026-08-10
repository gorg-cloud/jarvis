#!/usr/bin/env bash
# Runs the JARVIS desktop app in development (no .app bundle needed).
# Usage: ./jarvis/run_app.sh [--hidden]
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
PY="$ROOT/.venv/bin/python"

if [ ! -x "$PY" ]; then
    echo "No working virtualenv at $ROOT/.venv — run ./jarvis/build_app.sh first." >&2
    exit 1
fi

cd "$ROOT"
exec "$PY" -m jarvis.app "$@"
