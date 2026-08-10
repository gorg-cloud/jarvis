"""
jarvis/camera/window.py
JARVIS Gesture Control window — Stark-Industries styling.

MODE 1 (CURSOR): move your index finger to move the mouse; pinch thumb +
index together to click (pinch is normalized by hand size + needs a short
hold, so it's precise). Peace sign (index + middle out) held 3s closes the
frontmost app; a fist swipe left/right switches desktops. The feed is
mirrored (selfie view), so moving your hand right moves the cursor right.

Run with: python -m jarvis.camera   (or the packaged app: JARVIS.app --gestures)
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
import traceback

_DEBUG_LOG = os.path.expanduser("~/.jarvis/debug.log")


def _debug(msg: str) -> None:
    try:
        with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} [gestures] {msg}\n")
    except Exception:
        pass

# Let the OS handle the camera-permission prompt (NSCameraUsageDescription in
# the bundle) instead of cv2 trying to spin the run loop from the capture thread.
os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")

import cv2
import numpy as np

from PyQt6.QtCore import QPointF, QRectF, QThread, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QSlider, QStackedWidget, QVBoxLayout, QWidget,
)

from jarvis.camera.control import (
    KEY_LEFT, KEY_Q, KEY_RIGHT, MOD_CMD, MOD_CTRL,
    KeyboardController, MouseController,
)
from jarvis.camera.gestures import GestureEngine
from jarvis.camera.tracker import HandTracker
from jarvis.hud.theme import BG, CYAN, WHITE_DIM, mono

_CYAN = QColor("#00f0ff")
_CYAN_DIM = QColor(0, 240, 255, 150)
_ERR = QColor("#ff8a8a")

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
]

THUMB_TIP, INDEX_TIP = 4, 8

_DEFAULT_CFG = {
    "speed": 1.2,          # hand-range multiplier (small hand moves cover more screen)
    "smooth": 0.5,         # EMA response — lower = smoother/less shaky
    # Pinch thresholds are now RATIOS of hand size (thumb↔index gap ÷ palm
    # length), so a pinch is recognized identically near or far from the
    # camera — that's what makes it precise.
    "pinch_press": 0.24,   # ratio that triggers a click
    "pinch_release": 0.38,
}


class _Pinch:
    """Pinch state machine with hysteresis + cooldown + hold-to-confirm
    (edge-triggered click). The fingers must stay pinched for `hold` seconds
    before the click fires, so fast accidental brushes never click.
    Thresholds come from the live settings on every update."""

    def __init__(self, cooldown: float = 0.4, hold: float = 0.13) -> None:
        self.cooldown = cooldown
        self.hold = hold
        self.pinched = False
        self._last = 0.0
        self._press_at: float | None = None

    def update(self, dist: float, press: float, release: float) -> str | None:
        """Feed the (hand-size-normalized) thumb↔index distance. Returns
        'press', 'release' or None. A click should fire on 'press'."""
        now = time.time()
        if not self.pinched and dist < press and (now - self._last) > self.cooldown:
            if self._press_at is None:
                self._press_at = now
            elif now - self._press_at >= self.hold:
                self.pinched = True
                self._press_at = None
                return "press"
        else:
            self._press_at = None
        if self.pinched and dist > release:
            self.pinched = False
            self._last = now
            return "release"
        return None

    def reset(self) -> None:
        self.pinched = False
        self._press_at = None
        self._last = 0.0


class _PermissionThread(QThread):
    """Requests macOS camera permission (shows the system prompt) on its own
    thread so the UI never blocks. Emits granted=True when the camera is
    available for capture."""

    granted = pyqtSignal(bool)

    def run(self) -> None:
        try:
            import AVFoundation
        except Exception:
            # Can't introspect — let the capture thread try on its own.
            self.granted.emit(True)
            return

        status = AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_("vide")
        if status == 3:            # AVAuthorizationStatusAuthorized
            self.granted.emit(True)
            return
        if status == 2:            # AVAuthorizationStatusDenied — no more prompts
            self.granted.emit(False)
            return
        # Not determined yet — ask (this is what shows the system prompt).
        result: list = []
        done = threading.Event()

        def _cb(granted: bool) -> None:
            result.append(bool(granted))
            done.set()

        AVFoundation.AVCaptureDevice.requestAccessForMediaType_completionHandler_("vide", _cb)
        done.wait(20)
        self.granted.emit(bool(result and result[0]))


class _CaptureThread(QThread):
    """Grabs webcam frames, runs hand tracking, drives the real mouse."""

    frame_ready = pyqtSignal(object, object, bool, str, int, float, float)  # frame, hands, pinch, status, clicks, cursor_nx, cursor_ny
    failed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._stop = False
        self._pause = False
        self._mouse = MouseController()
        self._kbd = KeyboardController()
        self._pinch = _Pinch()
        self._pinch_r = _Pinch(cooldown=0.5)   # thumb+middle -> right-click
        self._pen_pinch = _Pinch(cooldown=0.3, hold=0.10)  # mode 2 pen down/up
        self._gestures = GestureEngine()
        self._smooth: tuple | None = None
        self._last_pos: tuple | None = None
        self._recent: list = []          # moving-average window (jitter reduction)
        self._clicks = 0
        self.cfg = dict(_DEFAULT_CFG)    # live-adjustable from the settings panel
        self._mode = 1                   # 1 = cursor, 2 = whiteboard

    def set_mode(self, mode: int) -> None:
        self._mode = mode
        # Fresh state per mode: no stale pen/click state or old averages.
        self._smooth = None
        self._recent.clear()
        self._last_pos = None
        self._pinch.reset()
        self._pinch_r.reset()
        self._pen_pinch.reset()

    def stop(self) -> None:
        self._stop = True

    def _execute_gesture(self, action: str) -> None:
        _debug(f"gesture action: {action}")
        if action == "close_app":
            self._kbd.combo(KEY_Q, MOD_CMD)
        elif action == "desktop_left":
            self._kbd.combo(KEY_LEFT, MOD_CTRL)
        elif action == "desktop_right":
            self._kbd.combo(KEY_RIGHT, MOD_CTRL)

    def set_paused(self, paused: bool) -> None:
        self._pause = paused

    def run(self) -> None:
        try:
            tracker = HandTracker()
        except Exception as exc:
            self.failed.emit(f"Hand-tracking model failed to load: {exc}")
            return

        # Retry opening the camera: if the user grants Camera permission while
        # this window is open, the next attempt succeeds and control starts.
        cap = None
        for _attempt in range(20):
            if self._stop:
                tracker.close()
                return
            cap = cv2.VideoCapture(0)
            if cap.isOpened():
                break
            if cap is not None:
                cap.release()
            cap = None
            self.frame_ready.emit(None, [], False, "WAITING FOR CAMERA…", self._clicks,
                                  -1.0, -1.0)
            time.sleep(3)
        if cap is None:
            tracker.close()
            self.failed.emit(
                "Camera unavailable. Grant permission in System Settings → "
                "Privacy & Security → Camera → JARVIS, then reopen gesture control."
            )
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        try:
            while not self._stop:
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                frame = cv2.flip(frame, 1)                      # mirror: selfie view
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame = np.ascontiguousarray(frame)

                hands: list = []
                pinch = False
                status = "SCANNING"
                cursor_nx, cursor_ny = -1.0, -1.0

                if not self._pause:
                    try:
                        hands = tracker.detect(frame)
                    except Exception:
                        hands = []
                    if hands:
                        pts = hands[0]
                        tip, thumb = pts[INDEX_TIP], pts[THUMB_TIP]
                        cfg = self.cfg
                        # Hand size = wrist→middle-MCP distance. Dividing the
                        # pinch gap by it makes thresholds scale-invariant, so
                        # the same pinch works near or far from the camera.
                        hand_size = max(
                            ((pts[0][0] - pts[9][0]) ** 2
                             + (pts[0][1] - pts[9][1]) ** 2) ** 0.5,
                            1e-4,
                        )
                        if self._mode == 1:
                            # ---- MODE 1: cursor control -------------------
                            # Map to the real screen. The feed is already mirrored
                            # (selfie view), so landmark coords match 1:1.
                            # Boost + clamping covers the whole screen; EMA +
                            # moving average + dead zone stop the cursor shaking.
                            sw, sh, ox, oy = self._mouse.screen()
                            tx = ox + (0.5 + (tip[0] - 0.5) * cfg["speed"]) * sw
                            ty = oy + (0.5 + (tip[1] - 0.5) * cfg["speed"]) * sh
                            tx = max(ox, min(ox + sw, tx))
                            ty = max(oy, min(oy + sh, ty))
                            if self._smooth is None:
                                self._smooth = (tx, ty)
                            else:
                                self._smooth = (
                                    self._smooth[0] + (tx - self._smooth[0]) * cfg["smooth"],
                                    self._smooth[1] + (ty - self._smooth[1]) * cfg["smooth"],
                                )
                            self._recent.append(self._smooth)
                            if len(self._recent) > 4:
                                self._recent.pop(0)
                            avg = (
                                sum(p[0] for p in self._recent) / len(self._recent),
                                sum(p[1] for p in self._recent) / len(self._recent),
                            )
                            if (self._last_pos is None
                                    or abs(avg[0] - self._last_pos[0]) > 2
                                    or abs(avg[1] - self._last_pos[1]) > 2):
                                self._mouse.move_to(*avg)
                                self._last_pos = avg
                            cursor_nx = (avg[0] - ox) / sw
                            cursor_ny = (avg[1] - oy) / sh

                            dist = ((((tip[0] - thumb[0]) ** 2
                                      + (tip[1] - thumb[1]) ** 2) ** 0.5)
                                     / hand_size)
                            # Mutual exclusion so left and right pinch never
                            # confuse the system: the left-pinch state machine
                            # is fed an "open" distance while the middle finger
                            # is near the thumb, and vice-versa for right-click.
                            middle = pts[12]
                            d_mid = ((((tip[0] - middle[0]) ** 2
                                       + (tip[1] - middle[1]) ** 2) ** 0.5)
                                      / hand_size)
                            feed_left = dist if d_mid > cfg["pinch_release"] else 9.0
                            feed_right = d_mid if dist > cfg["pinch_release"] else 9.0
                            a_left = self._pinch.update(feed_left, cfg["pinch_press"],
                                                        cfg["pinch_release"])
                            a_right = self._pinch_r.update(feed_right, cfg["pinch_press"] * 1.1,
                                                           cfg["pinch_release"] * 1.1)
                            if a_left == "press":
                                self._mouse.click(*avg)
                                self._clicks += 1
                                pinch = True
                                status = "CLICK!"
                            elif a_right == "press":
                                self._mouse.right_click(*avg)
                                self._clicks += 1
                                status = "RIGHT-CLICK!"
                            else:
                                g = self._gestures.update(pts)
                                if g:
                                    self._execute_gesture(g)
                                    status = f"⚡ {g.upper()}!"
                                elif self._pinch.pinched:
                                    status = "PINCH"
                                elif self._pinch_r.pinched:
                                    status = "RIGHT-PINCH"
                                else:
                                    status = f"TRACKING · {self._gestures.current}"
                        else:
                            # ---- MODE 2: whiteboard drawing ----------------
                            # Pen down/up runs through the pinch state machine
                            # (hysteresis + hold), so the pen can't flap at the
                            # threshold — that's what made strokes cutty.
                            dist = ((((tip[0] - thumb[0]) ** 2
                                      + (tip[1] - thumb[1]) ** 2) ** 0.5)
                                     / hand_size)
                            self._pen_pinch.update(dist, cfg["pinch_press"],
                                                   cfg["pinch_release"])
                            s = cfg["smooth"]
                            if self._smooth is None:
                                self._smooth = (tip[0], tip[1])
                            else:
                                self._smooth = (
                                    self._smooth[0] + (tip[0] - self._smooth[0]) * s,
                                    self._smooth[1] + (tip[1] - self._smooth[1]) * s,
                                )
                            self._recent.append(self._smooth)
                            if len(self._recent) > 4:
                                self._recent.pop(0)
                            avg = (
                                sum(p[0] for p in self._recent) / len(self._recent),
                                sum(p[1] for p in self._recent) / len(self._recent),
                            )
                            if self._pen_pinch.pinched:
                                cursor_nx, cursor_ny = avg  # pen down
                                status = "WRITING — PINCH HELD"
                            else:
                                cursor_nx, cursor_ny = -1.0, -1.0  # pen up
                                status = "PINCH TO WRITE · OPEN = MOVE"
                    else:
                        status = "HAND LOST"
                else:
                    status = "PAUSED"

                self.frame_ready.emit(frame, hands, pinch, status, self._clicks,
                                      cursor_nx, cursor_ny)
        finally:
            cap.release()
            tracker.close()


class _VideoWidget(QWidget):
    """Camera feed + cyan skeleton overlay + fingertip targeting reticle."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(640, 400)
        self._frame: QImage | None = None
        self._hands: list = []
        self._pinch = False
        self._status = "STARTING…"
        self._message: str | None = None
        self._banner: str | None = None

    def set_frame(self, rgb, hands, pinch, status) -> None:
        if rgb is None:
            self._status = status
            self.update()
            return
        h, w, _ = rgb.shape
        self._frame = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
        self._hands = hands or []
        self._pinch = pinch
        self._status = status
        self.update()

    def show_message(self, msg: str) -> None:
        self._message = msg
        self.update()

    def show_banner(self, msg: str) -> None:
        self._banner = msg
        self.update()

    def clear_banner(self) -> None:
        self._banner = None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#05070a"))

        if self._message is not None:
            p.setPen(_ERR)
            p.setFont(mono(12, bold=True))
            p.drawText(self.rect().adjusted(20, 0, -20, 0),
                       Qt.AlignmentFlag.AlignCenter, self._message)
            p.end()
            return

        if self._frame is None:
            p.setPen(_CYAN_DIM)
            p.setFont(mono(11))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "AWAITING CAMERA FEED…")
            p.end()
            return

        img_w, img_h = self._frame.width(), self._frame.height()
        scale = min(self.width() / img_w, self.height() / img_h)
        dw, dh = int(img_w * scale), int(img_h * scale)
        dx, dy = (self.width() - dw) // 2, (self.height() - dh) // 2
        p.drawImage(dx, dy, self._frame, 0, 0, img_w, img_h)

        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for pts in self._hands:
            for a, b in HAND_CONNECTIONS:
                p.setPen(QPen(QColor(0, 240, 255, 130), 1.5))
                p.drawLine(int(dx + pts[a][0] * dw), int(dy + pts[a][1] * dh),
                           int(dx + pts[b][0] * dw), int(dy + pts[b][1] * dh))
            for x, y in pts:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 240, 255, 200))
                p.drawEllipse(int(dx + x * dw) - 2, int(dy + y * dh) - 2, 4, 4)
            tip = pts[INDEX_TIP]
            cx, cy = int(dx + tip[0] * dw), int(dy + tip[1] * dh)
            col = QColor("#ffffff") if self._pinch else QColor("#37d6ff")
            # Big glowing cursor dot + crosshair so you can always see where
            # the mouse is aiming.
            halo = QRadialGradient(QPointF(cx, cy), 26)
            halo.setColorAt(0.0, QColor(0, 240, 255, 190))
            halo.setColorAt(1.0, QColor(0, 240, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(halo)
            p.drawEllipse(QPointF(cx, cy), 26, 26)
            p.setPen(QPen(col, 2))
            p.setBrush(col)
            p.drawEllipse(QPointF(cx, cy), 7, 7)
            p.drawLine(cx - 20, cy, cx - 10, cy)
            p.drawLine(cx + 10, cy, cx + 20, cy)
            p.drawLine(cx, cy - 20, cx, cy - 10)
            p.drawLine(cx, cy + 10, cx, cy + 20)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 240, 255, 40))
        p.drawRoundedRect(8, 8, 150, 26, 6, 6)
        p.setPen(_CYAN)
        p.setFont(mono(9, bold=True))
        p.drawText(18, 25, self._status)

        if self._banner:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 92, 92, 205))
            p.drawRoundedRect(QRectF(0, self.height() - 46, self.width(), 46), 0, 0)
            p.setPen(QColor("#ffffff"))
            p.setFont(mono(9, bold=True))
            p.drawText(
                QRectF(10, self.height() - 46, self.width() - 20, 46),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                | Qt.TextFlag.TextWordWrap,
                self._banner,
            )
        p.end()


def _ocr_image(path: str) -> str:
    """Transcribe handwritten text from an image via macOS Vision (offline)."""
    try:
        import Foundation
        import Vision
    except Exception:
        return ""
    try:
        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(
            Foundation.NSURL.fileURLWithPath_(path), None)
        req = Vision.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        req.setUsesLanguageCorrection_(True)
        ok, _err = handler.performRequests_error_([req], None)
        if not ok:
            return ""
        parts = []
        for obs in (req.results() or []):
            cand = obs.topCandidates_(1)
            if cand and len(cand):
                parts.append(cand[0].string())
        return " ".join(parts)
    except Exception:
        return ""


class _CanvasWidget(QWidget):
    """Whiteboard canvas — fingertip strokes drawn with the marker settings."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(640, 400)
        self._strokes: list = []
        self._current: list | None = None
        self._color = QColor("#00f0ff")
        self._width = 8.0
        self._eraser = False

    def set_brush(self, color: QColor, width: float) -> None:
        self._color = color
        self._width = width

    def set_eraser(self, on: bool) -> None:
        self._eraser = on

    def begin(self, x: float, y: float) -> None:
        color = QColor("#ffffff") if self._eraser else self._color
        self._current = [color, self._width, [(x, y)]]
        self._strokes.append(self._current)

    def add(self, x: float, y: float) -> None:
        if self._current is None:
            self.begin(x, y)
        self._current[2].append((x, y))
        self.update()

    def end(self) -> None:
        self._current = None

    def clear(self) -> None:
        self._strokes.clear()
        self._current = None
        self.update()

    def has_strokes(self) -> bool:
        return any(len(s[2]) >= 2 for s in self._strokes)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.GlobalColor.white)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for color, width, pts in self._strokes:
            if len(pts) < 2:
                continue
            path = QPainterPath()
            path.moveTo(pts[0][0], pts[0][1])
            for x, y in pts[1:]:
                path.lineTo(x, y)
            p.setPen(QPen(color, width, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPath(path)
        p.end()

    def render_image(self, scale: float = 2.0, ink: str | None = None) -> QImage:
        """Render strokes to a high-res image (white background). Pass `ink`
        (e.g. '#000000') to force the stroke color — used for OCR."""
        img = QImage(int(self.width() * scale), int(self.height() * scale),
                     QImage.Format.Format_RGB32)
        img.fill(Qt.GlobalColor.white)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for color, width, pts in self._strokes:
            if len(pts) < 2:
                continue
            path = QPainterPath()
            path.moveTo(pts[0][0] * scale, pts[0][1] * scale)
            for x, y in pts[1:]:
                path.lineTo(x * scale, y * scale)
            c = QColor(ink) if ink else color
            p.setPen(QPen(c, max(width * scale, 2.0), Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPath(path)
        p.end()
        return img


class _ScreenMap(QWidget):
    """Miniature screen outline with a glowing dot at the current cursor spot."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(210, 130)
        self._cursor: tuple | None = None

    def set_cursor(self, nx: float, ny: float) -> None:
        self._cursor = (nx, ny) if nx >= 0 else None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        m = 10
        rect = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#0a1218"))
        p.drawRoundedRect(rect, 6, 6)
        p.setPen(QPen(QColor(0, 240, 255, 90), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 6, 6)
        if self._cursor is not None:
            nx, ny = self._cursor
            cx = rect.left() + nx * rect.width()
            cy = rect.top() + ny * rect.height()
            halo = QRadialGradient(QPointF(cx, cy), 18)
            halo.setColorAt(0.0, QColor(0, 240, 255, 200))
            halo.setColorAt(1.0, QColor(0, 240, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(halo)
            p.drawEllipse(QPointF(cx, cy), 18, 18)
            p.setBrush(QColor("#bffcff"))
            p.drawEllipse(QPointF(cx, cy), 4.5, 4.5)
        p.end()


class GestureWindow(QMainWindow):
    """JARVIS Gesture Control — MODE 1: cursor + pinch-to-click."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("J.A.R.V.I.S. — Gesture Control")
        self.setStyleSheet(f"background: {BG.name()};")
        self.resize(760, 760)

        self._thread = _CaptureThread()
        self._thread.frame_ready.connect(self._on_frame)
        self._thread.failed.connect(self._on_failed)

        self._perm = _PermissionThread()
        self._perm.granted.connect(self._on_permission)
        self._opened_settings = False

        self._build_ui()
        self._setup_shortcuts()
        self._set_marker_color("#00f0ff")
        self._check_accessibility()
        self._status.setText("WAITING FOR CAMERA PERMISSION…")
        _debug("window constructed, requesting camera permission")
        self._perm.start()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel("J.A.R.V.I.S. — GESTURE CONTROL")
        title.setFont(mono(16, bold=True))
        title.setStyleSheet(f"color: {CYAN.name()}; background: transparent;")
        title_box.addWidget(title)
        sub = QLabel("MODE 1 · CURSOR — MOVE YOUR INDEX FINGER · PINCH TO CLICK")
        sub.setFont(mono(9))
        sub.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent;")
        title_box.addWidget(sub)
        header.addLayout(title_box)
        header.addStretch()

        self._status = QLabel("STARTING…")
        self._status.setFont(mono(10, bold=True))
        self._status.setStyleSheet(f"color: {CYAN.name()}; background: transparent;")
        header.addWidget(self._status)
        root.addLayout(header)

        divider = QWidget()
        divider.setFixedHeight(2)
        divider.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            " stop:0 rgba(0,240,255,0), stop:0.5 rgba(0,240,255,160), stop:1 rgba(0,240,255,0));"
        )
        root.addWidget(divider)

        # ---- Mode switcher -------------------------------------------------
        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_lab = QLabel("MODE")
        mode_lab.setFont(mono(9, bold=True))
        mode_lab.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent;")
        mode_row.addWidget(mode_lab)
        self._mode_buttons = {}
        for mid, label in ((1, "1 · CURSOR"), (2, "2 · WHITEBOARD")):
            b = QPushButton(label)
            b.setFont(mono(9, bold=True))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c, m=mid: self._select_mode(m))
            mode_row.addWidget(b)
            self._mode_buttons[mid] = b
        mode_row.addStretch()
        root.addLayout(mode_row)

        self._mode = 1
        self._prev_draw = None
        self._marker_color = "#00f0ff"
        # Auto-OCR: a short pause in drawing converts handwriting to text
        # automatically ("whiteboard font" display, Marker Felt below).
        self._ocr_timer = QTimer(self)
        self._ocr_timer.setInterval(1200)
        self._ocr_timer.setSingleShot(True)
        self._ocr_timer.timeout.connect(self._auto_convert)
        self._paint_mode_buttons()

        # Main content: page 1 = camera feed (mode 1), page 2 = whiteboard.
        self._video = _VideoWidget()
        self._canvas_page = QWidget()
        cv = QVBoxLayout(self._canvas_page)
        cv.setContentsMargins(0, 0, 0, 0)
        self._canvas = _CanvasWidget()
        cv.addWidget(self._canvas, stretch=1)
        self._canvas_text = QLabel("")
        self._canvas_text.setWordWrap(True)
        self._canvas_text.setStyleSheet(
            "color: #1a1a1a; background: #f2f2f2; border-radius: 6px; padding: 10px;"
        )
        self._canvas_text.setFont(QFont("Marker Felt", 26))
        self._canvas_text.setMinimumHeight(64)
        self._canvas_text.hide()
        cv.addWidget(self._canvas_text)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._video)
        self._stack.addWidget(self._canvas_page)

        main = QHBoxLayout()
        main.setSpacing(14)
        main.addWidget(self._stack, stretch=1)
        side = QVBoxLayout()
        side.setSpacing(6)
        side_label = QLabel("◉ CURSOR POSITION")
        side_label.setFont(mono(9, bold=True))
        side_label.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent;")
        side.addWidget(side_label)
        self._screen_map = _ScreenMap()
        side.addWidget(self._screen_map)

        side.addSpacing(10)
        settings_label = QLabel("⚙ SETTINGS")
        settings_label.setFont(mono(9, bold=True))
        settings_label.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent;")
        side.addWidget(settings_label)

        self._speed_slider, _ = self._add_slider(side, "SPEED", 50, 200, 120,
                                                 lambda v: f"{v}%")
        self._smooth_slider, _ = self._add_slider(side, "SMOOTHING", 0, 100, 60,
                                                  lambda v: f"{v}")
        hint = QLabel("LOW = snappy · HIGH = smooth")
        hint.setFont(mono(7))
        hint.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent;")
        side.addWidget(hint)
        self._pinch_slider, _ = self._add_slider(side, "PINCH", 1, 10, 7,
                                                 lambda v: str(v))
        self._size_slider, _ = self._add_slider(side, "SIZE", 2, 40, 8,
                                                lambda v: f"{v}px")

        reset_btn = QPushButton("RESET DEFAULTS")
        reset_btn.setFont(mono(8, bold=True))
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet(
            "QPushButton { background: #0a0a0e; color: #8fd8e0;"
            " border: 1px solid rgba(0,240,255,0.5); border-radius: 6px; padding: 5px 10px; }"
            "QPushButton:hover { background: #0e1a20; }"
        )
        reset_btn.clicked.connect(self._reset_settings)
        side.addWidget(reset_btn)

        side.addStretch()
        main.addLayout(side)
        root.addLayout(main, stretch=1)

        # Whiteboard toolbar (mode 2 only) — wrapped in a widget so it can
        # be shown/hidden with the rest of the canvas page.
        self._canvas_row_widget = QWidget()
        canvas_row = QHBoxLayout(self._canvas_row_widget)
        canvas_row.setContentsMargins(0, 0, 0, 0)
        canvas_row.setSpacing(8)
        color_lab = QLabel("COLOR")
        color_lab.setFont(mono(8, bold=True))
        color_lab.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent;")
        canvas_row.addWidget(color_lab)
        self._color_swatches = {}
        for name, hexv in (("CYAN 1", "#00f0ff"), ("WHITE 2", "#ffffff"), ("BLACK 3", "#111111"),
                           ("RED 4", "#ff4444"), ("GREEN 5", "#44ff88"), ("YELLOW 6", "#ffd400")):
            b = QPushButton()
            b.setFixedSize(26, 26)
            b.setToolTip(f"{name} — press {name[-1]} on keyboard")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c, h=hexv: self._set_marker_color(h))
            canvas_row.addWidget(b)
            self._color_swatches[hexv] = b
        self._erase_btn = QPushButton("ERASE")
        self._erase_btn.setCheckable(True)
        self._erase_btn.clicked.connect(lambda on: self._canvas.set_eraser(on))
        clear_btn = QPushButton("CLEAR")
        clear_btn.clicked.connect(self._canvas.clear)
        self._convert_btn = QPushButton("✎ CONVERT TO TEXT")
        self._convert_btn.clicked.connect(self._convert_canvas)
        self._save_btn = QPushButton("💾 SAVE TO OBSIDIAN")
        self._save_btn.clicked.connect(self._save_whiteboard)
        for b in (self._erase_btn, clear_btn, self._convert_btn, self._save_btn):
            b.setFont(mono(9, bold=True))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                "QPushButton { background: #0a0a0e; color: #8fd8e0;"
                " border: 1px solid rgba(0,240,255,0.5); border-radius: 6px; padding: 7px 12px; }"
                "QPushButton:hover { background: #0e1a20; }"
                "QPushButton:checked { background: #0e3a42; color: #ffffff; }"
            )
        canvas_row.addWidget(self._erase_btn)
        canvas_row.addWidget(clear_btn)
        canvas_row.addStretch()
        canvas_row.addWidget(self._convert_btn)
        canvas_row.addWidget(self._save_btn)
        root.addWidget(self._canvas_row_widget)
        self._canvas_row_widget.setVisible(False)

        info = QHBoxLayout()
        self._clicks = QLabel("CLICKS: 0")
        self._clicks.setFont(mono(10, bold=True))
        self._clicks.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent;")
        info.addWidget(self._clicks)
        info.addStretch()
        self._hint_label = QLabel("pinch=click · th+mid=right-click · peace 3s=close app · fist swipe=desktop")
        self._hint_label.setFont(mono(8))
        self._hint_label.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent;")
        info.addWidget(self._hint_label)
        root.addLayout(info)

        buttons = QHBoxLayout()
        buttons.addStretch()
        accel_btn = QPushButton("ENABLE ACCESSIBILITY")
        accel_btn.clicked.connect(self._open_accessibility_settings)
        self._pause_btn = QPushButton("PAUSE")
        self._pause_btn.clicked.connect(self._toggle_pause)
        stop_btn = QPushButton("STOP")
        stop_btn.setStyleSheet(
            "QPushButton { background: #0a0a0e; color: #ff8a8a;"
            " border: 1px solid rgba(255,92,92,0.5); border-radius: 8px; padding: 9px 20px; }"
            "QPushButton:hover { background: #1a0e0e; }"
        )
        stop_btn.clicked.connect(self.close)
        for b in (accel_btn, self._pause_btn, stop_btn):
            b.setFont(mono(10, bold=True))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                b.styleSheet() or
                "QPushButton { background: #0a0a0e; color: #8fd8e0;"
                " border: 1px solid rgba(0,240,255,0.5); border-radius: 8px; padding: 9px 20px; }"
                "QPushButton:hover { background: #0e1a20; }"
            )
        buttons.addWidget(self._pause_btn)
        buttons.addWidget(stop_btn)
        root.addLayout(buttons)

        self.setCentralWidget(central)

    def _check_accessibility(self) -> None:
        self._accel = False
        self._accel_timer = QTimer(self)
        self._accel_timer.setInterval(2000)
        self._accel_timer.timeout.connect(self._recheck_accessibility)
        self._accel_timer.start()
        self._recheck_accessibility()
        # Ask macOS to register this app for Accessibility and show its prompt
        # (verified needed: the app never appears in the list otherwise).
        if not self._accel:
            self._request_accessibility()

    def _accessibility_trusted(self) -> bool:
        """True when this app may post real click events (Accessibility).
        Movement no longer needs this (warp), but clicks do."""
        try:
            from ApplicationServices import AXIsProcessTrusted
            return bool(AXIsProcessTrusted())
        except Exception:
            pass
        try:
            import Quartz
            return bool(Quartz.CGPreflightPostEventAccess())
        except Exception:
            return True  # can't introspect — assume OK

    def _request_accessibility(self) -> None:
        """Show the system Accessibility prompt (registers this app identity so
        it appears in the list — verified it never appears otherwise)."""
        try:
            import ApplicationServices
            from ApplicationServices import AXIsProcessTrustedWithOptions
            AXIsProcessTrustedWithOptions({ApplicationServices.kAXTrustedCheckOptionPrompt: True})
        except Exception:
            try:
                from ApplicationServices import AXIsProcessTrustedWithOptions
                AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": True})
            except Exception:
                pass

    def _recheck_accessibility(self) -> None:
        trusted = self._accessibility_trusted()
        changed = trusted != self._accel
        self._accel = trusted
        if trusted:
            if changed:
                _debug("accessibility granted — clicks unlocked")
            self._video.clear_banner()
            self._status.setText("TRACKING")
        else:
            if changed:
                _debug("accessibility NOT granted — movement OK (warp), clicks locked")
            self._status.setText("⚠ CLICKS NEED ACCESSIBILITY")
            self._video.show_banner(
                "CURSOR MOVES ALREADY — to unlock PINCH-CLICKS & GESTURE SHORTCUTS, "
                "toggle JARVIS ON in Accessibility (settings opening). "
                "Movement needs no permission."
            )
            if not self._opened_settings:
                self._opened_settings = True
                self._open_accessibility_settings()

    def _open_accessibility_settings(self) -> None:
        subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])

    # ---------------------------------------------------------------- modes

    def _select_mode(self, mid: int) -> None:
        if mid == 2:
            self._mode = 2
            self._thread.set_mode(2)
            self._stack.setCurrentIndex(1)
            self._canvas_row_widget.setVisible(True)
            self._prev_draw = None
            self._paint_mode_buttons()
            self._status.setText("WHITEBOARD — PINCH TO WRITE")
            self._hint_label.setText("pinch=write · open=move · 1-6=color · ✎ convert → save to Obsidian")
            return
        self._mode = 1
        self._thread.set_mode(1)
        self._stack.setCurrentIndex(0)
        self._canvas_row_widget.setVisible(False)
        self._paint_mode_buttons()
        self._status.setText("MODE 1 — CURSOR")
        self._hint_label.setText("pinch=click · th+mid=right-click · peace 3s=close app · fist swipe=desktop")

    def _setup_shortcuts(self) -> None:
        """1-6 switch the marker color (window must be focused)."""
        from PyQt6.QtGui import QKeySequence, QShortcut
        colors = ("#00f0ff", "#ffffff", "#111111", "#ff4444", "#44ff88", "#ffd400")
        for i, hexv in enumerate(colors, 1):
            QShortcut(QKeySequence(str(i)), self,
                      activated=lambda h=hexv: self._set_marker_color(h))

    def _paint_mode_buttons(self) -> None:
        for mid, b in self._mode_buttons.items():
            active = mid == self._mode
            b.setStyleSheet(
                f"QPushButton {{ background: {'#0e3a42' if active else '#0a0a0e'};"
                f" color: {'#ffffff' if active else '#8fd8e0'};"
                f" border: 1px solid {'#00f0ff' if active else 'rgba(0,240,255,0.35)'};"
                f" border-radius: 6px; padding: 5px 12px; }}"
            )

    # ------------------------------------------------------------ settings

    def _add_slider(self, layout, name: str, lo: int, hi: int, val: int, fmt):
        """Add a labeled slider row; returns (slider, value_label)."""
        row = QHBoxLayout()
        row.setSpacing(6)
        lab = QLabel(name)
        lab.setFont(mono(8, bold=True))
        lab.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent;")
        val_lab = QLabel(fmt(val))
        val_lab.setFont(mono(8, bold=True))
        val_lab.setStyleSheet(f"color: {CYAN.name()}; background: transparent;")
        row.addWidget(lab)
        row.addStretch()
        row.addWidget(val_lab)
        layout.addLayout(row)

        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(val)
        s.setStyleSheet(
            "QSlider::groove:horizontal { height: 3px; background: #1c2733; border-radius: 1px; }"
            "QSlider::handle:horizontal { width: 12px; background: #00f0ff;"
            " border-radius: 6px; margin: -5px 0; }"
        )
        s.valueChanged.connect(lambda v, f=fmt, vl=val_lab: vl.setText(f(v)))
        s.valueChanged.connect(lambda _v: self._sync_settings())
        layout.addWidget(s)
        return s, val_lab

    def _sync_settings(self) -> None:
        """Push the slider values into the capture thread's live config."""
        t = self._thread
        t.cfg["speed"] = self._speed_slider.value() / 100.0
        t.cfg["smooth"] = round(0.25 + (100 - self._smooth_slider.value()) * 0.0065, 3)
        pinch = self._pinch_slider.value()
        # Hand-size ratio thresholds: 1 = loosest (0.42), 10 = tightest (0.16).
        t.cfg["pinch_press"] = round(0.42 - (pinch / 10.0) * 0.26, 3)
        t.cfg["pinch_release"] = round(t.cfg["pinch_press"] + 0.14, 3)
        _debug(f"settings: speed={t.cfg['speed']} smooth={t.cfg['smooth']} "
               f"press={t.cfg['pinch_press']} release={t.cfg['pinch_release']}")

    def _reset_settings(self) -> None:
        self._speed_slider.setValue(120)
        self._smooth_slider.setValue(60)
        self._pinch_slider.setValue(7)

    # --------------------------------------------------------------- I/O

    def _toggle_pause(self) -> None:
        paused = not self._thread._pause
        self._thread.set_paused(paused)
        self._pause_btn.setText("RESUME" if paused else "PAUSE")

    def _on_frame(self, frame, hands, pinch, status, clicks, nx, ny) -> None:
        self._video.set_frame(frame, hands, pinch, status)
        if self._mode == 2:
            if nx >= 0:
                cw = max(1, self._canvas.width())
                ch = max(1, self._canvas.height())
                x, y = nx * cw, ny * ch
                if self._prev_draw is None:
                    self._canvas.begin(x, y)
                    self._ocr_timer.stop()
                else:
                    self._canvas.add(x, y)
                self._prev_draw = (x, y)
            else:
                self._canvas.end()
                self._prev_draw = None
                if self._canvas.has_strokes():
                    self._ocr_timer.start()
        if self._accel:
            self._status.setText(status)
        self._clicks.setText(f"CLICKS: {clicks}")
        self._screen_map.set_cursor(nx, ny)

    # --------------------------------------------------------- whiteboard

    def _auto_convert(self) -> None:
        """Debounced auto-OCR: after a pause in drawing, turn the handwriting
        into text below the canvas (Marker Felt = whiteboard font)."""
        if self._mode == 2 and self._canvas.has_strokes():
            self._convert_canvas()

    def _set_marker_color(self, hexv: str) -> None:
        self._marker_color = hexv
        for h, b in self._color_swatches.items():
            b.setStyleSheet(
                f"QPushButton {{ background: {h}; border: 2px solid"
                f" {'#00f0ff' if h == hexv else '#333'}; border-radius: 4px; }}"
            )
        self._canvas.set_brush(QColor(hexv), self._size_slider.value())

    def _convert_canvas(self) -> None:
        if not self._canvas.has_strokes():
            self._status.setText("NOTHING TO CONVERT — DRAW FIRST")
            return
        self._status.setText("READING HANDWRITING…")
        tmp = os.path.expanduser("~/.jarvis/whiteboard_ocr.png")
        try:
            self._canvas.render_image(scale=2.0, ink="#000000").save(tmp)
            text = _ocr_image(tmp)
        except Exception as exc:
            self._status.setText(f"OCR ERROR: {exc}")
            return
        if text:
            self._canvas_text.setText(f"“{text}”")
            self._canvas_text.show()
            self._status.setText(f"READ: “{text}”")
            _debug(f"whiteboard OCR: {text!r}")
        else:
            self._status.setText("COULDN'T READ IT — WRITE BIGGER, CLEARER LETTERS")

    def _save_whiteboard(self) -> None:
        if not self._canvas.has_strokes():
            self._status.setText("NOTHING TO SAVE — DRAW FIRST")
            return
        try:
            from jarvis.tools.obsidian_tool import _pick_vault
        except Exception as exc:
            self._status.setText(f"OBSIDIAN ERROR: {exc}")
            return
        pick = _pick_vault()
        if not pick.get("ok"):
            self._status.setText("OBSIDIAN: " + str(pick.get("error", "no vault")))
            return
        ts = time.strftime("%Y-%m-%d %H.%M.%S")
        base = pick["path"] / "JARVIS" / "Whiteboard"
        imgs = base / "images"
        try:
            imgs.mkdir(parents=True, exist_ok=True)
            png = imgs / f"{ts}.png"
            self._canvas.render_image(scale=2.0).save(str(png))
            text = self._canvas_text.text().strip("“” ") if self._canvas_text.isVisible() else ""
            content = f"# Whiteboard — {ts}\n\n"
            if text:
                content += f"> {text}\n\n"
            content += f"![[{png.name}]]\n"
            note = base / f"{ts}.md"
            note.write_text(content, encoding="utf-8")
        except Exception as exc:
            self._status.setText(f"SAVE FAILED: {exc}")
            _debug(f"whiteboard save error: {exc}")
            return
        _debug(f"whiteboard saved: {note}")
        self._status.setText(f"💾 SAVED → {pick['name']} / JARVIS / Whiteboard / {ts}.md")

    def _on_permission(self, granted: bool) -> None:
        _debug(f"camera permission result: granted={granted}")
        if not granted:
            self._status.setText("⚠ CAMERA DENIED")
            self._video.show_message(
                "Camera permission denied. Enable it in System Settings → "
                "Privacy & Security → Camera → JARVIS, then reopen gesture control."
            )
            return
        self._status.setText("STARTING…")
        _debug("permission granted, starting capture thread")
        self._thread.start()

    def _on_failed(self, msg: str) -> None:
        _debug(f"camera error: {msg}")
        self._status.setText("⚠ CAMERA ERROR")
        self._video.show_message(msg)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._thread.stop()
        self._thread.wait(2000)
        super().closeEvent(event)


def run() -> int:
    _debug("gesture window process starting")
    app = QApplication([])
    app.setApplicationName("JARVIS Gesture Control")
    win = GestureWindow()
    win.show()
    win.raise_()
    win.activateWindow()
    _debug("gesture window shown")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
