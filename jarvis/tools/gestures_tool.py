"""
jarvis/tools/gestures_tool.py
Start/stop the JARVIS gesture-control window — webcam cursor control with
pinch-to-click (MODE 1). Triggered by voice/chat: "open the camera",
"gesture control", "move the mouse with my hand".
"""
import os
import subprocess
import sys
import time

# Project root (parent of the jarvis package) so `-m jarvis.camera` resolves.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _launch(project: bool = False) -> dict:
    """Open the JARVIS camera window, optionally straight into Mode 3."""
    try:
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--gestures"]
            if project:
                cmd.append("--project")
        else:
            cmd = [sys.executable, "-m", "jarvis.camera"]
            if project:
                cmd.append("--project")
        proc = subprocess.Popen(cmd, cwd=_PROJECT_ROOT, start_new_session=True)
        # Verify it actually came up instead of dying instantly.
        time.sleep(1.5)
        if proc.poll() is not None:
            return {"error": f"gesture control exited early (code {proc.returncode})"}
        return {
            "status": "gesture control opened",
            "hint": "Move your index finger to move the mouse; pinch thumb and index to click. Say 'stop gestures' to close it.",
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def start_gestures() -> dict:
    """Open the JARVIS gesture-control window."""
    return _launch(project=False)


def start_project() -> dict:
    """Open the JARVIS PROJECT canvas (Mode 3) — the Iron Man workshop."""
    return _launch(project=True)


def stop_project() -> dict:
    """Close any running JARVIS project canvas."""
    return stop_gestures()


def stop_gestures() -> dict:
    """Close any running JARVIS gesture-control window."""
    try:
        subprocess.run(["pkill", "-f", "MacOS/JARVIS --gestures"], capture_output=True, timeout=5)
        subprocess.run(["pkill", "-f", "jarvis.camera"], capture_output=True, timeout=5)
        return {"status": "gesture control closed"}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
