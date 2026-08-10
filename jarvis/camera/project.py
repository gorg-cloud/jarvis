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

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from jarvis.hud.theme import CYAN, WHITE_DIM, mono

_WHITE = QColor("#ffffff")
_WHITE_DIM = QColor(255, 255, 255, 90)

# (key, font family, bold) — selectable note fonts.
FONTS = [
    ("MARKER", "Marker Felt", True),
    ("MONO", "SF Mono, Menlo", True),
    ("SANS", "Helvetica Neue", False),
    ("SERIF", "Georgia", False),
]

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
]

INDEX_TIP = 8


class CameraPip(QWidget):
    """Tiny webcam preview with the hand skeleton — so you can see your hand
    while drawing on the fullscreen canvas. Repaints only this small widget,
    never the whole canvas."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(224, 168)
        self.setStyleSheet(
            "background: #000; border: 1px solid rgba(0, 240, 255, 0.35);"
            " border-radius: 6px;"
        )
        self._frame: QImage | None = None
        self._hands: list = []
        self._pinch = False
        self._status = "CAMERA"

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

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#000000"))
        if self._frame is None:
            p.setPen(QColor(0, 240, 255, 150))
            p.setFont(mono(9))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "CAMERA")
            p.end()
            return
        img = self._frame
        scale = min(self.width() / img.width(), self.height() / img.height())
        dw, dh = int(img.width() * scale), int(img.height() * scale)
        dx, dy = (self.width() - dw) // 2, (self.height() - dh) // 2
        p.drawImage(dx, dy, img, 0, 0, img.width(), img.height())

        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for pts in self._hands:
            for a, b in HAND_CONNECTIONS:
                p.setPen(QPen(QColor(0, 240, 255, 130), 1.2))
                p.drawLine(int(dx + pts[a][0] * dw), int(dy + pts[a][1] * dh),
                           int(dx + pts[b][0] * dw), int(dy + pts[b][1] * dh))
            tip = pts[INDEX_TIP]
            cx, cy = int(dx + tip[0] * dw), int(dy + tip[1] * dh)
            col = QColor("#ffffff") if self._pinch else QColor("#37d6ff")
            p.setPen(QPen(col, 2))
            p.setBrush(col)
            p.drawEllipse(QPointF(cx, cy), 4, 4)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 240, 255, 40))
        p.drawRoundedRect(QRectF(4, 4, 150, 20), 4, 4)
        p.setPen(QColor("#00f0ff"))
        p.setFont(mono(8, bold=True))
        p.drawText(10, 17, self._status[:22])
        p.end()


class ProjectCanvas(QWidget):
    """Black canvas, white strokes + typed notes + pinned images.
    Draw with your hand (pinch) or with the mouse (click + drag)."""

    drawing_ended = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(640, 420)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._mouse_drawing = False
        self._strokes: list = []          # [color, width, pts(normalized)]
        self._current: list | None = None
        self._items: list = []            # text notes / images
        self._color = QColor("#ffffff")
        self._width = 8.0
        self._slot = 0
        self._cursor: tuple | None = None   # fingertip aim reticle (screen-normalized)
        self._zoom = 1.0                    # 0.3 .. 4.0
        self._pan = (0.5, 0.5)              # world point at view center

        # Inline text editor (double-click the canvas to add/edit a note).
        self._editor = QTextEdit(self)
        self._editor.setStyleSheet(
            "QTextEdit { background: #0a0a0e; color: #ffffff;"
            " border: 1px solid rgba(0, 240, 255, 0.85); border-radius: 6px;"
            " font-family: 'Marker Felt'; font-size: 18px; padding: 4px; }"
        )
        self._editor.hide()
        self._editor.installEventFilter(self)
        self._editing_item = None           # existing item being edited, or None = new note
        self._editing_anchor = (0.0, 0.0)   # world coords of the editor's top-left
        self._pending_font = "MARKER"

        # Font picker shown above the editor.
        self._font_combo = QComboBox(self)
        for name, _fam, _bold in FONTS:
            self._font_combo.addItem(name)
        self._font_combo.setStyleSheet(
            "QComboBox { background: #0a0a0e; color: #ffffff;"
            " border: 1px solid rgba(0, 240, 255, 0.7); border-radius: 4px;"
            " padding: 2px 6px; font-family: 'SF Mono', Menlo, monospace; font-size: 10px; }"
            "QComboBox QAbstractItemView { background: #0a0a0e; color: #ffffff;"
            " selection-background-color: #0e3a42; }"
        )
        self._font_combo.hide()
        self._font_combo.currentIndexChanged.connect(self._on_font_changed)

        # Drag-to-move a note (mouse or two-finger grab).
        self._drag_item = None
        self._drag_off = (0.0, 0.0)

    # ------------------------------------------------------------------ API

    # ---- view (zoom / pan) ------------------------------------------------

    def set_zoom(self, zoom: float) -> None:
        self._zoom = max(0.3, min(4.0, zoom))
        self.update()

    def zoom_at(self, factor: float, cx: float = 0.5, cy: float = 0.5) -> None:
        """Zoom by `factor`, keeping the world point under (cx, cy) (widget-
        normalized screen coords) fixed on screen."""
        new_zoom = max(0.3, min(4.0, self._zoom * factor))
        if abs(new_zoom - self._zoom) < 1e-6:
            return
        wx = (cx - 0.5) / self._zoom + self._pan[0]
        wy = (cy - 0.5) / self._zoom + self._pan[1]
        self._zoom = new_zoom
        self._pan = (wx - (cx - 0.5) / new_zoom, wy - (cy - 0.5) / new_zoom)
        self._sync_editor_pos()
        self.update()

    def zoom_reset(self) -> None:
        self._zoom = 1.0
        self._pan = (0.5, 0.5)
        self._sync_editor_pos()
        self.update()

    def _edge_pan(self, nx: float, ny: float) -> None:
        """Limitless drawing: while the pen pushes against a view edge, scroll
        the view that way so you can keep drawing past any border. The canvas
        has no walls — the board follows your pen."""
        margin = 0.09
        dx = dy = 0.0
        if nx < margin:
            dx = (nx - margin) * 0.12
        elif nx > 1.0 - margin:
            dx = (nx - (1.0 - margin)) * 0.12
        if ny < margin:
            dy = (ny - margin) * 0.12
        elif ny > 1.0 - margin:
            dy = (ny - (1.0 - margin)) * 0.12
        if abs(dx) < 1e-4 and abs(dy) < 1e-4:
            return
        self._pan = (self._pan[0] + dx / self._zoom,
                     self._pan[1] + dy / self._zoom)
        self._sync_editor_pos()
        self.update()

    def _to_world(self, nx: float, ny: float) -> tuple:
        """Convert widget-normalized screen coords to world coords (inverse
        of the view transform). Unclamped — the canvas is infinite, so strokes
        can live anywhere, not just the home 0..1 area."""
        return ((nx - 0.5) / self._zoom + self._pan[0],
                (ny - 0.5) / self._zoom + self._pan[1])

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15
        pos = event.position()
        self.zoom_at(factor, pos.x() / max(1, self.width()),
                     pos.y() / max(1, self.height()))

    # ---- mouse as a marker ------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self._editor.isVisible():
                # a click on the canvas commits the note being edited
                self._commit_edit()
                return
            sx, sy = event.position().x(), event.position().y()
            item = self._hit_test(sx, sy)
            if item is not None:
                # grab a note to move it (double-click still edits)
                self.start_drag(item, sx, sy)
                return
            self._mouse_drawing = True
            self.begin(sx / max(1, self.width()), sy / max(1, self.height()))

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_item is not None:
            self.update_drag(event.position().x(), event.position().y())
            return
        if self._mouse_drawing:
            self.add(event.position().x() / max(1, self.width()),
                     event.position().y() / max(1, self.height()))

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_item is not None:
            self.end_drag()
            return
        if self._mouse_drawing:
            self._mouse_drawing = False
            self.end()
            if self.has_strokes():
                self.drawing_ended.emit()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        # drop the accidental dot stroke the first click started
        if self._strokes and len(self._strokes[-1][2]) < 3:
            self._strokes.pop()
        sx, sy = event.position().x(), event.position().y()
        self._begin_edit(sx, sy, self._hit_test(sx, sy))

    # ---- inline text editing ----------------------------------------------

    def _screen_to_world(self, sx: float, sy: float) -> tuple:
        return ((sx / max(1, self.width()) - 0.5) / self._zoom + self._pan[0],
                (sy / max(1, self.height()) - 0.5) / self._zoom + self._pan[1])

    def _item_rect_screen(self, it):
        """Screen-space rect (x, y, w, h) for a text item, for hit-testing and
        positioning the editor. None for non-text items."""
        if it["type"] != "text":
            return None
        w, h = max(1, self.width()), max(1, self.height())
        z, px, py = self._zoom, self._pan[0], self._pan[1]
        base = 22.0 * z * (w / 800.0)
        fam, bold = self._font_family(it.get("font", "MARKER"))
        font = QFont(fam, int(max(6, base)))
        font.setBold(bold)
        max_w = int(w * 0.26)
        lines = self._wrap(it["text"], font, max_w)
        x = (it["x"] - px) * z * w + w / 2
        y = (it["y"] - py) * z * h + h / 2
        return (x, y, max_w, len(lines) * QFontMetrics(font).height())

    def _hit_test(self, sx: float, sy: float):
        for it in reversed(self._items):
            r = self._item_rect_screen(it)
            if r and r[0] <= sx <= r[0] + r[2] and r[1] <= sy <= r[1] + r[3]:
                return it
        return None

    # ---- drag to move a note (mouse or two-finger grab) --------------------

    def start_drag(self, item, sx: float, sy: float) -> None:
        r = self._item_rect_screen(item)
        self._drag_item = item
        self._drag_off = (sx - r[0], sy - r[1]) if r else (0.0, 0.0)

    def update_drag(self, sx: float, sy: float) -> None:
        if self._drag_item is None:
            return
        wx, wy = self._screen_to_world(sx - self._drag_off[0], sy - self._drag_off[1])
        self._drag_item["x"] = wx
        self._drag_item["y"] = wy
        self.update()

    def end_drag(self) -> None:
        self._drag_item = None

    # ---- note fonts ---------------------------------------------------------

    @staticmethod
    def _font_family(name: str):
        for key, fam, bold in FONTS:
            if key == name:
                return fam, bold
        return FONTS[0][1], FONTS[0][2]

    def _on_font_changed(self, idx: int) -> None:
        if not (0 <= idx < len(FONTS)):
            return
        name = FONTS[idx][0]
        if self._editing_item is not None:
            self._editing_item["font"] = name
        else:
            self._pending_font = name
        self._sync_editor_pos()
        self.update()

    def begin_edit_at_center(self) -> None:
        """Open a fresh text box at the view center (TEXT button / voice)."""
        self._begin_edit(self.width() / 2, self.height() / 2, None)

    def _begin_edit(self, sx: float, sy: float, item=None) -> None:
        self._editing_item = item
        if item is None:
            self._editing_anchor = self._screen_to_world(sx, sy)
            self._editor.setPlainText("")
            self._editor.setGeometry(int(sx), int(sy),
                                     max(120, int(self.width() * 0.26)),
                                     max(60, int(self.height() * 0.22)))
        else:
            x, y, iw, ih = self._item_rect_screen(item)
            self._editing_anchor = self._screen_to_world(x, y)
            self._editor.setPlainText(item["text"])
            self._editor.setGeometry(int(x), int(y), int(iw), max(60, int(ih) + 10))
        # match the font picker to this note (or the pending font for new notes)
        font = item.get("font") if item is not None else self._pending_font
        idx = next((i for i, f in enumerate(FONTS) if f[0] == font), 0)
        self._font_combo.blockSignals(True)
        self._font_combo.setCurrentIndex(idx)
        self._font_combo.blockSignals(False)
        self._editor.show()
        self._font_combo.show()
        self._sync_editor_pos()
        self._editor.setFocus()
        self._editor.selectAll()

    def _commit_edit(self) -> None:
        if not self._editor.isVisible():
            return
        text = self._editor.toPlainText().strip()
        if self._editing_item is not None:
            if text:
                self._editing_item["text"] = text
            elif self._editing_item in self._items:
                self._items.remove(self._editing_item)
        elif text:
            self._items.append({"type": "text", "x": self._editing_anchor[0],
                                "y": self._editing_anchor[1], "text": text,
                                "font": self._pending_font})
        self._editing_item = None
        self._pending_font = "MARKER"
        self._editor.hide()
        self._font_combo.hide()
        self.update()

    def _cancel_edit(self) -> None:
        self._editing_item = None
        self._editor.hide()
        self._font_combo.hide()
        self.update()

    def _sync_editor_pos(self) -> None:
        """Keep the editor (and its font picker) glued to the item/anchor when
        the view zooms or pans."""
        if not self._editor.isVisible():
            return
        if self._editing_item is not None:
            r = self._item_rect_screen(self._editing_item)
            if r:
                self._editor.setGeometry(int(r[0]), int(r[1]), int(r[2]), max(60, int(r[3]) + 10))
        else:
            w, h = max(1, self.width()), max(1, self.height())
            sx = (self._editing_anchor[0] - self._pan[0]) * self._zoom * w + w / 2
            sy = (self._editing_anchor[1] - self._pan[1]) * self._zoom * h + h / 2
            self._editor.move(int(sx), int(sy))
        self._font_combo.move(self._editor.x(), max(0, self._editor.y() - self._font_combo.height() - 2))
        self._font_combo.resize(96, self._font_combo.height())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_editor_pos()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._editor:
            t = event.type()
            if t == QEvent.Type.KeyPress:
                if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                        self._commit_edit()
                        return True
                elif event.key() == Qt.Key.Key_Escape:
                    self._cancel_edit()
                    return True
            elif t == QEvent.Type.FocusOut:
                from PyQt6.QtWidgets import QApplication
                # Don't commit when focus moves to the font picker.
                if QApplication.focusWidget() is not self._font_combo:
                    self._commit_edit()
        return super().eventFilter(obj, event)

    # ---- strokes -----------------------------------------------------------

    def set_brush(self, color: QColor, width: float) -> None:
        self._color = QColor(color)
        self._width = width

    def begin(self, x: float, y: float) -> None:
        self._edge_pan(x, y)
        wx, wy = self._to_world(x, y)
        self._current = [QColor(self._color), self._width, [(wx, wy)]]
        self._strokes.append(self._current)

    def add(self, x: float, y: float) -> None:
        if self._current is None:
            self.begin(x, y)
        self._edge_pan(x, y)
        wx, wy = self._to_world(x, y)
        self._current[2].append((wx, wy))
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

    def add_plan_item(self, title: str, steps) -> None:
        """Lay out a titled plan as a card: bold title + numbered steps."""
        x, y = self._next_slot()
        self._items.append({"type": "plan", "x": x, "y": y,
                            "title": (title or "PLAN").strip(),
                            "steps": [str(s) for s in (steps or [])]})
        self.update()

    def add_schedule_item(self, title: str, columns, rows) -> None:
        """Lay out an Excel-style schedule table: header row, grid lines,
        alternating row shading, wrapped cells."""
        x, y = self._next_slot()
        self._items.append({"type": "schedule", "x": x, "y": y,
                            "title": (title or "SCHEDULE").strip(),
                            "columns": [str(c) for c in (columns or [])],
                            "rows": [[str(v) for v in r] for r in (rows or [])]})
        self.update()

    def add_flow_item(self, title: str, steps) -> None:
        """Lay out a flowchart: title + boxes connected by arrows, top to bottom."""
        x, y = self._next_slot()
        self._items.append({"type": "flow", "x": x, "y": y,
                            "title": (title or "FLOW").strip(),
                            "steps": [str(s) for s in (steps or [])]})
        self.update()

    def set_cursor(self, nx: float, ny: float) -> None:
        """Show a small white reticle where the fingertip is aiming (normalized
        coords; pass -1,-1 to hide). Lets you aim before you pinch.

        Throttled: a still hand no longer repaints the fullscreen canvas at
        30fps — that sustained paint churn is what crashed the app (~10 min)."""
        cur = (nx, ny) if nx >= 0 else None
        if cur == self._cursor:
            return
        if cur is not None and self._cursor is not None:
            dx = (cur[0] - self._cursor[0]) * self.width()
            dy = (cur[1] - self._cursor[1]) * self.height()
            if dx * dx + dy * dy < 4.0:      # < 2px — store, don't repaint
                self._cursor = cur
                return
        self._cursor = cur
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

    @staticmethod
    def _wrap(text: str, font: QFont, max_px: float) -> list:
        """Word-wrap `text` to fit max_px at the given font; returns lines."""
        fm = QFontMetrics(font)
        words = (text or "").split()
        lines, cur = [], ""
        for word in words:
            trial = (cur + " " + word).strip()
            if fm.horizontalAdvance(trial) <= max_px or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines or [""]

    def _paint_strokes(self, p: QPainter) -> None:
        w, h = max(1, self.width()), max(1, self.height())
        z, px, py = self._zoom, self._pan[0], self._pan[1]
        pw_scale = z * (w / 800.0)
        for color, width, pts in self._strokes:
            if len(pts) < 2:
                continue
            path = QPainterPath()
            path.moveTo((pts[0][0] - px) * z * w + w / 2,
                        (pts[0][1] - py) * z * h + h / 2)
            for wx, wy in pts[1:]:
                path.lineTo((wx - px) * z * w + w / 2, (wy - py) * z * h + h / 2)
            for pw, mult in ((width * 1.6 * pw_scale, 0.28), (width * pw_scale, 1.0)):
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
        z, px, py = self._zoom, self._pan[0], self._pan[1]
        base = 22.0 * z * (w / 800.0)
        font = QFont("Marker Felt", int(max(6, base)))
        font.setBold(True)
        for it in self._items:
            x = (it["x"] - px) * z * w + w / 2
            y = (it["y"] - py) * z * h + h / 2
            if it["type"] == "text":
                fam, bold = self._font_family(it.get("font", "MARKER"))
                tfont = QFont(fam, int(max(6, base)))
                tfont.setBold(bold)
                fm = QFontMetrics(tfont)
                max_w = int(w * 0.26)
                lines = self._wrap(it["text"], tfont, max_w)
                p.setFont(tfont)
                line_h = fm.height()
                for i, line in enumerate(lines):
                    p.setPen(_WHITE)
                    p.drawText(QRectF(x, y + i * line_h, max_w, line_h),
                               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, line)
            elif it["type"] == "plan":
                self._paint_plan(p, it, x, y, w, z)
            elif it["type"] == "schedule":
                self._paint_schedule(p, it, x, y, w, z)
            elif it["type"] == "flow":
                self._paint_flow(p, it, x, y, w, z)
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

    def _paint_plan(self, p: QPainter, it, x: float, y: float, w: float, z: float) -> None:
        """A plan card: bordered box, bold title, numbered wrapped steps."""
        base = 12.0 * z * (w / 800.0)
        pad = 12.0 * z * (w / 800.0)
        card_w = w * 0.44
        title_font = QFont("Marker Felt", int(max(6, base * 1.4)))
        title_font.setBold(True)
        step_font = QFont("Marker Felt", int(max(5, base)))
        tmf = QFontMetrics(title_font)
        smf = QFontMetrics(step_font)
        title_h = tmf.height() + 6 * z * (w / 800.0)
        lines = []
        for i, step in enumerate(it["steps"], 1):
            lines.extend(self._wrap(f"{i}. {step}", step_font, card_w - 2 * pad))
        body_h = max(smf.height(), len(lines) * smf.height()) + 8 * z * (w / 800.0)
        rect = QRectF(x, y, card_w, title_h + body_h)
        p.setPen(QPen(QColor(255, 255, 255, 90), max(1.0, z)))
        p.setBrush(QColor(255, 255, 255, 12))
        p.drawRoundedRect(rect, 8 * z, 8 * z)
        p.setFont(title_font)
        p.setPen(_WHITE)
        p.drawText(QRectF(x + pad, y + 3 * z * (w / 800.0), card_w - 2 * pad, title_h),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, it["title"])
        p.setFont(step_font)
        p.setPen(QColor(255, 255, 255, 215))
        ty = y + title_h
        for line in lines:
            p.drawText(QRectF(x + pad, ty, card_w - 2 * pad, smf.height()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, line)
            ty += smf.height()

    def _paint_schedule(self, p: QPainter, it, x: float, y: float, w: float, z: float) -> None:
        """Excel-looking table: bordered cells, header row, alternating rows."""
        base = 11.0 * z * (w / 800.0)
        pad = 10.0 * z * (w / 800.0)
        card_w = w * 0.60
        cols = it["columns"] or (["TIME"] + [""] * (len(it["rows"][0]) - 1) if it["rows"] else ["TIME"])
        n_cols = max(1, len(cols))
        col_w = card_w / n_cols
        title_font = QFont("Marker Felt", int(max(6, base * 1.4)))
        title_font.setBold(True)
        cell_font = QFont("Marker Felt", int(max(5, base)))
        tmf = QFontMetrics(title_font)
        cmf = QFontMetrics(cell_font)
        title_h = tmf.height() + 6 * z * (w / 800.0)
        row_h = cmf.height() + 10 * z * (w / 800.0)

        # Height = title + header + data rows
        total_h = title_h + row_h + len(it["rows"]) * row_h + 2 * pad
        p.setPen(QPen(QColor(255, 255, 255, 80), 1))
        p.setBrush(QColor(255, 255, 255, 10))
        p.drawRoundedRect(QRectF(x, y, card_w, total_h), 8 * z, 8 * z)

        p.setFont(title_font)
        p.setPen(_WHITE)
        p.drawText(QRectF(x + pad, y + 3 * z * (w / 800.0), card_w - 2 * pad, title_h),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, it["title"])

        # Header row
        hy = y + title_h
        p.fillRect(QRectF(x + 1, hy, card_w - 2, row_h), QColor(255, 255, 255, 34))
        p.setFont(cell_font)
        p.setPen(_WHITE)
        for ci, col in enumerate(cols):
            p.drawText(QRectF(x + pad + ci * col_w, hy + 4 * z * (w / 800.0),
                              col_w - 2 * pad, row_h),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(col).upper())

        # Data rows with alternating shading + grid lines
        for ri, row in enumerate(it["rows"]):
            ry = hy + row_h + ri * row_h
            if ri % 2 == 1:
                p.fillRect(QRectF(x + 1, ry, card_w - 2, row_h), QColor(255, 255, 255, 12))
            for ci in range(n_cols):
                val = row[ci] if ci < len(row) else ""
                p.setPen(QColor(255, 255, 255, 220))
                p.drawText(QRectF(x + pad + ci * col_w, ry + 4 * z * (w / 800.0),
                                  col_w - 2 * pad, row_h),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, val)
            # horizontal grid line
            p.setPen(QPen(QColor(255, 255, 255, 55), 1))
            p.drawLine(QPointF(x + 1, ry + row_h), QPointF(x + card_w - 1, ry + row_h))
        # vertical grid lines
        p.setPen(QPen(QColor(255, 255, 255, 55), 1))
        for ci in range(1, n_cols):
            gx = x + ci * col_w
            p.drawLine(QPointF(gx, hy), QPointF(gx, y + total_h - pad))

    def _paint_flow(self, p: QPainter, it, x: float, y: float, w: float, z: float) -> None:
        """Vertical flowchart: rounded boxes connected by arrowed lines."""
        base = 11.0 * z * (w / 800.0)
        pad = 10.0 * z * (w / 800.0)
        card_w = w * 0.42
        title_font = QFont("Marker Felt", int(max(6, base * 1.4)))
        title_font.setBold(True)
        box_font = QFont("Marker Felt", int(max(5, base)))
        tmf = QFontMetrics(title_font)
        bmf = QFontMetrics(box_font)
        title_h = tmf.height() + 6 * z * (w / 800.0)
        box_h = bmf.height() * 2 + 10 * z * (w / 800.0)
        gap = 14.0 * z * (w / 800.0)

        p.setFont(title_font)
        p.setPen(_WHITE)
        p.drawText(QRectF(x, y, card_w, title_h),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, it["title"])

        by = y + title_h + 4 * z * (w / 800.0)
        for i, step in enumerate(it["steps"], 1):
            if i > 1:
                # arrow from previous box to this one
                ay = by - gap / 2
                p.setPen(QPen(QColor(255, 255, 255, 160), 1.5))
                p.drawLine(QPointF(x + card_w / 2, by - gap), QPointF(x + card_w / 2, by - 4 * z * (w / 800.0)))
                p.setBrush(QColor(255, 255, 255, 160))
                p.setPen(Qt.PenStyle.NoPen)
                tri = QPainterPath()
                tri.moveTo(x + card_w / 2 - 4 * z, by - 4 * z * (w / 800.0))
                tri.lineTo(x + card_w / 2 + 4 * z, by - 4 * z * (w / 800.0))
                tri.lineTo(x + card_w / 2, by)
                tri.closeSubpath()
                p.drawPath(tri)
            # box
            p.setPen(QPen(QColor(255, 255, 255, 120), 1))
            p.setBrush(QColor(255, 255, 255, 14))
            p.drawRoundedRect(QRectF(x, by, card_w, box_h), 6 * z, 6 * z)
            p.setFont(box_font)
            p.setPen(QColor(255, 255, 255, 235))
            lines = self._wrap(f"{i}. {step}", box_font, card_w - 2 * pad)
            ly = by + 5 * z * (w / 800.0)
            for line in lines[:2]:
                p.drawText(QRectF(x + pad, ly, card_w - 2 * pad, bmf.height()),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, line)
                ly += bmf.height()
            by += box_h + gap

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
    zoom_in_requested = pyqtSignal()
    zoom_out_requested = pyqtSignal()
    zoom_reset_requested = pyqtSignal()
    cam_toggled = pyqtSignal(bool)
    text_requested = pyqtSignal()

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

        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(4)
        zlab = QLabel("ZOOM")
        zlab.setFont(mono(7, bold=True))
        zlab.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent;")
        zoom_row.addWidget(zlab)

        def _zbtn(text: str, tip: str, sig) -> QPushButton:
            b = QPushButton(text)
            b.setFont(mono(8, bold=True))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(tip)
            b.setStyleSheet(
                "QPushButton { background: #0a0a0e; color: #9fd8e0;"
                " border: 1px solid rgba(0, 240, 255, 0.4); border-radius: 5px; padding: 3px 6px; }"
                "QPushButton:hover { background: #0e1a20; }"
            )
            b.clicked.connect(lambda: sig.emit())
            return b

        zoom_row.addWidget(_zbtn("−", "Zoom out (or press −)", self.zoom_out_requested))
        zoom_row.addWidget(_zbtn("+", "Zoom in (or press +)", self.zoom_in_requested))
        zoom_row.addWidget(_zbtn("100%", "Reset zoom (or press 0)", self.zoom_reset_requested))
        zoom_row.addStretch()
        lay.addLayout(zoom_row)

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
        cam_btn = QPushButton("👁 CAM")
        cam_btn.setFont(mono(8, bold=True))
        cam_btn.setCheckable(True)
        cam_btn.setChecked(True)
        cam_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cam_btn.setToolTip("Show / hide the little camera preview")
        cam_btn.setStyleSheet(
            "QPushButton { background: #0a0a0e; color: #9fd8e0;"
            " border: 1px solid rgba(0, 240, 255, 0.4); border-radius: 5px; padding: 5px 4px; }"
            "QPushButton:hover { background: #0e1a20; }"
            "QPushButton:checked { background: #0e3a42; color: #ffffff; }"
        )
        cam_btn.toggled.connect(self.cam_toggled.emit)
        grid.addWidget(cam_btn, 2, 0)
        txt_btn = QPushButton("✎ TEXT")
        txt_btn.setFont(mono(8, bold=True))
        txt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        txt_btn.setToolTip("Add a text note at the center (or double-click the canvas)")
        txt_btn.setStyleSheet(
            "QPushButton { background: #0a0a0e; color: #9fd8e0;"
            " border: 1px solid rgba(0, 240, 255, 0.4); border-radius: 5px; padding: 5px 4px; }"
            "QPushButton:hover { background: #0e1a20; }"
        )
        txt_btn.clicked.connect(lambda: self.text_requested.emit())
        grid.addWidget(txt_btn, 2, 1)
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
