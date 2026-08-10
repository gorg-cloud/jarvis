"""
jarvis/tools/system_extras.py
Volume, brightness, Do Not Disturb, battery, timers.
"""
import subprocess
import threading
import time as _time
from datetime import datetime


def _osa(script: str, timeout: int = 10) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "applescript failed")
    return r.stdout.strip()


def set_volume(level: int) -> dict:
    """Set system volume 0-100."""
    level = max(0, min(100, int(level)))
    try:
        _osa(f"set volume output volume {level}")
        return {"volume": level, "status": "ok"}
    except Exception as e:
        return {"volume": level, "error": str(e)}


def get_volume() -> dict:
    try:
        v = _osa("output volume of (get volume settings)")
        muted = _osa("output muted of (get volume settings)")
        return {"volume": int(v), "muted": muted.lower() == "true"}
    except Exception as e:
        return {"error": str(e)}


def mute() -> dict:
    try:
        _osa("set volume output muted true")
        return {"muted": True, "status": "ok"}
    except Exception as e:
        return {"error": str(e)}


def unmute() -> dict:
    try:
        _osa("set volume output muted false")
        return {"muted": False, "status": "ok"}
    except Exception as e:
        return {"error": str(e)}


def set_brightness(level: float) -> dict:
    """Display brightness 0.0-1.0. Requires brightness CLI or AppleScript fallback."""
    level = max(0.0, min(1.0, float(level)))
    # Try the `brightness` homebrew CLI first
    import shutil
    if shutil.which("brightness"):
        try:
            subprocess.run(["brightness", str(level)], check=True, capture_output=True, timeout=5)
            return {"brightness": level, "method": "cli", "status": "ok"}
        except Exception:
            pass
    return {"brightness": level, "error": "Install `brightness` CLI: brew install brightness"}


def toggle_dnd(state: bool) -> dict:
    """
    Toggle macOS Focus / Do Not Disturb via shortcuts.
    Best-effort: requires a 'Toggle DND' shortcut. Returns guidance if not found.
    """
    try:
        # Try triggering via Control Center is not scriptable directly — use shortcuts
        # User must create a shortcut named "Toggle DND" once.
        subprocess.run(
            ["shortcuts", "run", "Toggle DND"],
            capture_output=True, text=True, timeout=10
        )
        return {"dnd": "toggled", "status": "ok"}
    except subprocess.CalledProcessError as e:
        return {
            "dnd": "unavailable",
            "error": "Create a Shortcut named 'Toggle DND' that toggles Focus, then retry.",
            "detail": e.stderr.strip(),
        }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def battery_status() -> dict:
    """Battery level + charging state."""
    try:
        r = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5)
        out = r.stdout
        # Parse "100%; charging; ..." style
        result = {"raw": out.strip()}
        for line in out.splitlines():
            if "Battery" in line or "%" in line:
                if "%" in line:
                    try:
                        result["percent"] = int(line.split("%")[0].split()[-1])
                    except Exception:
                        pass
                if "charging" in line.lower() or "AC Power" in line:
                    result["charging"] = True
                elif "discharging" in line.lower() or "Battery Power" in line:
                    result["charging"] = False
        return result
    except Exception as e:
        return {"error": str(e)}


def system_uptime() -> dict:
    try:
        r = subprocess.run(["uptime"], capture_output=True, text=True, timeout=5)
        return {"uptime": r.stdout.strip()}
    except Exception as e:
        return {"error": str(e)}


# --- Timers (in-process countdown) ---
_active_timers: dict = {}


def _timer_thread(name: str, seconds: int, message: str) -> None:
    _time.sleep(seconds)
    try:
        subprocess.run(["osascript", "-e", f'display notification "{message}" with title "Timer: {name}"'])
        subprocess.run(["say", f"Timer {name} finished. {message}"], check=False)
    except Exception:
        pass
    _active_timers.pop(name, None)


def start_timer(name: str, minutes: float, message: str = "") -> dict:
    """Start a background countdown. Speaks + notifies when done."""
    seconds = int(float(minutes) * 60)
    if seconds <= 0:
        return {"error": "minutes must be positive"}
    msg = message or f"Your {name} timer is done."
    t = threading.Thread(target=_timer_thread, args=(name, seconds, msg), daemon=True)
    _active_timers[name] = {"minutes": minutes, "started_at": datetime.now().isoformat(), "thread": t}
    t.start()
    return {"name": name, "minutes": minutes, "status": "started"}


def list_timers() -> dict:
    return {
        "active": [
            {"name": n, "minutes": v["minutes"], "started_at": v["started_at"]}
            for n, v in _active_timers.items()
        ]
    }
