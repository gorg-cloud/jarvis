"""
jarvis/tools/mac_apps.py
Tools for interacting with specific macOS apps (Messages, Music).
"""
import subprocess

from jarvis.platform import macos_only

def send_message(contact: str, message: str) -> dict:
    """Sends an iMessage/SMS using AppleScript."""
    blocked = macos_only("Messages")
    if blocked:
        return {"contact": contact, "status": "failed", "error": blocked}
    script = f'''
    tell application "Messages"
        set targetService to 1st service whose service type is iMessage
        set theBuddy to buddy "{contact}" of targetService
        send "{message}" to theBuddy
    end tell
    '''
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
        return {"contact": contact, "message": message, "status": "sent"}
    except subprocess.CalledProcessError as e:
        return {"contact": contact, "status": "failed", "error": e.stderr}

def control_music(action: str) -> dict:
    """Controls Apple Music. Actions: 'play', 'pause', 'next track', 'previous track'."""
    blocked = macos_only("Apple Music control")
    if blocked:
        return {"action": action, "status": "failed", "error": blocked}
    valid_actions = ["play", "pause", "next track", "previous track", "next", "previous"]
    
    if action == "next":
        action = "next track"
    elif action == "previous":
        action = "previous track"
        
    if action not in valid_actions:
        return {"status": "failed", "error": f"Invalid action. Must be one of: play, pause, next track, previous track."}

    script = f'tell application "Music" to {action}'
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
        return {"action": action, "status": "success"}
    except subprocess.CalledProcessError as e:
        return {"action": action, "status": "failed", "error": e.stderr}
