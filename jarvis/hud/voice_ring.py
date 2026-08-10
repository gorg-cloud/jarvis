"""
jarvis/hud/voice_ring.py
Central glowing reactive ring. Pulses when JARVIS or user speaks.
Listens to mic level via PyAudio in background thread, scales glow + vibration.
"""
from __future__ import annotations

import math
import threading
import time
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QRadialGradient, QPainterPath, QFont
)
from PyQt6.QtWidgets import QWidget

from .theme import CYAN, CYAN_DIM, WHITE, mono


class VoiceRing(QWidget):
    """
    Glowing ring. Reacts to:
      - ambient mic level (0.0-1.0) → ring expands + glow intensifies
      - "active" state (JARVIS speaking or listening) → steady pulse + vibration
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = 0.0        # smoothed mic level
        self._target_level = 0.0
        self._active = False     # JARVIS speaking/listening
        self._active_boost = 0.0
        self._phase = 0.0        # animation phase
        self._mic_level = 0.0    # raw mic level from thread
        self._mic_thread: Optional[threading.Thread] = None
        self._mic_running = False
        self._jts_label = "JARVIS"
        self.setFixedSize(220, 220)

        # 60fps animation timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)  # ~60fps

    # ---- public API ----
    def set_active(self, on: bool):
        """Set whether JARVIS is actively listening/speaking."""
        self._active = on

    def set_label(self, text: str):
        self._jts_label = text

    def start_mic_listener(self):
        """Start background mic-level monitor. Non-fatal if mic unavailable."""
        if self._mic_running:
            return
        self._mic_running = True
        self._mic_thread = threading.Thread(target=self._mic_loop, daemon=True)
        self._mic_thread.start()

    def stop_mic_listener(self):
        self._mic_running = False

    # ---- mic monitor thread ----
    def _mic_loop(self):
        try:
            import pyaudio
            import struct
            p = pyaudio.PyAudio()
            stream = p.open(
                format=pyaudio.paInt16, channels=1, rate=8000,
                input=True, frames_per_buffer=256,
            )
            while self._mic_running:
                try:
                    data = stream.read(256, exception_on_overflow=False)
                    samples = struct.unpack(f"<{len(data)//2}h", data)
                    peak = max(abs(s) for s in samples) / 32768.0 if samples else 0
                    # smooth + scale
                    self._mic_level = max(self._mic_level * 0.6, peak)
                except Exception:
                    time.sleep(0.05)
            stream.stop_stream()
            stream.close()
            p.terminate()
        except Exception as e:
            # Mic unavailable. Ring still works via active state.
            pass

    # ---- animation tick ----
    def _tick(self):
        self._phase += 0.05
        # Smooth level
        self._target_level = self._mic_level
        if self._active:
            # When active, add breathing pulse even in silence
            self._active_boost = 0.25 + 0.15 * math.sin(self._phase * 1.5)
            self._target_level = max(self._target_level, self._active_boost)
        else:
            self._active_boost *= 0.9
        self._level += (self._target_level - self._level) * 0.2
        self.update()

    # ---- paint ----
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2

        # Vibration offset when active + level high
        vibrate_x = 0
        vibrate_y = 0
        if self._active and self._level > 0.3:
            vibrate_x = math.sin(self._phase * 8) * self._level * 2.5
            vibrate_y = math.cos(self._phase * 7) * self._level * 2.5

        # Base ring radius with reactive expansion
        base_r = 70
        expand = self._level * 18
        # When active, add subtle breathing
        if self._active:
            expand += math.sin(self._phase * 1.5) * 3
        r_outer = base_r + expand

        # === Outer glow halo (multi-layer) ===
        for i, (alpha, radius_mult) in enumerate([
            (18, 1.6), (28, 1.4), (50, 1.2),
        ]):
            halo_r = r_outer * radius_mult
            grad = QRadialGradient(cx + vibrate_x, cy + vibrate_y, halo_r)
            intensity = alpha * (0.5 + self._level)
            grad.setColorAt(0, QColor(0, 240, 255, int(intensity)))
            grad.setColorAt(1, QColor(0, 240, 255, 0))
            p.setBrush(grad)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(
                cx + vibrate_x - halo_r, cy + vibrate_y - halo_r,
                halo_r * 2, halo_r * 2
            ))

        # === Main ring stroke (bright) ===
        ring_pen = QPen(CYAN, 2.5)
        ring_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(ring_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(
            cx + vibrate_x - r_outer, cy + vibrate_y - r_outer,
            r_outer * 2, r_outer * 2
        ))

        # === Inner ring (thin, counter-rotating ticks) ===
        inner_r = r_outer - 14
        if inner_r > 10:
            p.setPen(QPen(CYAN_DIM, 1))
            n_ticks = 24
            active_ticks = int(self._level * n_ticks + 4)
            for i in range(n_ticks):
                angle = (i / n_ticks) * 2 * math.pi + self._phase * (0.3 if self._active else 0.05)
                tick_len = 4 if i < active_ticks else 2
                x1 = cx + vibrate_x + math.cos(angle) * inner_r
                y1 = cy + vibrate_y + math.sin(angle) * inner_r
                x2 = cx + vibrate_x + math.cos(angle) * (inner_r - tick_len)
                y2 = cy + vibrate_y + math.sin(angle) * (inner_r - tick_len)
                p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # === Center core ===
        core_r = max(8, 32 - self._level * 8)
        core_grad = QRadialGradient(cx + vibrate_x, cy + vibrate_y, core_r * 2)
        core_grad.setColorAt(0, QColor(0, 240, 255, int(180 + self._level * 60)))
        core_grad.setColorAt(0.5, QColor(0, 240, 255, 40))
        core_grad.setColorAt(1, QColor(0, 240, 255, 0))
        p.setBrush(core_grad)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(
            cx + vibrate_x - core_r * 2, cy + vibrate_y - core_r * 2,
            core_r * 4, core_r * 4
        ))

        # === Status text ===
        p.setPen(WHITE if self._active else CYAN_DIM)
        p.setFont(mono(11, bold=True))
        status = "LISTENING" if self._active else self._jts_label
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, status)

        p.end()
