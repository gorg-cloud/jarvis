"""
jarvis/tools/notify_tool.py
macOS native notifications.
"""
import subprocess


def notify(title: str, message: str = "", sound: str = "") -> dict:
    """Push a macOS notification."""
    safe_title = title.replace('"', '\\"')
    safe_msg = message.replace('"', '\\"')
    script = f'display notification "{safe_msg}" with title "{safe_title}"'
    if sound:
        script += f' sound name "{sound}"'
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True, timeout=5)
        return {"title": title, "message": message, "status": "ok"}
    except Exception as e:
        return {"title": title, "error": str(e)}
