"""
jarvis/hud/watcher.py
Daemon. Polls displays every 3s. When external display appears:
1. Posts macOS native dialog: "Activate JARVIS HUD on <display>?"
2. If YES → launches HUD fullscreen on that display.
3. When display disappears → kills HUD.

Runs headlessly in background. Install via launchd (com.jarvis.hud.watcher.plist).

Trigger covers BOTH HDMI plug-in AND AirPlay connect (both add a display).
"""
from __future__ import annotations

import logging
import subprocess
import threading
import time
from typing import Optional

log = logging.getLogger("jarvis.hud.watcher")


# ---------- Display detection ----------

def _count_displays() -> int:
    """Use system_profiler (reliable, ~0.3s)."""
    try:
        r = subprocess.run(
            ["system_profiler", "SPDisplaysDataType"],
            capture_output=True, text=True, timeout=10,
        )
        # Count "Resolution:" lines = number of active displays
        return r.stdout.count("Resolution:")
    except Exception as e:
        log.warning("display count failed: %s", e)
        return -1


def _display_names() -> list:
    """Return list of display names (best-effort)."""
    try:
        r = subprocess.run(
            ["system_profiler", "SPDisplaysDataType"],
            capture_output=True, text=True, timeout=10,
        )
        names = []
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.endswith(":") and not line.startswith("Resolution") and not line.startswith("UI Looks"):
                # Display name lines look like "Color LCD:" or "DELL U2720Q:"
                name = line.rstrip(":").strip()
                if name and not name.isdigit():
                    names.append(name)
        return names
    except Exception:
        return []


# ---------- Popup ----------

def _ask_popup(display_name: str) -> bool:
    """Native macOS dialog. Returns True if user clicks 'Activate'."""
    title = "JARVIS HUD"
    msg = f"Activate JARVIS HUD on {display_name}?"
    # 2-button dialog: Activate (default) / Not now
    script = f'''
    tell application "System Events"
        activate
        set dlg to display dialog "{msg}" with title "{title}" buttons {{"Not now", "Activate JARVIS"}} default button "Activate JARVIS" with icon 1
        return button returned of dlg
    end tell
    '''
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=120,  # wait up to 2 min
        )
        return r.returncode == 0 and "Activate" in r.stdout
    except Exception as e:
        log.warning("popup failed: %s", e)
        return False


# ---------- HUD launch/kill ----------

def _launch_hud() -> Optional[int]:
    """Launch HUD fullscreen on external display."""
    import os
    import sys
    python = sys.executable
    try:
        proc = subprocess.Popen(
            [python, "-m", "jarvis.hud.app"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        log.info("HUD launched pid=%d", proc.pid)
        return proc.pid
    except Exception as e:
        log.error("HUD launch failed: %s", e)
        return None


def _kill_hud() -> None:
    try:
        subprocess.run(["pkill", "-f", "jarvis.hud.app"], timeout=5)
        log.info("HUD killed")
    except Exception as e:
        log.warning("HUD kill failed: %s", e)


# ---------- Main watcher loop ----------

class DisplayWatcher:
    def __init__(self, poll_interval: float = 3.0):
        self.poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._baseline = _count_displays()
        self._hud_pid: Optional[int] = None
        self._known = set(_display_names())

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("watcher started. baseline=%d displays", self._baseline)

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                time.sleep(self.poll_interval)
                self._check()
            except Exception as e:
                log.exception("watcher tick failed: %s", e)

    def _check(self):
        current = _count_displays()
        if current < 0:
            return
        names = set(_display_names())
        # New display detected
        if current > self._baseline and self._hud_pid is None:
            new_names = names - self._known
            display_name = next(iter(new_names), "external display")
            log.info("new display: %s", display_name)
            # Ask user
            if _ask_popup(display_name):
                pid = _launch_hud()
                if pid:
                    self._hud_pid = pid
            self._baseline = current
            self._known = names
        # Display removed
        elif current < self._baseline and self._hud_pid is not None:
            log.info("display removed, killing HUD")
            _kill_hud()
            self._hud_pid = None
            self._baseline = current
            self._known = names
        elif current != self._baseline:
            # Adjusted without launching/killing (e.g. multiple simultaneous changes)
            self._baseline = current
            self._known = names


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--interval", type=float, default=3.0)
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )
    w = DisplayWatcher(poll_interval=args.interval)
    w.start()
    # Block forever
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log.info("shutting down")


if __name__ == "__main__":
    main()
