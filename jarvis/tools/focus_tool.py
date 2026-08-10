"""
jarvis/tools/focus_tool.py
Real focus mode: quits the distracting apps, keeps them closed with an
enforcement loop while the session runs, and restores them when it ends.

Tools:
  - focus.start {minutes, apps}   — start a focus session
  - focus.stop {}                 — restore apps immediately
  - focus.status {}               — remaining time + blocked apps
"""
import os
import signal
import subprocess
import threading
import time

DEFAULT_BLOCK = [
    "Safari", "Google Chrome", "Messages", "Slack", "Discord",
    "Instagram", "TikTok", "Netflix",
]

_state = {
    "active": False,
    "end": 0.0,
    "minutes": 0,
    "apps": [],
    "lock": threading.Lock(),
}


def _notify(title: str, message: str) -> None:
    try:
        script = f'display notification "{message}" with title "{title}"'
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    except Exception:
        pass


def _quit_app(app: str) -> None:
    """Quit an app by name (no-op if it isn't running)."""
    try:
        script = f'tell application "{app}" to quit'
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=6)
    except Exception:
        pass


def _open_app(app: str) -> None:
    try:
        subprocess.run(["open", "-a", app], capture_output=True, timeout=6)
    except Exception:
        pass


def start_focus(minutes: float = 25, apps: list = None) -> dict:
    """Start a focus session: quit the listed apps and keep them closed."""
    minutes = max(1.0, float(minutes or 25))
    block_list = [a.strip() for a in (apps or DEFAULT_BLOCK) if a and a.strip()]
    if not block_list:
        block_list = list(DEFAULT_BLOCK)

    with _state["lock"]:
        if _state["active"]:
            return {
                "status": "already_active",
                "remaining_min": round((_state["end"] - time.time()) / 60.0, 1),
                "apps": list(_state["apps"]),
            }
        _state.update(active=True, end=time.time() + minutes * 60.0,
                      minutes=minutes, apps=block_list)

    for app in block_list:
        _quit_app(app)

    threading.Thread(target=_enforce_loop, daemon=True).start()
    _notify("JARVIS Focus", f"Focus on for {int(minutes)} min. Blocking: {', '.join(block_list[:3])}")
    return {
        "status": "started",
        "minutes": minutes,
        "blocked": block_list,
        "hint": "These apps are closed and will be kept closed until the session ends. Say 'stop focus' to restore them.",
    }


def _enforce_loop() -> None:
    """Daemon loop: re-quit blocked apps until the session ends."""
    while True:
        with _state["lock"]:
            active = _state["active"]
            end = _state["end"]
            apps = list(_state["apps"])
        if not active:
            return
        if time.time() >= end:
            stop_focus()
            return
        for app in apps:
            _quit_app(app)
        time.sleep(8)


def stop_focus() -> dict:
    """End the session and restore the blocked apps."""
    with _state["lock"]:
        if not _state["active"]:
            return {"status": "not_active"}
        apps = list(_state["apps"])
        _state["active"] = False
        _state["apps"] = []
    for app in apps:
        _open_app(app)
    _notify("JARVIS Focus", "Focus session over. Apps restored.")
    return {"status": "stopped", "restored": apps}


def focus_status() -> dict:
    """Remaining time and blocked apps."""
    with _state["lock"]:
        if not _state["active"]:
            return {"status": "inactive"}
        remaining = max(0.0, _state["end"] - time.time())
        return {
            "status": "active",
            "remaining_min": round(remaining / 60.0, 1),
            "minutes": _state["minutes"],
            "apps": list(_state["apps"]),
        }
