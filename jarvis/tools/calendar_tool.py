"""
jarvis/tools/calendar_tool.py
macOS Calendar.app via AppleScript — read events.
"""
import subprocess

from jarvis.platform import macos_only


def _run(script: str, timeout: int = 15) -> str:
    r = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=timeout
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "calendar applescript failed")
    return r.stdout.strip()


def next_events(limit: int = 5) -> dict:
    """Return up to `limit` upcoming events across all calendars."""
    blocked = macos_only("Calendar access")
    if blocked:
        return {"error": blocked}
    # Pull today + tomorrow events, sort in script
    script = f'''
    set output to ""
    set today to current date
    set hours of today to 0
    set minutes of today to 0
    set seconds of today to 0
    set tomorrow to today + (1 * days)
    set dayAfter to today + (2 * days)
    tell application "Calendar"
      set evs to {{}}
      repeat with c in calendars
        set evs to evs & (every event of c whose start date is greater than or equal to today and start date is less than dayAfter)
      end repeat
      set idx to 0
      repeat with e in evs
        if idx is greater than or equal to {limit} then exit repeat
        set sd to start date of e
        set ed to end date of e
        set summ to summary of e
        set loc to ""
        try
          set loc to location of e
        end try
        set output to output & (sd as text) & " || " & (ed as text) & " || " & summ & " || " & loc & linefeed
        set idx to idx + 1
      end repeat
    end tell
    return output
    '''
    try:
        raw = _run(script)
    except Exception as e:
        return {"error": str(e)}

    events = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("||")]
        events.append({
            "start": parts[0] if len(parts) > 0 else "",
            "end": parts[1] if len(parts) > 1 else "",
            "summary": parts[2] if len(parts) > 2 else "",
            "location": parts[3] if len(parts) > 3 else "",
        })
    # Sort by parsed start time (best effort)
    from datetime import datetime
    def _key(e):
        for fmt in ("%A, %B %d, %Y at %I:%M:%S %p", "%A, %d %B %Y at %I:%M:%S %p"):
            try:
                return datetime.strptime(e["start"], fmt)
            except Exception:
                pass
        return datetime.max
    events.sort(key=_key)
    return {"count": len(events), "events": events}


def free_at(time_str: str) -> dict:
    """Check if calendar is free at a given time. time_str: '2026-07-20 15:00'."""
    blocked = macos_only("Calendar access")
    if blocked:
        return {"time": time_str, "error": blocked}
    from datetime import datetime
    try:
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
    except ValueError:
        return {"time": time_str, "error": "Use format YYYY-MM-DD HH:MM"}
    start_str = dt.strftime("%A, %B %d, %Y at %I:%M:%S %p")
    end_dt = dt + __import__("datetime").timedelta(minutes=30)
    end_str = end_dt.strftime("%A, %B %d, %Y at %I:%M:%S %p")

    script = f'''
    set s to date "{start_str}"
    set e to date "{end_str}"
    set conflicts to ""
    tell application "Calendar"
      repeat with c in calendars
        repeat with ev in (every event of c whose start date is less than e and end date is greater than s)
          set conflicts to conflicts & (summary of ev) & " (" & (start date of ev) & " - " & (end date of ev) & ")" & linefeed
        end repeat
      end repeat
    end tell
    return conflicts
    '''
    try:
        conflicts = _run(script).strip()
    except Exception as e:
        return {"time": time_str, "error": str(e)}
    return {
        "time": time_str,
        "free": len(conflicts) == 0,
        "conflicts": conflicts.split("\n") if conflicts else [],
    }


def week_events(days: int = 7) -> dict:
    """Return all events for the next N days."""
    blocked = macos_only("Calendar access")
    if blocked:
        return {"error": blocked}
    from datetime import datetime, timedelta
    today = datetime.now()
    end = today + timedelta(days=days)
    today_str = today.strftime("%A, %B %d, %Y at %I:%M:%S %p")
    end_str = end.strftime("%A, %B %d, %Y at %I:%M:%S %p")
    script = f'''
    set s to date "{today_str}"
    set e to date "{end_str}"
    set output to ""
    tell application "Calendar"
      set evs to {{}}
      repeat with c in calendars
        set evs to evs & (every event of c whose start date is greater than or equal to s and start date is less than e)
      end repeat
      repeat with ev in evs
        set sd to start date of ev
        set ed to end date of ev
        set summ to summary of ev
        set loc to ""
        try
          set loc to location of ev
        end try
        set cal to name of (container of ev)
        set output to output & cal & " || " & (sd as text) & " || " & (ed as text) & " || " & summ & " || " & loc & linefeed
      end repeat
    end tell
    return output
    '''
    try:
        raw = _run(script, timeout=20)
    except Exception as e:
        return {"error": str(e)}
    events = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("||")]
        events.append({
            "calendar": parts[0] if len(parts) > 0 else "",
            "start": parts[1] if len(parts) > 1 else "",
            "end": parts[2] if len(parts) > 2 else "",
            "summary": parts[3] if len(parts) > 3 else "",
            "location": parts[4] if len(parts) > 4 else "",
        })
    from datetime import datetime
    def _key(e):
        for fmt in ("%A, %B %d, %Y at %I:%M:%S %p", "%A, %d %B %Y at %I:%M:%S %p"):
            try:
                return datetime.strptime(e["start"], fmt)
            except Exception:
                pass
        return datetime.max
    events.sort(key=_key)
    return {"count": len(events), "days": days, "events": events}
