"""
jarvis/app/status.py
Live status strip for the tray menu — battery, clock, current Spotify track.
Kept cheap: each call is a fast subprocess, and the menu polls every few seconds.
"""
import subprocess
import time


def _sh(cmd, timeout: float = 5.0) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def battery_percent() -> str:
    """'87%' or '87% ⚡' (charging) or '—' if unknown."""
    try:
        from jarvis.platform import battery_status
        b = battery_status()
        if b.get("percent") is not None and b["percent"] >= 0:
            charging = b.get("charging")
            return f"{b['percent']}%{' ⚡' if charging else ''}"
    except Exception:
        pass
    return "—"


def now_playing() -> str:
    """'♪ Track — Artist' or '' when Spotify isn't playing anything."""
    try:
        from jarvis.tools.spotify_tool import spotify_status

        s = spotify_status()
        if s.get("error") or not s.get("track"):
            return ""
        track = s["track"]
        artist = s.get("artist", "")
        return f"♪ {track} — {artist}" if artist else f"♪ {track}"
    except Exception:
        return ""


def clock() -> str:
    return time.strftime("%H:%M")


def status_line(max_len: int = 46) -> str:
    """One-line strip: ● ONLINE · battery · clock · now playing (truncated)."""
    parts = ["● ONLINE", battery_percent(), clock()]
    np = now_playing()
    if np:
        parts.append(np)
    line = "  ·  ".join(parts)
    if len(line) > max_len:
        line = line[: max_len - 1] + "…"
    return line
