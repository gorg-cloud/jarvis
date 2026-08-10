"""
jarvis/camera/gestures.py
Whole-hand gesture recognition for MODE 1 (cursor). Turns the 21 MediaPipe
hand landmarks into actions, tracking ALL fingers:

  peace sign (✌️) held 3s       -> "close_app"        (Cmd+Q)
  fist swipe left/right         -> "desktop_left/right" (Ctrl+Left/Right)

(Pinch clicks live in window.py — thumb↔finger distance, normalized by hand
size.) A fist is deliberate — you never make one while steering the cursor —
so the fist swipe needs no arming: make a fist and punch it left or right.
The peace sign is also deliberate enough that a 3s hold closes the app.
Actions are edge-triggered with a cooldown so each fires once.
"""
from __future__ import annotations

import time

WRIST = 0
THUMB_TIP = 4
THUMB_IP = 3                     # thumb interphalangeal joint
PALM = 9                         # middle-finger MCP — palm-center proxy
TIPS = (8, 12, 16, 20)           # index, middle, ring, pinky tips
PIPS = (6, 10, 14, 18)           # matching PIP joints

_FIST_HOLD = 3.0                 # seconds a peace sign must be held to close app
_SWIPE_WINDOW = 0.25             # seconds of hand history used for swipes
_SWIPE_DIST = 0.16               # normalized x travel required for a swipe
_SWIPE_SPEED = 0.7               # palm speed (norm units/s) required for a swipe
_COOLDOWN = 1.5                  # seconds between whole-hand actions


def _dist(a, b) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


class GestureEngine:
    """Recognizer: feed 21 landmarks each frame, get actions. `current` is a
    plain-English readout of what the hand looks like right now (tracks all
    fingers, including the thumb)."""

    def __init__(self) -> None:
        self.current = "TRACK"
        self._peace_start: float | None = None   # peace-hold timer (close app)
        self._x_hist: list = []       # (time, palm_x) for fist swipes
        self._last_action_t = 0.0

    def update(self, pts, now: float | None = None) -> str | None:
        now = now or time.time()
        palm = pts[PALM]

        extended = [self._extended(pts, t, p) for t, p in zip(TIPS, PIPS)]
        thumb_out = self._thumb_extended(pts)
        n_ext = sum(extended)
        all_ext = all(extended) and thumb_out
        none_ext = not any(extended)
        peace = extended[0] and extended[1] and not extended[2] and not extended[3]

        # Plain-English status that tracks every finger.
        if none_ext:
            self.current = "FIST"
        elif n_ext == 1:
            self.current = "ONE FINGER"
        elif peace:
            self.current = "PEACE"
        elif all_ext:
            self.current = "OPEN HAND"
        else:
            self.current = f"{n_ext} FINGERS"

        self._x_hist.append((now, palm[0]))
        while self._x_hist and now - self._x_hist[0][0] > _SWIPE_WINDOW:
            self._x_hist.pop(0)

        cooldown_ok = now - self._last_action_t > _COOLDOWN
        action: str | None = None

        # ---- Fist swipe left/right -> switch desktop ----------------------
        # A fist is deliberate (you never steer the cursor with one), so a
        # fast lateral punch is all it takes — no arming, no hold.
        if none_ext and cooldown_ok:
            if len(self._x_hist) >= 3:
                t0, x0 = self._x_hist[0]
                dx = palm[0] - x0
                dt = now - t0
                if (dt > 0.05 and abs(dx) > _SWIPE_DIST
                        and abs(dx) / max(dt, 1e-3) > _SWIPE_SPEED):
                    action = "desktop_right" if dx > 0 else "desktop_left"
                    self._x_hist.clear()
                    self._last_action_t = now

        # ---- Peace sign held -> close app ----------------------------------
        if peace and cooldown_ok and action is None:
            if self._peace_start is None:
                self._peace_start = now
            elif now - self._peace_start >= _FIST_HOLD:
                action = "close_app"
                self._peace_start = None
                self._last_action_t = now
            else:
                # countdown feedback so you know it's arming
                left = max(1, int(_FIST_HOLD - (now - self._peace_start)) + 1)
                self.current = f"CLOSE APP IN {left}s"
        else:
            self._peace_start = None

        return action

    @staticmethod
    def _extended(pts, tip: int, pip: int) -> bool:
        """A finger is extended when its tip is clearly farther from the wrist
        than its PIP joint (works for a hand facing the camera)."""
        w = pts[WRIST]
        return _dist(pts[tip], w) > _dist(pts[pip], w) * 1.18

    @staticmethod
    def _thumb_extended(pts) -> bool:
        """Thumb is out when its tip is clearly farther from the wrist than
        its IP joint."""
        w = pts[WRIST]
        return _dist(pts[THUMB_TIP], w) > _dist(pts[THUMB_IP], w) * 1.1
