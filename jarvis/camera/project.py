"""
jarvis/camera/project.py
MODE 3 · PROJECT — the Iron Man workshop canvas (v2).

A clean BLACK & WHITE fullscreen canvas: your hand draws white strokes,
JARVIS can drop typed notes and pinned pictures onto it, and a small JARVIS
panel floats beside it — chat in text + his voice, screenshot/camera pins,
remove-last, suggestions, and save to Obsidian.

Coordinates on the canvas are normalized (0..1) so it can be resized freely,
including going fullscreen.
"""
from __future__ import annotations

import os
import threading
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from jarvis.hud.theme import CYAN, WHITE_DIM, mono

_WHITE = QColor("#ffffff")
_WHITE_DIM = QColor(255, 255, 255, 90)


class ProjectCanvas(QWidget):
    """Black canvas, white strokes + typed notes + pinned images."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(640, 420)
        self._strokes: list = []          # [color, width, pts(normalized)]
        self._current: list | None = None
        self._items: list = []            # text notes / images
        self._color = QColor("#ffffff")
        self._width = 8.0
        self._slot = 0
        self._cursor: tuple | None = None   # fingertip aim reticle (normalized)

    # ------------------------------------------------------------------ API

    def set_brush(self, color: QColor, width: float) -> None:
        self._color = QColor(color)
        self._width = width

    def begin(self, x: float, y: float) -> None:
        self._current = [QColor(self._color), self._width, [(x, y)]]
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
        self._items.clear()
        self._slot = 0
        self.update()

    def has_strokes(self) -> bool:
        return any(len(s[2]) >= 2 for s in self._strokes)

    def has_content(self) -> bool:
        return self.has_strokes() or bool(self._items)

    # ------------------------------------------------------- JARVIS actions

    def _next_slot(self) -> tuple:
        """Return the next free spot (normalized) for a note/image, laid out
        in a tidy grid so JARVIS never piles things on top of each other."""
        cols = 3
        col = self._slot % cols
        row = (self._slot // cols) % 4
        self._slot += 1
        return (0.06 + col * 0.30, 0.10 + row * 0.16)

    def add_text_item(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        x, y = self._next_slot()
        self._items.append({"type": "text", "x": x, "y": y, "text": text})
        self.update()

    def add_image_item(self, pixmap: QPixmap, caption: str = "") -> None:
        if pixmap.isNull():
            return
        x, y = self._next_slot()
        self._items.append({"type": "image", "x": x, "y": y, "pixmap": pixmap,
                            "caption": caption})
        self.update()

    def set_cursor(self, nx: float, ny: float) -> None:
        """Show a small white reticle where the fingertip is aiming (normalized
        coords; pass -1,-1 to hide). Lets you aim before you pinch."""
        self._cursor = (nx, ny) if nx >= 0 else None
        self.update()

    def remove_last_item(self) -> bool:
        """Remove the most recently added element (note, image or stroke).
        Returns True if something was removed."""
        if self._items:
            self._items.pop()
            self._slot = max(0, self._slot - 1)
            self.update()
            return True
        if self._strokes:
            self._strokes.pop()
            self.update()
            return True
        return False

    def text_contents(self) -> list:
        return [it["text"] for it in self._items if it["type"] == "text"]

    # ------------------------------------------------------------- painting

    def _paint_strokes(self, p: QPainter) -> None:
        w, h = max(1, self.width()), max(1, self.height())
        for color, width, pts in self._strokes:
            if len(pts) < 2:
                continue
            path = QPainterPath()
            path.moveTo(pts[0][0] * w, pts[0][1] * h)
            for x, y in pts[1:]:
                path.lineTo(x * w, y * h)
            for pw, mult in ((width * 1.6, 0.28), (width, 1.0)):
                c = QColor(color)
                c.setAlpha(int(255 * mult))
                p.setPen(QPen(c, pw, Qt.PenStyle.SolidLine,
                              Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                p.drawPath(path)

    def _paint_cursor(self, p: QPainter) -> None:
        if self._cursor is None:
            return
        w, h = max(1, self.width()), max(1, self.height())
        cx, cy = self._cursor[0] * w, self._cursor[1] * h
        p.setPen(QPen(QColor(255, 255, 255, 150), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), 7, 7)
        p.drawLine(QPointF(cx - 12, cy), QPointF(cx - 5, cy))
        p.drawLine(QPointF(cx + 5, cy), QPointF(cx + 12, cy))
        p.drawLine(QPointF(cx, cy - 12), QPointF(cx, cy - 5))
        p.drawLine(QPointF(cx, cy + 5), QPointF(cx, cy + 12))

    def _paint_items(self, p: QPainter) -> None:
        w, h = max(1, self.width()), max(1, self.height())
        font = QFont("Marker Felt", 22)
        font.setBold(True)
        for it in self._items:
            x, y = it["x"] * w, it["y"] * h
            if it["type"] == "text":
                max_w = int(w * 0.26)
                fm = QFontMetrics(font)
                words = it["text"].split()
                lines, cur = [], ""
                for word in words:
                    trial = (cur + " " + word).strip()
                    if fm.horizontalAdvance(trial) <= max_w or not cur:
                        cur = trial
                    else:
                        lines.append(cur)
                        cur = word
                if cur:
                    lines.append(cur)
                p.setFont(font)
                line_h = fm.height()
                for i, line in enumerate(lines):
                    p.setPen(_WHITE)
                    p.drawText(QRectF(x, y + i * line_h, max_w, line_h),
                               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, line)
            else:  # image
                img = it["pixmap"]
                iw = int(w * 0.30)
                ih = int(img.height() * iw / max(1, img.width()))
                p.drawPixmap(QRectF(x, y, iw, ih), img)
                if it.get("caption"):
                    p.setPen(_WHITE_DIM)
                    p.setFont(mono(9))
                    p.drawText(QRectF(x, y + ih + 2, iw, 16), Qt.AlignmentFlag.AlignLeft,
                               it["caption"])

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.GlobalColor.black)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_strokes(p)
        self._paint_items(p)
        self._paint_cursor(p)
        p.end()

    def render_image(self, scale: float = 2.0, ink: str | None = None) -> QImage:
        """Render everything to a high-res image. Pass `ink` (e.g. '#ffffff')
        to force stroke color for OCR on black."""
        img = QImage(int(self.width() * scale), int(self.height() * scale),
                     QImage.Format.Format_RGB32)
        img.fill(Qt.GlobalColor.black)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = max(1, self.width()), max(1, self.height())
        for color, width, pts in self._strokes:
            if len(pts) < 2:
                continue
            path = QPainterPath()
            path.moveTo(pts[0][0] * w * scale, pts[0][1] * h * scale)
            for x, y in pts[1:]:
                path.lineTo(x * w * scale, y * h * scale)
            c = QColor(ink) if ink else color
            p.setPen(QPen(c, max(width * scale, 2.0), Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPath(path)
        p.end()
        return img


class SpotifyChip(QWidget):
    """Tiny now-playing chip. Polls the Spotify tool every few seconds."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._label = QLabel("♪ —")
        self._label.setFont(mono(8))
        self._label.setStyleSheet(
            "color: #9fd8e0; background: transparent; border: none;"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 0, 2, 0)
        lay.addWidget(self._label)

        self._timer = QTimer(self)
        self._timer.setInterval(15_000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def refresh(self) -> None:
        try:
            from jarvis.tools.spotify_tool import spotify_status
            st = spotify_status()
            track = (st or {}).get("track") or ""
            artist = (st or {}).get("artist") or ""
            playing = bool((st or {}).get("playing"))
            if track:
                icon = "▶" if playing else "⏸"
                label = f"{icon} {track}"
                if artist:
                    label += f" — {artist}"
                self._label.setText(label[:48])
                self._label.setToolTip(f"Now playing: {track} by {artist}")
            else:
                self._label.setText("♪ —")
                self._label.setToolTip("Spotify isn't playing anything right now")
        except Exception:
            self._label.setText("♪ —")
            self._label.setToolTip("Spotify unavailable")


class ProjectRail(QWidget):
    """The small JARVIS window: chat (text + voice), picture pins, remove,
    suggest, save. Stays compact so the canvas is the star."""

    submitted = pyqtSignal(str)
    voice_requested = pyqtSignal()
    screen_requested = pyqtSignal()
    snap_requested = pyqtSignal()
    remove_requested = pyqtSignal()
    suggest_requested = pyqtSignal()
    save_requested = pyqtSignal()
    new_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(250)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        head = QLabel("J.A.R.V.I.S.")
        head.setFont(mono(11, bold=True))
        head.setStyleSheet(f"color: {CYAN.name()}; background: transparent;")
        lay.addWidget(head)
        lay.addWidget(SpotifyChip())

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet(
            "QTextEdit { background: rgba(8, 10, 12, 0.92); color: #cfeef5;"
            " border: 1px solid rgba(0, 240, 255, 0.25); border-radius: 6px;"
            " padding: 6px; font-family: 'SF Mono', Menlo, monospace; font-size: 10px; }"
        )
        self._log.setMinimumHeight(150)
        lay.addWidget(self._log, stretch=1)

        row = QHBoxLayout()
        row.setSpacing(4)
        mic = QPushButton("🎤")
        mic.setFont(mono(9))
        mic.setFixedWidth(30)
        mic.setCursor(Qt.CursorShape.PointingHandCursor)
        mic.setToolTip("Speak to JARVIS — one command")
        mic.setStyleSheet(
            "QPushButton { background: #0a1a20; color: #00f0ff;"
            " border: 1px solid rgba(0, 240, 255, 0.6); border-radius: 5px; padding: 4px 2px; }"
            "QPushButton:hover { background: #0e2a34; }"
        )
        mic.clicked.connect(lambda: self.voice_requested.emit())
        row.addWidget(mic)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Talk to JARVIS…")
        self._input.setStyleSheet(
            "QLineEdit { background: rgba(8, 10, 12, 0.92); color: #eaffff;"
            " border: 1px solid rgba(0, 240, 255, 0.4); border-radius: 5px; padding: 5px 7px;"
            " font-family: 'SF Mono', Menlo, monospace; font-size: 10px; }"
        )
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input, stretch=1)

        send = QPushButton("SEND")
        send.setFont(mono(8, bold=True))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(
            "QPushButton { background: #0a1a20; color: #00f0ff;"
            " border: 1px solid rgba(0, 240, 255, 0.6); border-radius: 5px; padding: 5px 9px; }"
            "QPushButton:hover { background: #0e2a34; }"
        )
        send.clicked.connect(self._send)
        row.addWidget(send)
        lay.addLayout(row)

        # Action buttons: two compact rows.
        grid = QGridLayout()
        grid.setSpacing(4)
        actions = (
            ("📷 SCREEN", self.screen_requested, "Pin a screenshot of your screen to the canvas"),
            ("🎥 SNAP", self.snap_requested, "Pin the current camera frame to the canvas"),
            ("🗑 REMOVE", self.remove_requested, "Remove the last element (note, image or stroke)"),
            ("💡 SUGGEST", self.suggest_requested, "JARVIS suggests what to add or do next"),
            ("💾 SAVE", self.save_requested, "Save this project to Obsidian"),
            ("✨ NEW", self.new_requested, "Start a fresh project canvas"),
        )
        for i, (label, sig, tip) in enumerate(actions):
            b = QPushButton(label)
            b.setFont(mono(8, bold=True))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(tip)
            b.setStyleSheet(
                "QPushButton { background: #0a0a0e; color: #9fd8e0;"
                " border: 1px solid rgba(0, 240, 255, 0.4); border-radius: 5px; padding: 5px 4px; }"
                "QPushButton:hover { background: #0e1a20; }"
            )
            b.clicked.connect(lambda _c, s=sig: s.emit())
            grid.addWidget(b, i // 3, i % 3)
        lay.addLayout(grid)

        self._busy = False

    def _send(self) -> None:
        text = self._input.text().strip()
        if not text or self._busy:
            return
        self._input.clear()
        self._busy = True
        self.append_user(text)
        self.submitted.emit(text)

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._input.setEnabled(not busy)

    def append_user(self, text: str) -> None:
        self._log.append(
            f'<span style="color:#ffffff;">YOU — {self._ts()}</span><br>'
            f'<span style="color:#9fd8e0;">{text}</span>'
        )
        self._scroll()

    def append_jarvis(self, text: str) -> None:
        self._log.append(
            f'<span style="color:#00f0ff;">J.A.R.V.I.S. — {self._ts()}</span><br>'
            f'<span style="color:#cfeef5;">{text}</span>'
        )
        self._scroll()

    @staticmethod
    def _ts() -> str:
        return time.strftime("%H:%M")

    def _scroll(self) -> None:
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())
