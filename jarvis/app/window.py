"""
jarvis/app/window.py
Animated JARVIS chat window — Stark-Industries styling with a glowing
arc-reactor logo, a pulsing status indicator, glowing message bubbles and
a typewriter effect for JARVIS's replies.
"""
import math
import os
import subprocess
import time
import traceback
from typing import Set

from PyQt6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QAction, QColor, QFont, QLinearGradient, QPainter, QPen, QRadialGradient,
)
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from jarvis.app.prefs import get as get_pref
from jarvis.app.prefs import set_ as set_pref
from jarvis.app.recent import add as recent_add
from jarvis.app.recent import clear as recent_clear
from jarvis.app.recent import load as recent_load
from jarvis.app.worker import JarvisWorker
from jarvis.hud.theme import BG, CYAN, WHITE, WHITE_DIM, mono

_DEBUG_LOG = os.path.expanduser("~/.jarvis/debug.log")


def _debug(msg: str) -> None:
    """Append a line to ~/.jarvis/debug.log (the packaged app has no stderr)."""
    try:
        with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} [window] {msg}\n")
    except Exception:
        pass

ACCENT = QColor("#00f0ff")
ACCENT_SOFT = QColor(0, 240, 255, 110)
USER_FG = QColor("#ffffff")
LOG_FG = QColor("#5f7a99")
ERR_FG = QColor("#ff5c5c")

_WELCOME = (
    "J.A.R.V.I.S. at your service.\n"
    "Try: \"capture this in Obsidian\", \"add a task to Notion\", "
    "\"check my calendar\", \"what's my battery?\", \"open chrome\"."
)


# ----------------------------------------------------------------------
# Animated widgets
# ----------------------------------------------------------------------

class _ArcLogo(QWidget):
    """Rotating dashed rings + pulsing core — the arc reactor mark."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(58, 58)
        self._phase = 0.0
        self._busy = False
        self._timer = QTimer(self)
        self._timer.setInterval(33)          # ~30 fps
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy

    def _tick(self) -> None:
        self._phase += 0.06
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.rect().center())
        pulse = 0.5 + 0.5 * math.sin(self._phase * 2.0)
        busy_wobble = 0.5 + 0.5 * math.sin(self._phase * 7.0) if self._busy else 0.0

        # Outer glow
        glow_r = 12 + 4 * pulse + 6 * busy_wobble
        grad = QRadialGradient(c, glow_r * 2.4)
        grad.setColorAt(0.0, QColor(190, 255, 255, 220))
        grad.setColorAt(0.35, QColor(0, 240, 255, 150))
        grad.setColorAt(1.0, QColor(0, 240, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawEllipse(QPointF(c), glow_r * 2.4, glow_r * 2.4)

        # Solid core
        core_r = 4.5 + 1.6 * pulse + 2.2 * busy_wobble
        p.setBrush(QColor("#d9fbff"))
        p.drawEllipse(QPointF(c), core_r, core_r)

        # Outer rotating dashed ring
        pen = QPen(QColor(0, 240, 255, 210), 2)
        pen.setDashPattern([5, 5])
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        r1 = 26
        p.drawArc(QRectF(c.x() - r1, c.y() - r1, r1 * 2, r1 * 2),
                  int(-self._phase * 57.3 * 16), 320 * 16)

        # Inner counter-rotating ring
        pen2 = QPen(QColor(0, 240, 255, 100), 1)
        pen2.setDashPattern([2, 4])
        p.setPen(pen2)
        r2 = 20
        p.drawArc(QRectF(c.x() - r2, c.y() - r2, r2 * 2, r2 * 2),
                  int(self._phase * 41.0 * 16), 260 * 16)

        p.end()


class _StatusIndicator(QWidget):
    """Pulsing dot (idle) or animated equalizer bars (busy) + status text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(190, 34)
        self._phase = 0.0
        self._busy = False
        self._label = "ONLINE"
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_busy(self, busy: bool, label: str = "") -> None:
        self._busy = busy
        if label:
            self._label = label

    def _tick(self) -> None:
        self._phase += 0.12
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Animated element on the left: bars when busy, pulsing dot when idle.
        x = 6
        y_mid = self.height() / 2.0
        if self._busy:
            for i in range(5):
                h = 4 + 10 * (0.5 + 0.5 * math.sin(self._phase * 3.0 + i * 1.15))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 240, 255, 190))
                p.drawRoundedRect(QRectF(x, y_mid - h / 2, 3, h), 1.5, 1.5)
                x += 7
            label = self._label or "PROCESSING"
            color = QColor(0, 240, 255, 235)
        else:
            pulse = 0.5 + 0.5 * math.sin(self._phase * 2.0)
            r = 4 + 2 * pulse
            glow = QRadialGradient(QPointF(x + 4, y_mid), r * 3)
            glow.setColorAt(0.0, QColor(0, 240, 255, 200))
            glow.setColorAt(1.0, QColor(0, 240, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QPointF(x + 4, y_mid), r * 3, r * 3)
            p.setBrush(QColor("#aefaff"))
            p.drawEllipse(QPointF(x + 4, y_mid), r, r)
            label = self._label or "ONLINE"
            color = QColor(0, 240, 255, 180)

        p.setPen(color)
        p.setFont(mono(10, bold=True))
        p.drawText(self.rect().adjusted(0, 0, -6, 0),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   label)
        p.end()


class _Bubble(QLabel):
    """A chat message bubble. JARVIS bubbles glow; replies can type out."""

    typing_finished = pyqtSignal()

    def __init__(self, text: str, kind: str = "jarvis", animate: bool = False, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._full = text
        self._shown = 0
        self._tick = 0
        self.setWordWrap(True)
        self.setMaximumWidth(600)
        self.setFont(mono(11))
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        if kind == "user":
            self.setStyleSheet(
                "background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.14);"
                "color: #ffffff; border-radius: 10px; padding: 10px 14px;"
            )
        elif kind == "error":
            self.setStyleSheet(
                "background: rgba(255,92,92,0.08); border: 1px solid rgba(255,92,92,0.45);"
                "color: #ff8a8a; border-radius: 10px; padding: 10px 14px;"
            )
        elif kind == "log":
            self.setStyleSheet("color: #5f7a99; background: transparent; border: none; padding: 2px 8px;")
            self.setFont(mono(9))
        else:  # jarvis
            self.setStyleSheet(
                "background: #081018; border: 1px solid rgba(0,240,255,0.5);"
                "color: #00f0ff; border-radius: 10px; padding: 10px 14px;"
            )
            # Glow is applied only AFTER typing completes — rendering a
            # drop-shadow on every character stalls the main thread.
            if not animate:
                self._apply_glow()

        if animate and kind == "jarvis":
            self.setText("")
        else:
            self.setText(text)

    def _advance(self, count: int = 1) -> bool:
        """Type `count` more characters. Returns True when the message is complete.
        Never raises — on any error the message is force-completed."""
        self._tick += 1
        self._shown = min(self._shown + count, len(self._full))
        try:
            if self._shown < len(self._full):
                caret = "▍" if (self._tick // 16) % 2 == 0 else ""
                self.setText(self._full[: self._shown] + caret)
                return False
            self.setText(self._full)
            self._apply_glow()
            self.typing_finished.emit()
            return True
        except Exception:
            _debug(f"_advance exception len={len(self._full)} shown={self._shown}: {traceback.format_exc()}")
            self.setText(self._full)
            self._apply_glow()
            self.typing_finished.emit()
            return True

    def _apply_glow(self) -> None:
        """Add the cyan drop-shadow once (skipped during typing for speed)."""
        if self.graphicsEffect() is not None:
            return
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(22)
        glow.setColor(QColor(0, 240, 255, 130))
        glow.setOffset(0, 0)
        self.setGraphicsEffect(glow)


# ----------------------------------------------------------------------
# Main window
# ----------------------------------------------------------------------

class ChatWindow(QMainWindow):
    """Animated JARVIS chat window. `controller` is optional (tests)."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._workers: Set[JarvisWorker] = set()
        self._active = 0          # running query workers
        self._typing = False      # a reply is currently typing out
        self._typing_bubbles: list = []   # bubbles currently typing
        self._typing_timer = QTimer(self)
        self._typing_timer.setInterval(12)
        self._typing_timer.timeout.connect(self._tick_typing_all)
        # Independent watchdog: a window-owned timer that re-checks every 100ms
        # and force-completes any reply that runs past its deadline. Unlike a
        # one-shot QTimer.singleShot(lambda), this can never be garbage-collected
        # or lost, so typing cannot stall silently.
        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setInterval(100)
        self._watchdog_timer.timeout.connect(self._watchdog_check)
        self._watchdog_timer.start()

        self.setWindowTitle("JARVIS — Desktop Assistant")
        self.resize(900, 660)
        self.setStyleSheet(f"background: {BG.name()};")

        self._build_ui()
        self._build_menus()
        self._apply_startup_prefs()
        self._append_jarvis(_WELCOME, animate=True)

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        central = QWidget()
        central.setStyleSheet(f"background: {BG.name()};")
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # ---- Header -------------------------------------------------------
        header = QHBoxLayout()
        header.setSpacing(14)

        self._logo = _ArcLogo()
        header.addWidget(self._logo)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel("J.A.R.V.I.S.")
        title.setFont(mono(18, bold=True))
        title.setStyleSheet(f"color: {ACCENT.name()}; background: transparent;")
        glow = QGraphicsDropShadowEffect(title)
        glow.setBlurRadius(26)
        glow.setColor(QColor(0, 240, 255, 170))
        glow.setOffset(0, 0)
        title.setGraphicsEffect(glow)
        titles.addWidget(title)

        sub = QLabel("DESKTOP ASSISTANT — IRON MAN OS")
        sub.setFont(mono(9))
        sub.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent; letter-spacing: 2px;")
        titles.addWidget(sub)
        header.addLayout(titles)

        header.addStretch()
        self._status = _StatusIndicator()
        header.addWidget(self._status)
        root.addLayout(header)

        # Thin accent divider with a glow
        divider = QWidget()
        divider.setFixedHeight(2)
        divider.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            " stop:0 rgba(0,240,255,0), stop:0.5 rgba(0,240,255,160), stop:1 rgba(0,240,255,0));"
        )
        root.addWidget(divider)

        # ---- Chat scroll area ---------------------------------------------
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: #0a0a0e; width: 8px; border: none; }"
            "QScrollBar::handle:vertical { background: rgba(0,240,255,0.35); border-radius: 4px; min-height: 24px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )

        self._chat_container = QWidget()
        self._chat_container.setStyleSheet("background: transparent;")
        self._chat_vbox = QVBoxLayout(self._chat_container)
        self._chat_vbox.setContentsMargins(4, 8, 12, 8)
        self._chat_vbox.setSpacing(10)
        self._chat_vbox.addStretch(1)
        self._scroll.setWidget(self._chat_container)
        root.addWidget(self._scroll, stretch=1)

        # ---- Input row -----------------------------------------------------
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask J.A.R.V.I.S. anything…")
        self._input.setFont(mono(11))
        self._input.setStyleSheet(
            f"background: #0a0a0e; color: {WHITE.name()}; border: 1px solid #1c2733;"
            f"border-radius: 8px; padding: 9px 12px; selection-background-color: #0e3a42;"
        )
        self._input.returnPressed.connect(self._send)
        input_row.addWidget(self._input, stretch=1)

        def _button(text: str, accent: bool = False) -> QPushButton:
            b = QPushButton(text)
            b.setFont(mono(10, bold=True))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            color = ACCENT.name() if accent else "#8fd8e0"
            b.setStyleSheet(
                f"QPushButton {{ background: #0a0a0e; color: {color};"
                f" border: 1px solid rgba(0,240,255,0.5); border-radius: 8px; padding: 9px 16px; }}"
                f"QPushButton:hover {{ background: #0e1a20; border-color: {ACCENT.name()}; }}"
                f"QPushButton:pressed {{ background: #062028; }}"
            )
            return b

        camera_btn = _button("CAMERA ▣")
        camera_btn.clicked.connect(self._open_camera)
        send_btn = _button("SEND ▸", accent=True)
        send_btn.clicked.connect(self._send)
        voice_btn = _button("VOICE")
        voice_btn.clicked.connect(lambda: self._start_voice("once"))
        clear_btn = _button("CLEAR")
        clear_btn.clicked.connect(lambda: self._clear_chat())

        input_row.addWidget(camera_btn)
        input_row.addWidget(send_btn)
        input_row.addWidget(voice_btn)
        input_row.addWidget(clear_btn)
        root.addLayout(input_row)

        self.setCentralWidget(central)

    def _build_menus(self) -> None:
        bar = self.menuBar()
        bar.setStyleSheet(f"background: {BG.name()}; color: {WHITE_DIM.name()};")

        jarvis_menu = bar.addMenu("JARVIS")
        self._add_action(jarvis_menu, "Open Camera", self._open_camera, "Meta+1")
        self._add_action(jarvis_menu, "HUD Preview", lambda: self._controller.launch_hud(preview=True), "Meta+2")
        jarvis_menu.addSeparator()
        self._add_action(jarvis_menu, "Settings…", self._open_settings, "Meta+,")
        jarvis_menu.addSeparator()
        self._add_action(jarvis_menu, "Quit", lambda: self._controller.quit())

        voice_menu = bar.addMenu("Voice")
        self._add_action(voice_menu, "One command", lambda: self._start_voice("once"), "Meta+3")
        self._add_action(voice_menu, "Conversational", lambda: self._start_voice("conversational"), "Meta+4")
        self._add_action(voice_menu, "Wake word (say “JARVIS”)", lambda: self._start_voice("wake"))
        self._add_action(voice_menu, "Stop voice", lambda: self._controller.voice.stop())

        ask_menu = bar.addMenu("ASK")
        ask_menu.aboutToShow.connect(lambda: self._fill_ask_menu(ask_menu))
        self._fill_ask_menu(ask_menu)

        help_menu = bar.addMenu("Help")
        self._add_action(help_menu, "Example commands", self._show_examples)

    def _add_action(self, menu, text: str, slot, shortcut: str = None) -> QAction:
        act = QAction(text, self)
        if shortcut:
            act.setShortcut(shortcut)
        act.triggered.connect(slot)
        menu.addAction(act)
        return act

    def _fill_ask_menu(self, menu) -> None:
        """Rebuild the ASK menu from persisted recent commands."""
        menu.clear()
        recents = recent_load()
        if not recents:
            act = menu.addAction("No recent commands yet")
            act.setEnabled(False)
            return
        for cmd in recents:
            label = cmd if len(cmd) <= 46 else cmd[:45] + "…"
            act = menu.addAction("⌘ " + label)
            act.triggered.connect(lambda _=False, c=cmd: self.submit_command(c))
        menu.addSeparator()
        self._add_action(menu, "Clear history", recent_clear)

    def _apply_startup_prefs(self) -> None:
        if get_pref("always_on_top", False):
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

    def _open_settings(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("JARVIS — Settings")
        dlg.setStyleSheet(f"background: {BG.name()}; color: {WHITE.name()};")
        v = QVBoxLayout(dlg)
        v.setSpacing(12)

        title = QLabel("SETTINGS")
        title.setFont(mono(12, bold=True))
        title.setStyleSheet(f"color: {ACCENT.name()}; background: transparent; letter-spacing: 2px;")
        v.addWidget(title)

        top = QCheckBox("Keep window always on top")
        top.setFont(mono(10))
        top.setChecked(bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))

        def _toggle(checked: bool) -> None:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
            self.show()
            set_pref("always_on_top", checked)

        top.toggled.connect(_toggle)
        v.addWidget(top)

        def _open_config_dir() -> None:
            subprocess.Popen(["open", os.path.expanduser("~/.jarvis")])

        btn_cfg = QPushButton("Open config folder")
        btn_cfg.setFont(mono(10))
        btn_cfg.clicked.connect(_open_config_dir)
        v.addWidget(btn_cfg)

        hint = QLabel("Tip: API keys live in ~/.jarvis/.env —".ljust(50))
        hint.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent;")
        hint.setFont(mono(8))
        v.addWidget(hint)

        btn_close = QPushButton("Close")
        btn_close.setFont(mono(10, bold=True))
        btn_close.clicked.connect(dlg.accept)
        v.addWidget(btn_close)
        dlg.exec()

    # ------------------------------------------------------------------ I/O

    def _send(self) -> None:
        self.submit_command(self._input.text())
        self._input.clear()

    def submit_command(self, text: str) -> None:
        """Send a command to JARVIS (used by the input box, tray ASK menu and
        recents). Records it in the recent-commands history."""
        text = text.strip()
        if not text:
            return
        self._flush_typing()
        self._append_user(text)
        recent_add(text)

        self._set_busy(self._active + 1)
        worker = JarvisWorker(text)
        worker.finished_with.connect(self._on_reply)
        worker.finished.connect(lambda: self._worker_done(worker))
        self._workers.add(worker)
        worker.start()

    def _worker_done(self, worker: JarvisWorker) -> None:
        self._workers.discard(worker)
        self._set_busy(max(0, self._active - 1))

    def _open_camera(self) -> None:
        """Launch the JARVIS camera (gesture control) window."""
        try:
            from jarvis.tools.gestures_tool import start_gestures
            result = start_gestures()
            if result.get("error"):
                self._append_log("⚠ Camera: " + result["error"], error=True)
            else:
                self._append_log("📷 Opening JARVIS camera…")
        except Exception as exc:
            self._append_log(f"⚠ Camera: {exc}", error=True)

    def _start_voice(self, mode: str) -> None:
        from jarvis.app.voice_thread import VOICE_MODES
        if self._controller is None:
            return
        result = self._controller.voice.start(VOICE_MODES[mode])
        if result == "busy":
            self._append_log("Voice is already running — stop it first.", error=True)
        else:
            self._append_log(f"Voice started ({mode}) — replies are spoken.")

    def _on_reply(self, reply: dict) -> None:
        error = reply.get("error")
        if error:
            _debug(f"reply error: {error[:120]!r}")
            self._append_log(error, error=True)
            return
        message = reply.get("message")
        logs = reply.get("logs", "")
        _debug(f"reply received message={message!r} logs={logs[:80]!r}")
        self._flush_typing()
        if message:
            self._append_jarvis(message, animate=True)
        if logs and logs != "✅ No tool calls":
            self._append_log("⚙ " + logs)

    # ------------------------------------------------------------------ chat

    def _clear_chat(self) -> None:
        self._typing_bubbles.clear()
        self._typing_timer.stop()
        while self._chat_vbox.count() > 1:  # keep trailing stretch
            item = self._chat_vbox.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._append_jarvis(_WELCOME, animate=True)

    def _set_busy(self, active: int) -> None:
        self._active = max(0, active)
        busy = self._active > 0 or self._typing
        self._logo.set_busy(busy)
        self._status.set_busy(busy, "PROCESSING" if self._active > 0 else "TYPING")

    def _scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _append_user(self, text: str) -> None:
        bubble = _Bubble(text, kind="user")
        self._add_bubble(bubble, align_right=True, fade=True)

    def _append_jarvis(self, text: str, animate: bool = False) -> None:
        bubble = _Bubble(text, kind="jarvis", animate=animate)
        if animate:
            self._typing = True
            self._set_busy(self._active)
            bubble.typing_finished.connect(self._on_typing_done)
            bubble._typing_started = time.time()
            bubble._typing_deadline = time.time() + max(3.0, len(text) * 0.04)
            self._typing_bubbles.append(bubble)
            if not self._typing_timer.isActive():
                self._typing_timer.start()
            _debug(f"typing start len={len(text)} full={text[:80]!r}")
        self._add_bubble(bubble, align_right=False)

    def _append_log(self, text: str, error: bool = False) -> None:
        self._add_bubble(_Bubble(text, kind="error" if error else "log"),
                         align_right=False, fade=True)

    def _add_bubble(self, bubble: _Bubble, align_right: bool, fade: bool = False) -> None:
        self._chat_vbox.insertWidget(self._chat_vbox.count() - 1, bubble,
                                     alignment=Qt.AlignmentFlag.AlignRight if align_right
                                     else Qt.AlignmentFlag.AlignLeft)
        if fade:
            op = QGraphicsOpacityEffect(bubble)
            bubble.setGraphicsEffect(op)
            anim = QPropertyAnimation(op, b"opacity", bubble)
            anim.setDuration(220)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._scroll_to_bottom()

    def _tick_typing_all(self) -> None:
        now = time.time()
        for bubble in list(self._typing_bubbles):
            # In-tick stall detector (second watchdog): if a bubble has been
            # typing noticeably longer than expected, force-finish it.
            expected = len(bubble._full) * 0.02 + 2.0  # seconds
            if (now - getattr(bubble, "_typing_started", now) > expected
                    and bubble._shown < len(bubble._full)):
                _debug(f"in-tick stall: shown={bubble._shown} len={len(bubble._full)}")
                bubble._shown = len(bubble._full)
            if bubble._advance(2):
                _debug(f"typing done len={len(bubble._full)} full={bubble._full[:80]!r}")
                if bubble in self._typing_bubbles:
                    self._typing_bubbles.remove(bubble)
        if self._typing_bubbles:
            self._scroll_to_bottom()
        else:
            self._typing_timer.stop()

    def _watchdog_check(self) -> None:
        """Window-owned watchdog, re-checked every 100ms: force-complete any
        reply that has run past its deadline, even if the typing timer died."""
        now = time.time()
        for bubble in list(self._typing_bubbles):
            deadline = getattr(bubble, "_typing_deadline", None)
            if deadline is None or bubble._shown >= len(bubble._full):
                continue
            if now > deadline:
                _debug(f"WATCHDOG fired: shown={bubble._shown} len={len(bubble._full)} full={bubble._full[:80]!r}")
                self._force_finish_typing(bubble)

    def _flush_typing(self) -> None:
        """Force-complete any replies still typing. Called before appending new
        content so a stalled typewriter can never block the conversation."""
        for bubble in list(self._typing_bubbles):
            self._force_finish_typing(bubble)
        if self._typing_bubbles:
            self._typing_bubbles.clear()
            self._typing_timer.stop()
        self._typing = False
        self._set_busy(self._active)

    def _force_finish_typing(self, bubble) -> None:
        if bubble not in self._typing_bubbles:
            return
        _debug(f"force-finish: shown={bubble._shown} len={len(bubble._full)} full={bubble._full[:80]!r}")
        self._typing_bubbles.remove(bubble)
        bubble._shown = len(bubble._full)
        bubble.setText(bubble._full)
        bubble._apply_glow()
        bubble.typing_finished.emit()
        if not self._typing_bubbles:
            self._typing_timer.stop()

    def _on_typing_done(self) -> None:
        self._typing = False
        self._set_busy(self._active)

    def _show_examples(self) -> None:
        QMessageBox.information(
            self, "JARVIS — example commands",
            "• Capture in Obsidian: “note down that the server restarted at 2pm”\n"
            "• “Add a task to Notion: finish quarterly report”\n"
            "• “What did I write about X?” → searches your Obsidian vault\n"
            "• “Check my calendar” / “What’s next on my calendar?”\n"
            "• “Open Spotify and play something” / “What’s my battery?”\n"
            "• “Set an alarm for 7am” / “Remind me to call mom tomorrow at 6pm”\n"
            "• “Search the web for …” / “Open chrome”",
        )
