"""
jarvis/tools/system_tools.py
Tools for interacting with the macOS operating system (e.g., opening apps).
"""
import subprocess

def open_app(app_name: str) -> dict:
    try:
        subprocess.run(["open", "-a", app_name], check=True, capture_output=True, text=True)
        return {"app": app_name, "status": "opened"}
    except subprocess.CalledProcessError as e:
        return {"app": app_name, "status": "failed", "error": e.stderr}

def open_url(url: str) -> dict:
    """Opens a URL in the default browser."""
    try:
        subprocess.run(["open", url], check=True, capture_output=True, text=True)
        return {"url": url, "status": "opened"}
    except subprocess.CalledProcessError as e:
        return {"url": url, "status": "failed", "error": e.stderr}

def set_wifi(state: bool) -> dict:
    """Turns Wi-Fi on (True) or off (False)."""
    val = "on" if state else "off"
    try:
        subprocess.run(["networksetup", "-setairportpower", "en0", val], check=True, capture_output=True, text=True)
        return {"wifi": val, "status": "success"}
    except subprocess.CalledProcessError as e:
        return {"wifi": val, "status": "failed", "error": e.stderr}

def set_bluetooth(state: bool) -> dict:
    """Turns Bluetooth on (True) or off (False)."""
    val = "1" if state else "0"
    try:
        subprocess.run(["/opt/homebrew/bin/blueutil", "-p", val], check=True, capture_output=True, text=True)
        str_val = "on" if state else "off"
        return {"bluetooth": str_val, "status": "success"}
    except subprocess.CalledProcessError as e:
        return {"bluetooth": "unknown", "status": "failed", "error": e.stderr}

def sleep_mac() -> dict:
    """Puts the Mac to sleep."""
    try:
        subprocess.run(["pmset", "sleepnow"], check=True, capture_output=True, text=True)
        return {"action": "sleep", "status": "success"}
    except subprocess.CalledProcessError as e:
        return {"action": "sleep", "status": "failed", "error": e.stderr}

def start_screensaver() -> dict:
    """Starts the Mac Screen Saver."""
    try:
        subprocess.run(["open", "-a", "ScreenSaverEngine"], check=True, capture_output=True, text=True)
        return {"action": "screensaver", "status": "success"}
    except subprocess.CalledProcessError as e:
        return {"action": "screensaver", "status": "failed", "error": e.stderr}
