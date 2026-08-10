"""
jarvis/tools/context_tool.py
Senses active app + selected text so JARVIS knows what the user is looking at.
"""
import subprocess

from jarvis.platform import macos_only


def frontmost_app() -> dict:
    """Return name + bundle id of the currently focused app."""
    blocked = macos_only("Frontmost-app sensing")
    if blocked:
        return {"error": blocked}
    script = (
        'tell application "System Events"'
        ' to {name of first application process whose frontmost is true, '
        'bundle identifier of first application process whose frontmost is true}'
    )
    try:
        out = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, check=True, timeout=5
        )
        parts = [p.strip() for p in out.stdout.split(",")]
        return {
            "app": parts[0] if parts else "",
            "bundle_id": parts[1] if len(parts) > 1 else "",
        }
    except subprocess.CalledProcessError as e:
        return {"error": e.stderr.strip() or "no frontmost app"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def selected_text() -> dict:
    """
    Get text currently selected in the frontmost app.
    Uses cmd+C via System Events (requires Accessibility permission).
    """
    blocked = macos_only("Selected-text sensing")
    if blocked:
        return {"text": "", "length": 0, "empty": True, "error": blocked}
    # Save current clipboard so we don't destroy it
    saved = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5).stdout
    # Clear clipboard
    subprocess.run(["pbcopy"], input="", text=True, timeout=5)

    script = (
        'tell application "System Events" to keystroke "c" using command down'
    )
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
    except Exception:
        pass

    # Small delay for clipboard to update
    import time
    time.sleep(0.15)

    try:
        new = subprocess.run(["pbpaste", "-Prefer", "txt"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        new = ""

    # Restore original clipboard
    subprocess.run(["pbcopy"], input=saved, text=True, timeout=5)

    return {
        "text": new,
        "length": len(new),
        "empty": len(new.strip()) == 0,
    }


def active_context() -> dict:
    """Combined: frontmost app + selected text."""
    app = frontmost_app()
    sel = selected_text()
    return {"app": app, "selection": sel}
