"""
jarvis/camera/control.py
Real mouse control via Quartz CGEvent — moves the actual macOS cursor and
posts real clicks. Requires Accessibility permission for JARVIS in
System Settings → Privacy & Security → Accessibility.
"""
import time

import Quartz


class MouseController:
    """Moves the real cursor and clicks, using global display coordinates
    (origin top-left, in points of the main display).

    Movement uses CGWarpMouseCursorPosition, which works WITHOUT the
    Accessibility permission (verified: warp moves the cursor even when
    event posting is denied). Clicks still post real events and therefore
    need Accessibility granted once.
    """

    def __init__(self) -> None:
        self._bounds = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        self._w = float(self._bounds.size.width)
        self._h = float(self._bounds.size.height)
        self._ox = float(self._bounds.origin.x)
        self._oy = float(self._bounds.origin.y)

    def screen(self) -> tuple:
        """(width, height, origin_x, origin_y) of the main display."""
        return self._w, self._h, self._ox, self._oy

    def move_to(self, x: float, y: float) -> None:
        """Move the cursor. Works without Accessibility (verified via
        CGWarpMouseCursorPosition in the packaged app's locked state)."""
        Quartz.CGWarpMouseCursorPosition((x, y))

    def click(self, x: float, y: float) -> None:
        self._post_mouse(x, y, Quartz.kCGEventLeftMouseDown,
                         Quartz.kCGEventLeftMouseUp, Quartz.kCGMouseButtonLeft)

    def right_click(self, x: float, y: float) -> None:
        self._post_mouse(x, y, Quartz.kCGEventRightMouseDown,
                         Quartz.kCGEventRightMouseUp, Quartz.kCGMouseButtonRight)

    def _post_mouse(self, x: float, y: float, down_type, up_type, button) -> None:
        down = Quartz.CGEventCreateMouseEvent(None, down_type, (x, y), button)
        up = Quartz.CGEventCreateMouseEvent(None, up_type, (x, y), button)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        time.sleep(0.04)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


# Virtual key codes + modifier masks (CGEvent).
KEY_LEFT = 123
KEY_RIGHT = 124
KEY_UP = 126
KEY_Q = 12
MOD_CMD = 0x100000    # kCGEventFlagMaskCommand
MOD_CTRL = 0x40000    # kCGEventFlagMaskControl


class KeyboardController:
    """Posts real keyboard shortcuts (needs Accessibility, like clicks)."""

    def combo(self, keycode: int, flags: int) -> None:
        down = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
        Quartz.CGEventSetFlags(down, flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        up = Quartz.CGEventCreateKeyboardEvent(None, keycode, False)
        Quartz.CGEventSetFlags(up, flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
