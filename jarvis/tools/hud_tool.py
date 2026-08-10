"""
jarvis/tools/hud_tool.py
Launches the JARVIS HUD on external display (TV/monitor).

Actions:
  - launch_hud          — fullscreen on physical external display (legacy)
  - close_hud           — kill any running PyQt HUD (legacy)
  - launch_hud_preview  — open the PyQt HUD as a window on the primary
                          display so the user can see it locally
  - launch_hud_on_tv    — open the PyQt HUD as a window AND mirror it
                          over AirPlay to a named receiver
  - launch_hud_web      — start the local web HUD server (universal
                          fallback for non-AirPlay TVs)
  - stop_hud_web        — stop the web HUD server
  - list_airplay_receivers — show the names of visible AirPlay TVs
  - stop_airplay        — turn off the current AirPlay mirroring session
"""
import os
import subprocess
import sys

from jarvis.hud.airplay import list_receivers, start_airplay, stop_airplay


# ---- legacy: fullscreen on a physical external display ----

def launch_hud(preview: bool = False) -> dict:
    """
    Launch JARVIS HUD fullscreen on external display.
    preview=True → opens as window on primary screen (for testing).
    """
    python = sys.executable
    cmd = [python, "-m", "jarvis.hud.app"]
    if preview:
        cmd.append("--preview")

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        return {
            "pid": proc.pid,
            "mode": "preview" if preview else "fullscreen",
            "status": "launched",
        }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def close_hud() -> dict:
    """Kill any running JARVIS HUD process."""
    try:
        result = subprocess.run(
            ["pkill", "-f", "jarvis.hud.app"],
            capture_output=True, text=True, timeout=5
        )
        return {"status": "killed"}
    except Exception as e:
        return {"error": str(e)}


# ---- new: local preview (PyQt window on primary display) ----

def launch_hud_preview() -> dict:
    """Open the PyQt HUD as a windowed preview on the primary display.

    Lets the user see the live HUD locally before pushing it to a TV.
    No AirPlay required. Close the window (or the kill button) to dismiss.
    """
    return launch_hud(preview=True)


# ---- new: AirPlay mirror to a TV ----

def launch_hud_on_tv(receiver: str = "") -> dict:
    """Open the PyQt HUD as a window AND mirror to an AirPlay receiver.

    If `receiver` is empty, returns the list of visible receivers
    instead of starting a session, so the LLM can prompt the user.
    """
    if not receiver:
        return {
            "status": "need_receiver",
            "receivers": list_receivers(),
            "hint": "call hud.launch_on_tv with one of the receiver names",
        }
    air = start_airplay(receiver)
    if not air.get("ok"):
        return {
            "error": air.get("error", "airplay failed"),
            "receivers": list_receivers(),
        }
    launch = launch_hud(preview=True)
    if "error" in launch:
        return {"error": launch["error"], "airplay": "started", "receiver": receiver}
    return {
        "status": "mirroring",
        "receiver": receiver,
        "hud_pid": launch.get("pid"),
        "hint": "HUD is on your Mac and mirroring to the TV. Call hud.stop_airplay to disconnect.",
    }


def list_airplay_receivers() -> dict:
    """List the names of AirPlay receivers visible to macOS."""
    return {"receivers": list_receivers()}


def stop_airplay_session() -> dict:
    """Turn off the current AirPlay mirroring session, if any."""
    return stop_airplay()


# ---- new: web HUD (universal fallback for non-AirPlay TVs) ----

def launch_hud_web(port: int = 8765, background: bool = True) -> dict:
    """Start the web HUD server.

    Returns the URL(s) to load in any browser on the same network.
    """
    python = sys.executable
    cmd = [python, "-m", "jarvis.hud.server", "--port", str(port)]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=background,
        )
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    # Best-effort LAN IP for the response. Import lazily to avoid
    # importing the server module until we need it.
    try:
        from jarvis.hud.server import _local_ip
        ip = _local_ip()
    except Exception:
        ip = "127.0.0.1"

    return {
        "status": "started",
        "pid": proc.pid,
        "port": port,
        "url_local": f"http://localhost:{port}/",
        "url_network": f"http://{ip}:{port}/",
        "hint": f"open {ip}:{port} on the TV's browser (Chromecast, Fire Stick, RPi, laptop)",
    }


def stop_hud_web() -> dict:
    """Kill any running JARVIS HUD web server."""
    try:
        result = subprocess.run(
            ["pkill", "-f", "jarvis.hud.server"],
            capture_output=True, text=True, timeout=5
        )
        return {"status": "killed"}
    except Exception as e:
        return {"error": str(e)}
