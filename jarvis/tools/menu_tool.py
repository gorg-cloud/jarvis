"""
jarvis/tools/menu_tool.py
Opens/closes the JARVIS menu interface — the Stark-Industries window with
the big pulsing arc reactor, latest news and the current Spotify track.

Triggered by voice/chat: "open menu".
"""
import os
import subprocess
import sys

# Project root (parent of the jarvis package) so `-m jarvis.menu` resolves.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def open_menu() -> dict:
    """Open the JARVIS menu window."""
    try:
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--menu"]
        else:
            cmd = [sys.executable, "-m", "jarvis.menu"]
        subprocess.Popen(cmd, cwd=_PROJECT_ROOT, start_new_session=True)
        return {"status": "menu opened", "hint": "Say 'close menu' to dismiss it"}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def close_menu() -> dict:
    """Close any running JARVIS menu window."""
    try:
        subprocess.run(["pkill", "-f", "MacOS/JARVIS --menu"], capture_output=True, timeout=5)
        subprocess.run(["pkill", "-f", "jarvis.menu"], capture_output=True, timeout=5)
        return {"status": "menu closed"}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
