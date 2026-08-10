"""
jarvis/tools/alarms_tool.py
Triggers macOS/iOS alarms via the Shortcuts CLI or AppleScript fallback.
"""
import subprocess
from datetime import datetime
from ..config import USE_SHORTCUT, ALARM_SHORTCUT_NAME
from jarvis.platform import macos_only


def create_alarm(time_str: str) -> dict:
    """
    Create an alarm on macOS (syncs to iPhone via iCloud Shortcuts).

    Parameters
    ----------
    time_str : str
        Time in HH:MM (24-hour) format, e.g. "08:30" or "18:00".

    Returns
    -------
    dict
        Confirmation with the scheduled time.
    """
    blocked = macos_only("Alarms")
    if blocked:
        return {"alarm_time": time_str, "error": blocked}
    if USE_SHORTCUT:
        # Invoke the user's pre-built Shortcut named "CreateAlarm"
        subprocess.run(
            ["shortcuts", "run", ALARM_SHORTCUT_NAME, "-i", time_str],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    else:
        # Fallback: create a Calendar event with a display alarm at trigger time
        today = datetime.now().strftime("%B %d, %Y")
        script = (
            f'set alarmTime to date "{today} {time_str}"\n'
            'tell application "Calendar"\n'
            '  set theCal to first calendar\n'
            '  set newEvent to make new event at end of events of theCal '
            'with properties {summary:"JARVIS Alarm", start date:alarmTime, end date:alarmTime}\n'
            '  make new display alarm at end of display alarms of newEvent '
            'with properties {trigger interval:0}\n'
            'end tell'
        )
        subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )

    return {"alarm_time": time_str, "created": True}
