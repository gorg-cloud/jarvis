"""
jarvis/tools/reminders_tool.py
Creates reminders in the native macOS Reminders app via AppleScript.
"""
import subprocess
from datetime import datetime
from typing import Optional

from jarvis.platform import macos_only


def _run_applescript(script: str) -> str:
    """Run an AppleScript snippet and return stdout."""
    result = subprocess.run(
        ["osascript", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.stdout.strip()


def create_reminder(title: str, due: Optional[str] = None) -> dict:
    """
    Create a reminder in macOS Reminders.app.

    Parameters
    ----------
    title : str
        The reminder text.
    due : Optional[str]
        Due date/time as a human-readable string that AppleScript can parse,
        e.g. "July 20, 2026 6:00 PM".  If omitted the reminder has no due date.

    Returns
    -------
    dict
        Confirmation with the title and due date.
    """
    blocked = macos_only("Reminders")
    if blocked:
        return {"title": title, "error": blocked}
    # Escape double quotes for AppleScript string literals
    safe_title = title.replace('"', '\\"')

    if due:
        try:
            dt = datetime.strptime(due, "%Y-%m-%d %H:%M:%S")
            script = (
                'set dueDate to current date\n'
                f'set year of dueDate to {dt.year}\n'
                f'set month of dueDate to {dt.month}\n'
                f'set day of dueDate to {dt.day}\n'
                f'set hours of dueDate to {dt.hour}\n'
                f'set minutes of dueDate to {dt.minute}\n'
                f'set seconds of dueDate to {dt.second}\n'
                'tell application "Reminders"\n'
                f'  make new reminder with properties {{name:"{safe_title}", due date:dueDate}}\n'
                'end tell'
            )
        except ValueError:
            safe_due = due.replace('"', '\\"')
            script = (
                'tell application "Reminders"\n'
                f'  set dueDate to date "{safe_due}"\n'
                f'  make new reminder with properties {{name:"{safe_title}", due date:dueDate}}\n'
                'end tell'
            )
    else:
        script = (
            'tell application "Reminders"\n'
            f'  make new reminder with properties {{name:"{safe_title}"}}\n'
            'end tell'
        )

    _run_applescript(script)
    return {"title": title, "due": due, "created": True}
