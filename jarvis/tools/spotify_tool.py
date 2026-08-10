"""
jarvis/tools/spotify_tool.py
Controls Spotify.app via AppleScript (no API/OAuth needed).
"""
import subprocess

VALID_ACTIONS = {
    "play", "pause", "playpause", "next", "previous",
    "next track", "previous track",
}


def control_spotify(action: str) -> dict:
    """Play/pause/skip Spotify."""
    a = action.lower().strip()
    if a == "next":
        a = "next track"
    elif a == "previous":
        a = "previous track"

    if a not in VALID_ACTIONS:
        return {"action": action, "status": "failed",
                "error": f"Invalid action. Must be one of: play, pause, playpause, next, previous."}

    script = f'tell application "Spotify" to {a}'
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True, timeout=10)
        return {"action": a, "status": "success"}
    except subprocess.CalledProcessError as e:
        err = e.stderr.strip()
        # If Spotify not running, try to open + retry play
        if "not running" in err.lower() or "-1728" in err:
            subprocess.run(["open", "-a", "Spotify"], capture_output=True, timeout=10)
            return {"action": a, "status": "launched_spotify"}
        return {"action": a, "status": "failed", "error": err}


def spotify_status() -> dict:
    """Now playing info: track, artist, album, state."""
    script = '''
    tell application "Spotify"
      if player state is playing then
        set state to "playing"
      else if player state is paused then
        set state to "paused"
      else
        set state to "stopped"
      end if
      try
        set t to name of current track
        set a to artist of current track
        set al to album of current track
        return state & "|" & t & "|" & a & "|" & al
      on error
        return state & "|||"
      end try
    end tell
    '''
    try:
        out = subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True, timeout=5)
        parts = out.stdout.strip().split("|", 3)
        return {
            "state": parts[0] if len(parts) > 0 else "unknown",
            "track": parts[1] if len(parts) > 1 else "",
            "artist": parts[2] if len(parts) > 2 else "",
            "album": parts[3] if len(parts) > 3 else "",
        }
    except subprocess.TimeoutExpired:
        return {"error": "Spotify not responding (not running or needs launch)"}
    except subprocess.CalledProcessError as e:
        return {"error": e.stderr.strip() or "spotify not running"}
