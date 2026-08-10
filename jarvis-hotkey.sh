#!/bin/zsh
# JARVIS voice trigger. Bind a global hotkey to this script.
# Modes (set $JARVIS_MODE or pass a flag):
#   once            — single-shot (default for hotkey)
#   conversational  — always-listening follow-up (no wake word)
#   wake-word       — wait for "jarvis" then listen
cd /Users/gorg/.gemini/antigravity/scratch/jarvis
exec ./.venv/bin/python -m jarvis.voice --once
