"""
jarvis/hud/airplay.py
Drive macOS AirPlay 'Screen Mirroring' from the menu bar.

There is no first-party Apple API for starting an AirPlay session
programmatically. The fully-software path on macOS is to use AppleScript
to click the Control Center's 'Screen Mirroring' menu bar item and pick
a named receiver.

First run: macOS will prompt for permission to control System Events.
After that, the script runs headlessly.

EXTEND MODE: After connecting, calls `set_extend_mode()` which opens
System Settings → Displays and forces the receiver to "Use as: Separate
Display" via AppleScript. Falls back gracefully if UI labels differ.
Works for all AirPlay receivers (TVs, Apple TVs, other Macs, AirPlay
speakers-as-receivers, third-party receivers).
"""
from __future__ import annotations

import subprocess
import time
from typing import List, Optional


# AppleScript: open Screen Mirroring, click the receiver whose name
# matches. If not present, return a sentinel.
_AIRPLAY_SCRIPT = '''
tell application "System Events"
    tell process "ControlCenter"
        if not (exists menu bar item "Screen Mirroring" of menu bar 1) then
            return "NO_MENU_BAR_ITEM"
        end if
        click menu bar item "Screen Mirroring" of menu bar 1
        delay 0.5
        tell menu 1 of menu bar item "Screen Mirroring" of menu bar 1
            set targetName to "{name}"
            if exists menu item targetName then
                click menu item targetName
                return "OK"
            else if exists menu item (targetName & "…") then
                click menu item (targetName & "…")
                delay 0.4
                key code 36
                return "OK"
            else
                -- list what we saw to help debugging
                set seen to ""
                repeat with mi in menu items
                    set seen to seen & (name of mi) & "|"
                end repeat
                key code 53 -- Escape to close
                return "RECEIVER_NOT_FOUND:" & seen
            end if
        end tell
    end tell
end tell
return "OK"
'''


# AppleScript: list visible receivers from the menu.
_LIST_SCRIPT = '''
tell application "System Events"
    tell process "ControlCenter"
        if not (exists menu bar item "Screen Mirroring" of menu bar 1) then
            return "[]"
        end if
        click menu bar item "Screen Mirroring" of menu bar 1
        delay 0.4
        set names to {}
        tell menu 1 of menu bar item "Screen Mirroring" of menu bar 1
            repeat with mi in menu items
                set nm to name of mi
                if nm is not "Turn Screen Mirroring Off" then
                    set end of names to nm
                end if
            end repeat
        end tell
        key code 53
        set AppleScript's text item delimiters to "|"
        return names as text
    end tell
end tell
'''


# AppleScript: turn off any active mirroring session.
_STOP_SCRIPT = '''
tell application "System Events"
    tell process "ControlCenter"
        if not (exists menu bar item "Screen Mirroring" of menu bar 1) then
            return "NO_MENU_BAR_ITEM"
        end if
        click menu bar item "Screen Mirroring" of menu bar 1
        delay 0.4
        tell menu 1 of menu bar item "Screen Mirroring" of menu bar 1
            if exists menu item "Turn Screen Mirroring Off" then
                click menu item "Turn Screen Mirroring Off"
                return "STOPPED"
            else
                key code 53
                return "NOT_ACTIVE"
            end if
        end tell
    end tell
end tell
return "NOT_ACTIVE"
'''


def _run_osascript(script: str, timeout: float = 8.0) -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 124, "", "osascript timed out"
    except FileNotFoundError:
        return 127, "", "osascript not found (macOS only)"


def start_airplay(receiver: str, timeout: float = 8.0) -> dict:
    """Start mirroring the primary display to the named AirPlay receiver."""
    from jarvis.platform import macos_only
    blocked = macos_only("AirPlay")
    if blocked:
        return {"ok": False, "error": blocked}
    if not receiver:
        return {"ok": False, "error": "no receiver name given"}
    # Escape double quotes for AppleScript string literal
    safe = receiver.replace("\\", "\\\\").replace('"', '\\"')
    rc, out, err = _run_osascript(_AIRPLAY_SCRIPT.format(name=safe), timeout=timeout)
    if "RECEIVER_NOT_FOUND" in out:
        seen = out.split(":", 1)[1] if ":" in out else ""
        return {
            "ok": False,
            "error": f"receiver '{receiver}' not found in Screen Mirroring menu",
            "visible": [s for s in seen.split("|") if s],
        }
    if "NO_MENU_BAR_ITEM" in out:
        return {
            "ok": False,
            "error": "Screen Mirroring menu-bar item not visible — make sure you're logged in to macOS as a user (not at the lock screen) and that Control Center is enabled",
        }
    if rc != 0 and "OK" not in out:
        return {"ok": False, "error": err or f"osascript exit {rc}"}
    return {"ok": True, "error": None, "receiver": receiver}


def list_receivers(timeout: float = 6.0) -> List[str]:
    """Return visible AirPlay receiver names from the Screen Mirroring menu."""
    from jarvis.platform import macos_only
    if macos_only("AirPlay"):
        return []
    rc, out, err = _run_osascript(_LIST_SCRIPT, timeout=timeout)
    if rc != 0 or not out:
        return []
    return [s for s in out.split("|") if s]


def stop_airplay(timeout: float = 6.0) -> dict:
    """Turn off any active AirPlay mirroring session."""
    from jarvis.platform import macos_only
    blocked = macos_only("AirPlay")
    if blocked:
        return {"ok": False, "error": blocked}
    rc, out, err = _run_osascript(_STOP_SCRIPT, timeout=timeout)
    if "STOPPED" in out:
        return {"ok": True, "error": None, "status": "stopped"}
    if "NOT_ACTIVE" in out:
        return {"ok": True, "error": None, "status": "not_active"}
    if "NO_MENU_BAR_ITEM" in out:
        return {"ok": False, "error": "Screen Mirroring menu not available"}
    return {"ok": False, "error": err or f"osascript exit {rc}"}


# ============================================================
# EXTEND MODE (TV = separate display, Mac stays free)
# ============================================================

# Opens System Settings → Displays and sets receiver to "Separate Display".
_EXTEND_SCRIPT_TEMPLATE = '''
on setExtend(receiverName)
    tell application "System Settings"
        activate
    end tell
    delay 1.0
    tell application "System Events"
        tell process "System Settings"
            set found to false
            try
                repeat with r in rows of outline 1 of scroll area 1 of group 1 of group 2 of splitter group 1 of group 1 of window "System Settings"
                    if name of UI element 1 of r contains "Displays" then
                        select r
                        set found to true
                        exit repeat
                    end if
                end repeat
            end try
            if not found then
                return "NAV_FAIL"
            end if
            delay 1.0
            try
                set tiles to buttons of group 1 of group 2 of splitter group 1 of group 1 of window "System Settings"
                repeat with t in tiles
                    if name of t contains receiverName then
                        click t
                        delay 0.8
                        exit repeat
                    end if
                end repeat
            end try
            try
                set dd to first pop up button of group 1 of group 2 of splitter group 1 of group 1 of window "System Settings" whose help contains "Use as"
                click dd
                delay 0.5
                repeat with mi in menu items of menu 1 of dd
                    set nm to name of mi
                    if nm contains "Separate" or nm contains "Extended" then
                        click mi
                        delay 0.5
                        return "OK"
                    end if
                end repeat
                key code 53
                return "OPTION_NOT_FOUND"
            end try
            return "DROPDOWN_NOT_FOUND"
        end tell
    end tell
    return "OK"
end setExtend

setExtend("{receiver}")
'''


def set_extend_mode(receiver: str, timeout: float = 15.0) -> dict:
    """
    Force an AirPlay receiver into Extend mode (separate display, not mirror).
    Opens System Settings → Displays and selects 'Use as: Separate Display'.
    """
    from jarvis.platform import macos_only
    blocked = macos_only("AirPlay")
    if blocked:
        return {"ok": False, "error": blocked}
    if not receiver:
        return {"ok": False, "error": "no receiver name given"}
    safe = receiver.replace("\\", "\\\\").replace('"', '\\"')
    script = _EXTEND_SCRIPT_TEMPLATE.format(receiver=safe)
    rc, out, err = _run_osascript(script, timeout=timeout)
    if "OK" in out:
        return {"ok": True, "status": "extended", "receiver": receiver}
    return {
        "ok": False,
        "status": out.strip() if out else "fail",
        "error": err or f"osascript exit {rc}",
        "hint": "Open System Settings → Displays → click the receiver tile → set 'Use as' to 'Separate Display' manually.",
    }
