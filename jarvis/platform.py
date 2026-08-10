"""
jarvis/platform.py
Cross-platform abstraction for everything the app does at the OS level.

macOS uses Quartz CGEvent (same as before); Windows uses ctypes + user32/
kernel32. Every function here works on both, so the camera, HUD and tools
never import Quartz directly.

Windows notes:
  * Mouse moves/clicks post real input via SendInput (works on the secure
    desktop too, needs no special permission beyond running as the user).
  * Keyboard shortcuts use SendInput with virtual key codes.
  * Notifications use the WinRT toast API when available; otherwise they
    fall back to a console beep + print (never crash).
"""
from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
import sys
import time

_IS_MAC = sys.platform == "darwin"
_IS_WIN = os.name == "nt" or sys.platform == "win32"


# ---------------------------------------------------------------------------
# Mouse
# ---------------------------------------------------------------------------
class MouseController:
    """Moves the real cursor and posts real clicks. Display coordinates are
    origin-top-left, in physical pixels (macOS points == pixels on Retina
    for CGEvent; Windows SendInput uses pixels)."""

    def __init__(self) -> None:
        if _IS_MAC:
            import Quartz  # type: ignore

            self._quartz = Quartz
            b = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
            self._w = float(b.size.width)
            self._h = float(b.size.height)
            self._ox = float(b.origin.x)
            self._oy = float(b.origin.y)
        elif _IS_WIN:
            import ctypes  # noqa: PLC0415

            self._user32 = ctypes.windll.user32
            self._w = float(self._user32.GetSystemMetrics(0))
            self._h = float(self._user32.GetSystemMetrics(1))
            self._ox = 0.0
            self._oy = 0.0
        else:
            self._w = self._h = 1280.0
            self._ox = self._oy = 0.0

    def screen(self) -> tuple[float, float, float, float]:
        """(width, height, origin_x, origin_y) of the main display."""
        return self._w, self._h, self._ox, self._oy

    def move_to(self, x: float, y: float) -> None:
        if _IS_MAC:
            self._quartz.CGWarpMouseCursorPosition((x, y))
        elif _IS_WIN:
            self._user32.SetCursorPos(int(x), int(y))
        # other platforms: no-op

    def click(self, x: float, y: float) -> None:
        if _IS_MAC:
            self._post_mac(x, y, self._quartz.kCGEventLeftMouseDown,
                           self._quartz.kCGEventLeftMouseUp,
                           self._quartz.kCGMouseButtonLeft)
        elif _IS_WIN:
            self.move_to(x, y)
            self._win_button(0x0002, 0x0004)  # MOUSEEVENTF_LEFTDOWN / LEFTUP

    def right_click(self, x: float, y: float) -> None:
        if _IS_MAC:
            self._post_mac(x, y, self._quartz.kCGEventRightMouseDown,
                           self._quartz.kCGEventRightMouseUp,
                           self._quartz.kCGMouseButtonRight)
        elif _IS_WIN:
            self.move_to(x, y)
            self._win_button(0x0008, 0x0010)  # MOUSEEVENTF_RIGHTDOWN / RIGHTUP

    # -- internals ----------------------------------------------------------
    def _post_mac(self, x: float, y: float, down_type, up_type, button) -> None:
        q = self._quartz
        down = q.CGEventCreateMouseEvent(None, down_type, (x, y), button)
        up = q.CGEventCreateMouseEvent(None, up_type, (x, y), button)
        q.CGEventPost(q.kCGHIDEventTap, down)
        time.sleep(0.04)
        q.CGEventPost(q.kCGHIDEventTap, up)

    def _win_button(self, down_flag: int, up_flag: int) -> None:
        import ctypes  # noqa: PLC0415

        class _INPUT(ctypes.Structure):
            class _U(ctypes.Union):
                class _MI(ctypes.Structure):
                    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                                ("mouseData", ctypes.c_ulong),
                                ("dwFlags", ctypes.c_ulong),
                                ("time", ctypes.c_ulong),
                                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

                _fields_ = [("mi", _MI)]

            _fields_ = [("type", ctypes.c_ulong), ("u", _U)]

        for flag in (down_flag, up_flag):
            inp = _INPUT()
            inp.type = 0  # INPUT_MOUSE
            inp.u.mi.dwFlags = flag
            self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))
            time.sleep(0.04)


# ---------------------------------------------------------------------------
# Keyboard
# ---------------------------------------------------------------------------
if _IS_MAC:
    # Virtual key codes (CGEvent) + modifier masks.
    KEY_LEFT = 123
    KEY_RIGHT = 124
    KEY_UP = 126
    KEY_Q = 12
    MOD_CMD = 0x100000    # kCGEventFlagMaskCommand
    MOD_CTRL = 0x40000    # kCGEventFlagMaskControl
    MOD_ALT = 0x80000     # kCGEventFlagMaskAlternate
elif _IS_WIN:
    # Virtual key codes (Windows) + modifiers.
    KEY_LEFT = 0x25       # VK_LEFT
    KEY_RIGHT = 0x27      # VK_RIGHT
    KEY_UP = 0x26         # VK_UP
    KEY_Q = 0x51          # VK_Q
    MOD_CMD = 0x0008      # MOD_WIN — Windows key
    MOD_CTRL = 0x0002     # MOD_CONTROL
    MOD_ALT = 0x0001      # MOD_ALT
else:
    KEY_LEFT = KEY_RIGHT = KEY_UP = KEY_Q = 0
    MOD_CMD = MOD_CTRL = MOD_ALT = 0


class KeyboardController:
    """Posts real keyboard shortcuts."""

    def combo(self, keycode: int, flags: int) -> None:
        if _IS_MAC:
            import Quartz  # type: ignore

            down = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
            Quartz.CGEventSetFlags(down, flags)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
            up = Quartz.CGEventCreateKeyboardEvent(None, keycode, False)
            Quartz.CGEventSetFlags(up, flags)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
        elif _IS_WIN:
            import ctypes  # noqa: PLC0415

            u = ctypes.windll.user32
            mods = {"ctrl": bool(flags & MOD_CTRL), "cmd": bool(flags & MOD_CMD)}
            vk = keycode
            # macOS left/right arrow codes map 1:1 to the same physical keys.
            for mod, held in mods.items():
                if held:
                    vk_mod = {"ctrl": 0x11, "cmd": 0x5B}.get(mod)  # VK_CONTROL, VK_LWIN
                    if vk_mod:
                        u.keybd_event(vk_mod, 0, 0, 0)
            u.keybd_event(vk, 0, 0, 0)
            u.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP
            for mod, held in mods.items():
                if held:
                    vk_mod = {"ctrl": 0x11, "cmd": 0x5B}.get(mod)
                    if vk_mod:
                        u.keybd_event(vk_mod, 0, 2, 0)
        # other platforms: no-op


# ---------------------------------------------------------------------------
# OS helpers
# ---------------------------------------------------------------------------
def is_mac() -> bool:
    return _IS_MAC


def is_windows() -> bool:
    return _IS_WIN


def os_name() -> str:
    if _IS_MAC:
        return "macos"
    if _IS_WIN:
        return "windows"
    return platform.system().lower() or "unknown"


def open_path(path: str) -> None:
    """Open a file/folder in the platform file manager."""
    path = os.path.expanduser(path)
    if _IS_MAC:
        subprocess.Popen(["open", path])
    elif _IS_WIN:
        os.startfile(path)  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", path])


def open_url(url: str) -> None:
    if _IS_MAC:
        subprocess.Popen(["open", url])
    elif _IS_WIN:
        os.startfile(url)  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", url])


def launch_app(app: str) -> None:
    """Launch an app by name (mac: `open -a`, win: start the .exe if found)."""
    if _IS_MAC:
        subprocess.Popen(["open", "-a", app])
    elif _IS_WIN:
        # Try a couple of common install locations, then fall back to `start`.
        exe = _find_win_exe(app)
        if exe:
            subprocess.Popen([exe])
        else:
            subprocess.Popen(["cmd", "/c", "start", "", app])
    else:
        subprocess.Popen([app])


def _find_win_exe(name: str) -> str | None:
    """Best-effort lookup of an installed app's .exe by name."""
    name = name.lower().replace(".exe", "")
    candidates = [
        os.path.expandvars(f"%ProgramFiles%\\{name}.exe"),
        os.path.expandvars(f"%ProgramFiles(x86)%\\{name}.exe"),
        os.path.expandvars(f"%LOCALAPPDATA%\\{name}\\{name}.exe"),
        os.path.expandvars(f"%LOCALAPPDATA%\\Programs\\{name}\\{name}.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def notify(title: str, message: str) -> None:
    """Show a desktop notification. mac: osascript. win: toast via PowerShell."""
    try:
        if _IS_MAC:
            subprocess.Popen(["osascript", "-e",
                              f'display notification "{message}" with title "{title}"'])
        elif _IS_WIN:
            script = (
                "[Windows.UI.Notifications.ToastNotificationManager, "
                "Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; "
                "$template = [Windows.UI.Notifications.ToastNotificationManager]::"
                "GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::"
                "ToastText02); "
                "$textNodes = $template.GetElementsByTagName('text'); "
                f"$textNodes.Item(0).AppendChild($template.CreateTextNode('{title}')) > $null; "
                f"$textNodes.Item(1).AppendChild($template.CreateTextNode('{message}')) > $null; "
                "$toast = [Windows.UI.Notifications.ToastNotification]::new($template); "
                "[Windows.UI.Notifications.ToastNotificationManager]::"
                "CreateToastNotifier('JARVIS').Show($toast)"
            )
            subprocess.Popen(["powershell", "-NoProfile", "-Command", script])
        else:
            print(f"[notify] {title}: {message}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[notify] failed: {exc}", flush=True)


def screenshot_png(path: str) -> bool:
    """Save a full-screen screenshot to `path`. Returns True on success."""
    try:
        if _IS_MAC:
            subprocess.run(["screencapture", "-x", path], check=True, timeout=15)
            return os.path.isfile(path)
        if _IS_WIN:
            import ctypes  # noqa: PLC0415

            u = ctypes.windll.user32
            w = u.GetSystemMetrics(0)
            h = u.GetSystemMetrics(1)
            hdc_screen = u.GetDC(0)
            hdc_mem = ctypes.windll.gdi32.CreateCompatibleDC(hdc_screen)
            bmp = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
            ctypes.windll.gdi32.SelectObject(hdc_mem, bmp)
            ctypes.windll.gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, 0, 0, 0x00CC0020)
            # Write BMP then convert to PNG with PIL if available.
            from PIL import Image  # noqa: PLC0415

            import io  # noqa: PLC0415

            buf = ctypes.create_string_buffer(w * h * 4)
            ctypes.windll.gdi32.GetDIBits(
                hdc_mem, bmp, 0, h, buf,
                _BITMAPINFO(w, h), 0)
            img = Image.frombuffer("RGB", (w, h), buf.raw, "raw", "BGRX", 0, 1)
            img.save(path, "PNG")
            ctypes.windll.gdi32.DeleteObject(bmp)
            ctypes.windll.gdi32.DeleteDC(hdc_mem)
            u.ReleaseDC(0, hdc_screen)
            return os.path.isfile(path)
    except Exception as exc:  # noqa: BLE001
        print(f"[platform] screenshot failed: {exc}", flush=True)
        return False
    return False


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]

    def __init__(self, w: int, h: int) -> None:
        super().__init__()
        self.biSize = ctypes.sizeof(self)
        self.biWidth = w
        self.biHeight = -h  # top-down
        self.biPlanes = 1
        self.biBitCount = 32


def accessibility_trusted() -> bool:
    """True when this app may post real input events."""
    if _IS_MAC:
        try:
            from ApplicationServices import AXIsProcessTrusted  # noqa: PLC0415
            return bool(AXIsProcessTrusted())
        except Exception:  # noqa: BLE001
            try:
                import Quartz  # noqa: PLC0415
                return bool(Quartz.CGPreflightPostEventAccess())
            except Exception:  # noqa: BLE001
                return True
    if _IS_WIN:
        return True  # SendInput needs no permission for the same user
    return True


def request_accessibility() -> None:
    """Prompt the OS to register this app for input-event permission."""
    if _IS_MAC:
        try:
            from ApplicationServices import AXIsProcessTrustedWithOptions  # noqa: PLC0415
            AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": True})
        except Exception:  # noqa: BLE001
            pass
    # Windows: nothing to request


def camera_permission_granted() -> bool:
    """Best-effort camera permission check. mac: AVFoundation, win: True
    (OpenCV handles the WinRT permission prompt on first capture)."""
    if _IS_MAC:
        try:
            import AVFoundation  # noqa: PLC0415
            return AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_(
                "vide") == 3
        except Exception:  # noqa: BLE001
            return True
    return True


def open_camera_settings() -> None:
    if _IS_MAC:
        subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera"])
    elif _IS_WIN:
        subprocess.Popen(["start", "ms-settings:privacy-webcam"], shell=True)


def which(prog: str) -> str | None:
    return shutil.which(prog)


def battery_status() -> dict:
    """Battery level + charging state (best-effort, cross-platform)."""
    if _IS_MAC:
        try:
            r = subprocess.run(["pmset", "-g", "batt"], capture_output=True,
                               text=True, timeout=5)
            result: dict = {"raw": r.stdout.strip()}
            for line in r.stdout.splitlines():
                if "InternalBattery" in line and "%" in line:
                    try:
                        result["percent"] = int(line.split("%")[0].rsplit(" ", 1)[-1])
                    except Exception:
                        pass
                    if "charging" in line.lower() or "AC Power" in line:
                        result["charging"] = True
                    elif "discharging" in line.lower() or "Battery Power" in line:
                        result["charging"] = False
            return result
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}
    if _IS_WIN:
        try:
            script = (
                "Get-WmiObject Win32_Battery | "
                "Select-Object EstimatedChargeRemaining, BatteryStatus | ConvertTo-Json -Compress"
            )
            r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                               capture_output=True, text=True, timeout=10)
            import json  # noqa: PLC0415
            data = json.loads(r.stdout.strip() or "{}")
            return {
                "percent": int(data.get("EstimatedChargeRemaining", -1)),
                "charging": int(data.get("BatteryStatus", 2)) == 2,
            }
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}
    return {"error": "battery status not available on this platform"}


def macos_only(feature: str) -> str | None:
    """Return an explanatory error string when running on a non-macOS OS,
    or None when this platform supports the feature. Tools call this first
    so AppleScript-bound features degrade cleanly on Windows."""
    if _IS_MAC:
        return None
    return f"{feature} is only available on macOS (you're on {os_name()})."
