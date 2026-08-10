"""
jarvis/tools/findmy_tool.py
Find My device lookup via a Shortcut (must be set up once).
"""
import subprocess

from jarvis.platform import macos_only


def find_device(device: str) -> dict:
    """
    Play a sound on a Find My device via a Shortcut named 'Find My Device'
    that accepts `device` as input.

    First-time setup:
    1. Open Shortcuts.app → New Shortcut
    2. Add action: "Find Devices" or "Play Sound on Device"
    3. Set the device name from the shortcut input
    4. Name the shortcut 'Find My Device'
    """
    blocked = macos_only("Find My")
    if blocked:
        return {"device": device, "error": blocked}
    try:
        r = subprocess.run(
            ["shortcuts", "run", "Find My Device", "-i", device],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode != 0:
            return {
                "device": device,
                "status": "failed",
                "error": r.stderr.strip(),
                "hint": "Create a Shortcut named 'Find My Device' that plays a sound on the given device name.",
            }
        return {"device": device, "status": "playing_sound"}
    except FileNotFoundError:
        return {"error": "shortcuts CLI not available"}
    except Exception as e:
        return {"device": device, "error": f"{type(e).__name__}: {e}"}
