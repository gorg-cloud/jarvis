"""
jarvis/hud/widgets.py
Custom Stark-HUD widgets: GaugeCircle, MiniGraph, MarkdownStream, LogPanel, StatusBar.
"""
import re
from typing import List

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QPainterPath, QRadialGradient, QLinearGradient
)
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton

from .theme import (
    BG, BG_PANEL, BG_PANEL_BORDER, CYAN, CYAN_DIM, CYAN_ALPHA,
    WHITE, WHITE_DIM, mono,
)


class Panel(QFrame):
    """Base panel with 1px cyan border."""
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("hudPanel")
        self.setStyleSheet(f"""
            #hudPanel {{
                background: {BG_PANEL.name()};
                border: 1px solid {BG_PANEL_BORDER.name()};
                border-radius: 4px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        if title:
            lbl = QLabel(title.upper())
            lbl.setFont(mono(9, bold=True))
            lbl.setStyleSheet(f"color: {CYAN.name()}; border: none; background: transparent;")
            lbl.setFixedHeight(18)
            layout.addWidget(lbl)
        self._content_layout = layout

    def add(self, widget: QWidget):
        self._content_layout.addWidget(widget)


class GaugeCircle(QWidget):
    """Animated arc gauge (CPU/RAM/battery)."""
    def __init__(self, label: str, max_val: float = 100, unit: str = "%", parent=None):
        super().__init__(parent)
        self.label = label
        self.max_val = max_val
        self.unit = unit
        self._value = 0.0
        self._target = 0.0
        self.setFixedSize(160, 160)

    def set_value(self, v: float):
        self._target = min(v, self.max_val)

    def paintEvent(self, event):
        # Smooth animation
        diff = self._target - self._value
        self._value += diff * 0.15
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2
        radius = 58

        # Background track
        pen_bg = QPen(CYAN_ALPHA, 6)
        pen_bg.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen_bg)
        p.drawArc(cx - radius, cy - radius, radius * 2, radius * 2, 225 * 16, -270 * 16)

        # Value arc
        angle = (self._value / self.max_val) * 270
        pen_val = QPen(CYAN, 3)
        pen_val.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen_val)
        if angle > 0.1:
            p.drawArc(cx - radius, cy - radius, radius * 2, radius * 2,
                       225 * 16, -int(angle * 16))

        # Center text
        p.setPen(WHITE)
        p.setFont(mono(22, bold=True))
        text = f"{self._value:.0f}"
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, text)
        # Unit
        p.setFont(mono(9))
        p.setPen(CYAN_DIM)
        p.drawText(QRectF(cx - radius, cy + 20, radius * 2, 20),
                   Qt.AlignmentFlag.AlignCenter, self.unit)
        # Label below
        p.setFont(mono(9, bold=True))
        p.setPen(CYAN)
        p.drawText(QRectF(0, h - 22, w, 18), Qt.AlignmentFlag.AlignCenter, self.label.upper())


class MiniGraph(QWidget):
    """Rolling line graph for memory/network."""
    def __init__(self, label: str, max_points: int = 60, parent=None):
        super().__init__(parent)
        self.label = label
        self.max_points = max_points
        self._data: List[float] = [0.0] * max_points
        self.setFixedHeight(100)
        self.setMinimumWidth(200)

    def push(self, v: float):
        self._data.append(v)
        if len(self._data) > self.max_points:
            self._data = self._data[-self.max_points:]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        margin = 2
        gw = w - margin * 2
        gh = h - margin * 2 - 16

        # Grid lines
        p.setPen(QPen(QColor(255, 255, 255, 15), 1, Qt.PenStyle.DotLine))
        for frac in (0.25, 0.5, 0.75):
            y = margin + int(gh * (1 - frac))
            p.drawLine(margin, y, w - margin, y)

        # Data line
        n = len(self._data)
        if n < 2:
            p.end()
            return
        max_val = max(max(self._data), 1)

        # Fill gradient
        path_fill = QPainterPath()
        path_fill.moveTo(margin, margin + gh)
        for i, v in enumerate(self._data):
            x = margin + int(i * gw / (n - 1))
            y = margin + int(gh * (1 - v / max_val))
            path_fill.lineTo(x, y)
        path_fill.lineTo(margin + gw, margin + gh)
        path_fill.closeSubpath()
        grad = QLinearGradient(0, margin, 0, margin + gh)
        grad.setColorAt(0, QColor(0, 240, 255, 50))
        grad.setColorAt(1, QColor(0, 240, 255, 0))
        p.fillPath(path_fill, grad)

        # Stroke line
        pen = QPen(CYAN, 1.5)
        p.setPen(pen)
        path_line = QPainterPath()
        for i, v in enumerate(self._data):
            x = margin + int(i * gw / (n - 1))
            y = margin + int(gh * (1 - v / max_val))
            if i == 0:
                path_line.moveTo(x, y)
            else:
                path_line.lineTo(x, y)
        p.drawPath(path_line)

        # Label
        p.setPen(CYAN_DIM)
        p.setFont(mono(8))
        p.drawText(margin, h - 2, self.label.upper())

        # Max value
        p.setPen(WHITE_DIM)
        p.drawText(w - margin - 40, h - 2, f"{max_val:.0f}")
        p.end()


class MarkdownStream(QWidget):
    """Live-streaming markdown renderer."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._lines: List[str] = []
        self._max_lines = 300
        self._scroll_y = 0
        self.setStyleSheet(f"background: {BG.name()};")

    def append(self, text: str):
        for line in text.split("\n"):
            self._lines.append(line)
        if len(self._lines) > self._max_lines:
            self._lines = self._lines[-self._max_lines:]
        self._scroll_y = max(0, len(self._lines) - self._visible_lines())
        self.update()

    def _visible_lines(self) -> int:
        return max(1, (self.height() - 20) // 16)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, BG)
        y = 8 - (self._scroll_y * 16)
        line_h = 16
        for line in self._lines:
            if y > h:
                break
            if y + line_h < 0:
                y += line_h
                continue
            self._paint_line(p, line, y, w)
            y += line_h
        p.end()

    def _paint_line(self, p: QPainter, line: str, y: int, w: int):
        x = 12
        stripped = line.strip()
        # Headers
        if stripped.startswith("###"):
            p.setFont(mono(11, bold=True))
            p.setPen(CYAN)
            p.drawText(x, y + 13, stripped[3:].strip())
            p.setPen(QPen(CYAN_ALPHA, 1))
            p.drawLine(x, y + 15, x + 200, y + 15)
        elif stripped.startswith("##"):
            p.setFont(mono(12, bold=True))
            p.setPen(CYAN)
            p.drawText(x, y + 13, stripped[2:].strip())
            p.setPen(QPen(CYAN_ALPHA, 1))
            p.drawLine(x, y + 16, x + 250, y + 16)
        elif stripped.startswith("# "):
            p.setFont(mono(14, bold=True))
            p.setPen(WHITE)
            p.drawText(x, y + 14, stripped[1:].strip())
            p.setPen(QPen(CYAN, 1))
            p.drawLine(x, y + 17, x + 300, y + 17)
        # Bullet points
        elif stripped.startswith("* ") or stripped.startswith("- "):
            p.setFont(mono(11))
            p.setPen(CYAN_DIM)
            p.drawText(x, y + 12, "▸")
            p.setPen(WHITE)
            p.drawText(x + 16, y + 12, stripped[2:])
        # Code blocks
        elif stripped.startswith("```"):
            p.setFont(mono(10))
            p.setPen(CYAN_ALPHA)
            p.drawText(x, y + 12, "▎" + stripped)
        elif stripped.startswith("  ") or stripped.startswith("\t"):
            p.setFont(mono(10))
            p.setPen(CYAN_DIM)
            p.drawText(x, y + 12, stripped)
        # Timestamps
        elif re.match(r"^\[\d{2}:\d{2}:\d{2}\]", stripped):
            p.setFont(mono(10))
            p.setPen(CYAN_DIM)
            bracket_end = stripped.index("]") + 1
            p.drawText(x, y + 12, stripped[:bracket_end])
            p.setPen(WHITE_DIM)
            p.drawText(x + 70, y + 12, stripped[bracket_end:])
        # Error lines
        elif "❌" in stripped or "error" in stripped.lower() or "failed" in stripped.lower():
            p.setFont(mono(10))
            p.setPen(QColor("#ff4444"))
            p.drawText(x, y + 12, stripped)
        # Success
        elif "✅" in stripped:
            p.setFont(mono(10))
            p.setPen(CYAN)
            p.drawText(x, y + 12, stripped)
        # Normal
        else:
            p.setFont(mono(11))
            p.setPen(WHITE)
            p.drawText(x, y + 12, stripped)


class NowPlayingWidget(QWidget):
    """Shows current Spotify track with album art (fetched from iTunes API)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._track = ""
        self._artist = ""
        self._album = ""
        self._state = "stopped"
        self._art_pixmap = None
        self._art_key = ""  # track key we already fetched art for
        self._fetching = False
        self.setFixedHeight(110)
        self.setMinimumWidth(220)

    def update_track(self, data: dict):
        old_key = self._art_key
        self._state = data.get("state", "stopped")
        self._track = data.get("track", "")
        self._artist = data.get("artist", "")
        self._album = data.get("album", "")
        new_key = f"{self._artist}|{self._album}"
        if new_key != old_key and self._track:
            # Trigger album art fetch
            self._art_key = new_key
            self._fetching = False
            import threading
            threading.Thread(target=self._fetch_album_art, args=(self._artist, self._album), daemon=True).start()
        self.update()

    def _fetch_album_art(self, artist: str, album: str):
        """Fetch album art from iTunes Search API (public, no auth)."""
        if self._fetching or not (artist or album):
            return
        self._fetching = True
        import urllib.request
        import urllib.parse
        import json
        query = " ".join(filter(None, [artist, album])).strip()
        if not query:
            return
        url = "https://itunes.apple.com/search?media=music&entity=album&limit=1&term=" + urllib.parse.quote(query)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-HUD/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            results = data.get("results", [])
            if not results:
                self._fetching = False
                return
            art_url = results[0].get("artworkUrl100", "")
            if not art_url:
                self._fetching = False
                return
            # Upgrade to higher resolution
            art_url = art_url.replace("100x100bb", "300x300bb")
            req2 = urllib.request.Request(art_url, headers={"User-Agent": "JARVIS-HUD/1.0"})
            with urllib.request.urlopen(req2, timeout=5) as resp:
                img_data = resp.read()
            from PyQt6.QtGui import QPixmap
            from PyQt6.QtCore import QByteArray
            pix = QPixmap()
            pix.loadFromData(img_data)
            if not pix.isNull():
                self._art_pixmap = pix
                self.update()
        except Exception:
            pass
        finally:
            self._fetching = False

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        # Label
        p.setFont(mono(9, bold=True))
        p.setPen(CYAN_DIM)
        p.drawText(12, 14, "NOW PLAYING" if self._state == "playing" else "SPOTIFY")
        # Album art box (left)
        art_size = 70
        art_x, art_y = 12, 22
        if self._art_pixmap and not self._art_pixmap.isNull():
            # Draw rounded art
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(CYAN_DIM, 1))
            p.drawRoundedRect(QRectF(art_x, art_y, art_size, art_size), 4, 4)
            scaled = self._art_pixmap.scaled(art_size, art_size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap(art_x + 1, art_y + 1, scaled, 0, 0, art_size - 2, art_size - 2)
        else:
            # Placeholder with play/pause icon
            p.setPen(QPen(CYAN_ALPHA, 1))
            p.setBrush(QColor(0, 240, 255, 12))
            p.drawRoundedRect(QRectF(art_x, art_y, art_size, art_size), 4, 4)
            icon = "▶" if self._state == "playing" else "⏸" if self._state == "paused" else "⏹"
            p.setFont(mono(20))
            p.setPen(CYAN_DIM)
            p.drawText(QRectF(art_x, art_y, art_size, art_size), Qt.AlignmentFlag.AlignCenter, icon)
        # Track + artist (right of art)
        text_x = art_x + art_size + 12
        text_w = w - text_x - 12
        p.setFont(mono(11, bold=True))
        p.setPen(WHITE)
        text = self._track if self._track else "No track"
        fm = p.fontMetrics()
        while fm.horizontalAdvance(text) > text_w and len(text) > 4:
            text = text[:-4] + "…"
        p.drawText(text_x, 38, text)
        # Artist + album
        p.setFont(mono(9))
        p.setPen(WHITE_DIM)
        info = self._artist
        if self._album:
            info += f" - {self._album}"
        while fm.horizontalAdvance(info) > text_w and len(info) > 4:
            info = info[:-4] + "…"
        p.drawText(text_x, 56, info)
        # Progress bar (static since Spotify applescript doesn't expose position easily)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 240, 255, 30))
        p.drawRect(text_x, 78, text_w, 2)
        p.setBrush(CYAN)
        p.drawRect(text_x, 78, max(8, text_w * 0.3), 2)
        p.end()


class CalendarWidget(QWidget):
    """Shows upcoming calendar events for the week."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._events: list = []
        self.setFixedHeight(160)
        self.setMinimumWidth(200)

    def set_events(self, events: list):
        self._events = events[:6]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        # Label
        p.setFont(mono(9, bold=True))
        p.setPen(CYAN_DIM)
        p.drawText(12, 14, "THIS WEEK")
        if not self._events:
            p.setFont(mono(10))
            p.setPen(WHITE_DIM)
            p.drawText(12, 36, "No events")
            p.end()
            return
        y = 32
        for ev in self._events:
            if y > h - 10:
                p.setFont(mono(8))
                p.setPen(WHITE_DIM)
                p.drawText(12, y, f"+{len(self._events) - self._events.index(ev) - 1} more…")
                break
            # Dot + summary
            p.setFont(mono(9, bold=True))
            p.setPen(CYAN)
            p.drawText(12, y, "●")
            summary = ev.get("summary", "")
            fm = p.fontMetrics()
            while fm.horizontalAdvance(summary) > w - 80 and len(summary) > 4:
                summary = summary[:-4] + "…"
            p.setPen(WHITE)
            p.drawText(26, y, summary)
            # Time + location
            y += 15
            start = ev.get("start", "")
            # Shorten date: take "Friday, July 25, 2026 at 10:00:00 AM" → "Fri 10:00 AM"
            short = start
            if " at " in start:
                parts = start.split(" at ")
                day = parts[0].split(",")[0][:3]  # "Friday" → "Fri"
                time_part = parts[1]
                if ":" in time_part:
                    time_part = time_part[:7]  # "10:00:00 AM" → "10:00 A"
                    time_part = time_part.rstrip("0").rstrip(":").rstrip(" ").rstrip("A").rstrip("M") + (" AM" if "AM" in parts[1] else " PM" if "PM" in parts[1] else "")
                short = f"{day} {time_part}"
            loc = ev.get("location", "")
            line2 = short
            if loc:
                line2 += f" · {loc}"
            p.setFont(mono(8))
            p.setPen(WHITE_DIM)
            p.drawText(26, y, line2[:50])
            y += 16
        p.end()


class KillButton(QPushButton):
    """Minimal HUD exit button."""
    def __init__(self, parent=None):
        super().__init__("⏻", parent)
        self.setFixedSize(36, 36)
        self.setToolTip("Close JARVIS HUD")
        self.setStyleSheet(f"""
            QPushButton {{
                color: {CYAN.name()};
                background: {BG_PANEL.name()};
                border: 1px solid {BG_PANEL_BORDER.name()};
                border-radius: 18px;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {CYAN.name()};
                color: {BG.name()};
            }}
        """)
