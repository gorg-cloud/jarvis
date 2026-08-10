"""
jarvis/menu.py
The JARVIS "menu" — a Stark-Industries command interface with a big
pulsing arc reactor in the center, the latest news headlines and the
currently playing Spotify track.

Launch:
    python -m jarvis.menu            (development)
    JARVIS.app --menu                (packaged app)
"""
import math
import os
import subprocess
import sys
import time
import traceback
import urllib.request

_DEBUG_LOG = os.path.expanduser("~/.jarvis/debug.log")


def _debug(msg: str) -> None:
    """Append a line to ~/.jarvis/debug.log (the packaged app has no stderr)."""
    try:
        with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} [menu] {msg}\n")
    except Exception:
        pass


def _beep() -> None:
    from PyQt6.QtWidgets import QApplication
    try:
        QApplication.beep()
    except Exception:
        pass

from PyQt6.QtCore import QPointF, QRectF, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QRadialGradient
from PyQt6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QVBoxLayout, QWidget,
)

from jarvis.app.worker import JarvisWorker
from jarvis.engine.speaker import speak
from jarvis.hud.theme import BG, CYAN, WHITE, WHITE_DIM, mono
from jarvis.tools.briefing_tool import fetch_news_headlines

ACCENT = QColor("#00f0ff")


# ----------------------------------------------------------------------
# Big arc reactor
# ----------------------------------------------------------------------

class _BigArc(QWidget):
    """The centerpiece: layered rotating rings, orbiting particles, pulsing core."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(320, 320)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self) -> None:
        self._phase += 0.05
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.rect().center())
        pulse = 0.5 + 0.5 * math.sin(self._phase * 2.0)

        # Outer atmosphere glow
        r_glow = self.width() * 0.16 + 7 * pulse
        grad = QRadialGradient(c, r_glow * 2.3)
        grad.setColorAt(0.0, QColor(205, 255, 255, 200))
        grad.setColorAt(0.35, QColor(0, 240, 255, 140))
        grad.setColorAt(1.0, QColor(0, 240, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawEllipse(c, r_glow * 2.3, r_glow * 2.3)

        # Solid core
        core = 20 + 8 * pulse
        p.setBrush(QColor(219, 251, 255))
        p.drawEllipse(c, core, core)

        # Inner static halo ring
        pen = QPen(QColor(0, 240, 255, 90), 3)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        rr = self.width() * 0.30
        p.drawEllipse(c, rr, rr)

        # Rotating dashed rings (different speeds/directions)
        rings = [
            (0.43, 3.0, [7, 5], 1.0, 210),
            (0.36, 2.0, [3, 4], -0.7, 130),
            (0.27, 1.5, [2, 3], 0.5, 80),
        ]
        for frac, width, dash, speed, alpha in rings:
            r = self.width() * frac
            pen = QPen(QColor(0, 240, 255, alpha), width)
            pen.setDashPattern(dash)
            p.setPen(pen)
            p.drawArc(QRectF(c.x() - r, c.y() - r, r * 2, r * 2),
                      int(self._phase * speed * 57.3 * 16), 340 * 16)

        # Orbiting particles
        for i, frac in enumerate((0.38, 0.31, 0.24)):
            ang = self._phase * (1.2 + 0.35 * i) + i * 2.1
            r = self.width() * frac
            dx = c.x() + r * math.cos(ang)
            dy = c.y() + r * math.sin(ang)
            g = QRadialGradient(QPointF(dx, dy), 6)
            g.setColorAt(0.0, QColor(255, 255, 255, 230))
            g.setColorAt(1.0, QColor(0, 240, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawEllipse(QPointF(dx, dy), 6, 6)

        p.end()


# ----------------------------------------------------------------------
# News feed (RSS, stdlib only)
# ----------------------------------------------------------------------

class _NewsThread(QThread):
    loaded = pyqtSignal(dict)

    def run(self) -> None:
        self.loaded.emit(fetch_news_headlines(limit=6))


class _BriefThread(QThread):
    """Load the daily briefing (calendar/weather/mail/news) for the TODAY bar."""

    loaded = pyqtSignal(dict)

    def run(self) -> None:
        from jarvis.tools.briefing_tool import get_briefing
        self.loaded.emit(get_briefing())


def _itunes_art(track: str, artist: str) -> str:
    """Find album art via the iTunes Search API (no key needed)."""
    import json
    import urllib.parse
    term = urllib.parse.quote(f"{track} {artist}")
    url = f"https://itunes.apple.com/search?term={term}&entity=song&limit=1"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        results = data.get("results") or []
        if results and results[0].get("artworkUrl100"):
            return results[0]["artworkUrl100"].replace("100x100", "400x400")
    except Exception:
        pass
    return ""


class _ArtThread(QThread):
    loaded = pyqtSignal(object)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        # Only download in the worker thread — image decoding happens on the
        # GUI thread (QImage/QPixmap are not thread-safe here).
        try:
            req = urllib.request.Request(
                self._url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            if data:
                self.loaded.emit(data)
                return
        except Exception:
            pass
        self.loaded.emit(None)


class _SpeakThread(QThread):
    """One-shot mic capture + transcription (Google STT)."""

    done = pyqtSignal(str)

    def run(self) -> None:
        import speech_recognition as sr
        try:
            mic = sr.Microphone()
            rec = sr.Recognizer()
            rec.energy_threshold = 400
            rec.dynamic_energy_threshold = True
            with mic as source:
                # 10s timeout so it can never hang silently waiting for speech
                audio = rec.listen(source, timeout=10, phrase_time_limit=30)
            _debug("audio captured, transcribing…")
            text = rec.recognize_google(audio)
        except sr.WaitTimeoutError:
            self.done.emit("⚠ No speech heard — click SPEAK and speak right after the beep")
            return
        except sr.UnknownValueError:
            self.done.emit("⚠ Couldn't understand that — try again")
            return
        except Exception as exc:
            _debug(f"speak thread error: {type(exc).__name__}: {exc}")
            msg = f"⚠ {type(exc).__name__}: {exc}"
            if isinstance(exc, OSError):
                msg = "⚠ Microphone unavailable — check System Settings → Privacy & Security → Microphone"
            self.done.emit(msg)
            return
        _debug(f"transcribed: {text[:80]!r}")
        self.done.emit(text)


# ----------------------------------------------------------------------
# Spotify (osascript, same as the HUD)
# ----------------------------------------------------------------------

_SPOTIFY_SCRIPT = '''
tell application "Spotify"
    if player state is playing then
        set state to "playing"
    else if player state is paused then
        set state to "paused"
    else
        set state to "stopped"
    end if
    try
        return state & "|" & name of current track & "|" & artist of current track & "|" & album of current track
    on error
        return "stopped|||"
    end try
end tell
'''


def spotify_status() -> dict:
    """Now-playing info. macOS: AppleScript. Windows: none (no API key) → off."""
    from jarvis.platform import macos_only
    if macos_only("Spotify status"):
        return {"state": "off"}
    try:
        r = subprocess.run(["osascript", "-e", _SPOTIFY_SCRIPT],
                           capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return {"state": "off"}
        parts = r.stdout.strip().split("|", 3)
        return {
            "state": parts[0] if parts and parts[0] else "off",
            "track": parts[1] if len(parts) > 1 else "",
            "artist": parts[2] if len(parts) > 2 else "",
            "album": parts[3] if len(parts) > 3 else "",
        }
    except Exception:
        return {"state": "off"}


def battery_percent() -> str:
    try:
        from jarvis.platform import battery_status
        b = battery_status()
        if b.get("percent") is not None and b["percent"] >= 0:
            return f"{b['percent']}%"
    except Exception:
        pass
    return "--"


# ----------------------------------------------------------------------
# Window
# ----------------------------------------------------------------------

class MenuWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("J.A.R.V.I.S. — Menu")
        self.resize(1120, 720)
        self.setStyleSheet(f"background: {BG.name()};")
        self._build_ui()
        self._wire_timers()

    # ---- UI ----------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        central.setStyleSheet(f"background: {BG.name()};")
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel("J.A.R.V.I.S.")
        title.setFont(mono(20, bold=True))
        title.setStyleSheet(f"color: {ACCENT.name()}; background: transparent;")
        glow = QGraphicsDropShadowEffect(title)
        glow.setBlurRadius(30)
        glow.setColor(QColor(0, 240, 255, 180))
        glow.setOffset(0, 0)
        title.setGraphicsEffect(glow)
        header.addWidget(title)

        self._online = QLabel("● ONLINE")
        self._online.setFont(mono(10, bold=True))
        self._online.setStyleSheet(f"color: {ACCENT.name()}; background: transparent;")
        header.addWidget(self._online)
        header.addStretch()

        self._clock_label = QLabel("00:00:00")
        self._clock_label.setFont(mono(16, bold=True))
        self._clock_label.setStyleSheet(f"color: {WHITE.name()}; background: transparent;")
        header.addWidget(self._clock_label)
        root.addLayout(header)

        # TODAY briefing bar (populated by briefing.get)
        self._brief_label = QLabel("TODAY: loading…")
        self._brief_label.setFont(mono(9))
        self._brief_label.setWordWrap(True)
        self._brief_label.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent;")
        root.addWidget(self._brief_label)

        # Main row: NEWS | ARC | SPOTIFY
        main = QHBoxLayout()
        main.setSpacing(16)

        main.addWidget(self._build_panel("▣ LATEST NEWS", "news", 0))
        main.addStretch(1)

        center_col = QVBoxLayout()
        center_col.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._arc = _BigArc()
        center_col.addWidget(self._arc, alignment=Qt.AlignmentFlag.AlignCenter)
        self._sys_label = QLabel("ALL SYSTEMS NOMINAL")
        self._sys_label.setFont(mono(10, bold=True))
        self._sys_label.setStyleSheet(f"color: {ACCENT.name()}; background: transparent;")
        center_col.addWidget(self._sys_label, alignment=Qt.AlignmentFlag.AlignCenter)
        center_col.addSpacing(4)
        self._battery_label = QLabel("BATTERY --")
        self._battery_label.setFont(mono(9))
        self._battery_label.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent;")
        center_col.addWidget(self._battery_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self._speak_status = QLabel("")
        self._speak_status.setFont(mono(9))
        self._speak_status.setWordWrap(True)
        self._speak_status.setMaximumWidth(430)
        self._speak_status.setStyleSheet(f"color: {ACCENT.name()}; background: transparent;")
        center_col.addWidget(self._speak_status, alignment=Qt.AlignmentFlag.AlignCenter)

        center = QWidget()
        center.setLayout(center_col)
        main.addWidget(center)
        main.addStretch(1)

        main.addWidget(self._build_panel("♪ NOW PLAYING", "spotify", 1))
        root.addLayout(main, stretch=1)

        # Bottom controls
        controls = QHBoxLayout()
        footer = QLabel("J.A.R.V.I.S. MENU — IRON MAN OS v0.1")
        footer.setFont(mono(9))
        footer.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent;")
        controls.addWidget(footer)
        controls.addStretch(1)

        def _ctl(text: str) -> QPushButton:
            b = QPushButton(text)
            b.setFont(mono(10, bold=True))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton {{ background: #081018; color: {ACCENT.name()};"
                f" border: 1px solid rgba(0,240,255,0.5); border-radius: 8px; padding: 8px 18px; }}"
                f"QPushButton:hover {{ background: #0e1a20; border-color: {ACCENT.name()}; }}"
            )
            return b

        speak_btn = _ctl("🎙 SPEAK")
        speak_btn.clicked.connect(self._speak_once)
        close_btn = _ctl("✕ CLOSE")
        close_btn.clicked.connect(self.close)
        controls.addWidget(speak_btn)
        controls.addWidget(close_btn)
        root.addLayout(controls)

        self.setCentralWidget(central)

    def _build_panel(self, title: str, kind: str, _index: int) -> QFrame:
        frame = QFrame()
        frame.setFixedWidth(330)
        frame.setStyleSheet("QFrame { background: transparent; border: none; }")

        v = QVBoxLayout(frame)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)

        head = QLabel(title)
        head.setFont(mono(11, bold=True))
        head.setStyleSheet(f"color: {ACCENT.name()}; background: transparent;")
        v.addWidget(head)

        if kind == "news":
            self._news_source = QLabel("")
            self._news_source.setFont(mono(8))
            self._news_source.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent;")
            v.addWidget(self._news_source)
            self._news_box = QVBoxLayout()
            self._news_box.setSpacing(8)
            v.addLayout(self._news_box)
            v.addStretch(1)
        else:
            self._art_label = QLabel("")
            self._art_label.setFixedSize(150, 150)
            self._art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._art_label.setStyleSheet("background: transparent; border: none;")
            art_glow = QGraphicsDropShadowEffect(self._art_label)
            art_glow.setBlurRadius(28)
            art_glow.setColor(QColor(0, 240, 255, 90))
            art_glow.setOffset(0, 0)
            self._art_label.setGraphicsEffect(art_glow)
            v.addWidget(self._art_label, alignment=Qt.AlignmentFlag.AlignHCenter)

            self._track = QLabel("—")
            self._track.setFont(mono(14, bold=True))
            self._track.setWordWrap(True)
            self._track.setStyleSheet(f"color: {WHITE.name()}; background: transparent;")
            track_glow = QGraphicsDropShadowEffect(self._track)
            track_glow.setBlurRadius(18)
            track_glow.setColor(QColor(0, 240, 255, 120))
            track_glow.setOffset(0, 0)
            self._track.setGraphicsEffect(track_glow)
            v.addWidget(self._track)

            self._artist = QLabel("—")
            self._artist.setFont(mono(11))
            self._artist.setStyleSheet(f"color: {ACCENT.name()}; background: transparent;")
            v.addWidget(self._artist)

            self._album = QLabel("—")
            self._album.setFont(mono(9))
            self._album.setWordWrap(True)
            self._album.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent;")
            v.addWidget(self._album)

            self._play_state = QLabel("● OFFLINE")
            self._play_state.setFont(mono(9, bold=True))
            self._play_state.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent;")
            v.addWidget(self._play_state)
            v.addStretch(1)

        return frame

    # ---- Data ----------------------------------------------------------

    def _wire_timers(self) -> None:
        self._last_track = ""
        self._speak_thread = None
        self._art_thread = None
        self._speak_worker = None
        self._brief_thread = None
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

        self._spotify_timer = QTimer(self)
        self._spotify_timer.timeout.connect(self._poll_spotify)
        self._spotify_timer.start(5000)
        self._poll_spotify()

        self._battery_timer = QTimer(self)
        self._battery_timer.timeout.connect(self._poll_battery)
        self._battery_timer.start(30000)
        self._poll_battery()

        self._news_thread = _NewsThread(self)
        self._news_thread.loaded.connect(self._show_news)
        self._news_thread.start()

        # Daily briefing → TODAY bar (refresh every 5 min)
        self._load_brief()
        self._brief_timer = QTimer(self)
        self._brief_timer.timeout.connect(self._load_brief)
        self._brief_timer.start(5 * 60 * 1000)

    def _update_clock(self) -> None:
        self._clock_label.setText(time.strftime("%H:%M:%S"))

    def _poll_spotify(self) -> None:
        s = spotify_status()
        if s["state"] == "playing":
            track = s.get("track") or "—"
            self._track.setText(track)
            self._artist.setText(s.get("artist") or "—")
            self._album.setText(s.get("album") or "—")
            self._play_state.setText("● PLAYING — LIVE")
            self._play_state.setStyleSheet(f"color: {ACCENT.name()}; background: transparent;")
            self._online.setText("● ONLINE — SYNCING AUDIO")
            if track != self._last_track:
                self._last_track = track
                self._load_art(track, s.get("artist") or "")
        elif s["state"] == "paused":
            self._play_state.setText("❚❚ PAUSED")
            self._play_state.setStyleSheet(f"color: #8fd8e0; background: transparent;")
        else:
            self._track.setText("NOTHING PLAYING")
            self._artist.setText("")
            self._album.setText("")
            self._art_label.clear()
            self._play_state.setText("● OFFLINE")
            self._play_state.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent;")

    def _poll_battery(self) -> None:
        self._battery_label.setText(f"BATTERY {battery_percent()}")

    def _load_art(self, track: str, artist: str) -> None:
        url = _itunes_art(track, artist)
        if not url:
            self._art_label.clear()
            return
        self._art_thread = _ArtThread(url)
        self._art_thread.loaded.connect(self._on_art)
        self._art_thread.start()

    def _on_art(self, data) -> None:
        if not data:
            self._art_label.clear()
            return
        img = QImage.fromData(data)
        if img.isNull():
            self._art_label.clear()
            return
        pm = QPixmap.fromImage(img)
        self._art_label.setPixmap(pm.scaled(
            150, 150, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))

    # ---- Speak button ---------------------------------------------------

    def _speak_once(self) -> None:
        if self._speak_thread is not None and self._speak_thread.isRunning():
            _debug("speak clicked while already listening")
            return
        self._speak_status.setText("🎙 LISTENING… speak now")
        _beep()
        _debug("speak: listening started")
        self._speak_thread = _SpeakThread(self)
        self._speak_thread.done.connect(self._on_speak_done)
        self._speak_thread.start()

    def _on_speak_done(self, text: str) -> None:
        _debug(f"speak done: {text[:80]!r}")
        if text.startswith("⚠"):
            self._speak_status.setText(text)
            return
        self._speak_status.setText(f"YOU: {text}")
        worker = JarvisWorker(text)
        self._speak_worker = worker
        worker.finished_with.connect(self._on_menu_reply)
        worker.start()

    def _on_menu_reply(self, reply: dict) -> None:
        _debug(f"menu reply: {str(reply)[:120]}")
        if reply.get("error"):
            self._speak_status.setText("⚠ " + str(reply["error"])[:90])
            return
        message = reply.get("message") or ""
        logs = reply.get("logs", "")
        if message:
            speak(message)
            self._speak_status.setText("J.A.R.V.I.S.: " + message[:90])
        elif logs:
            speak("Done, sir.")
            self._speak_status.setText("✔ " + logs[:90])

    def _load_brief(self) -> None:
        if self._brief_thread is not None and self._brief_thread.isRunning():
            return
        self._brief_thread = _BriefThread(self)
        self._brief_thread.loaded.connect(self._show_brief)
        self._brief_thread.start()

    def _show_brief(self, data: dict) -> None:
        summary = (data or {}).get("summary", "")
        self._brief_label.setText("TODAY: " + (summary or "nothing notable"))

    def _show_news(self, data: dict) -> None:
        # Clear previous headlines
        while self._news_box.count():
            item = self._news_box.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        if data.get("error"):
            label = QLabel("⚠ " + data["error"])
            label.setWordWrap(True)
            label.setStyleSheet(f"color: #ff8a8a; background: transparent;")
            self._news_box.addWidget(label)
            return
        self._news_source.setText(f"SOURCE: {data.get('source', '')}")
        for i, headline in enumerate(data.get("headlines", [])):
            label = QLabel(f"{i + 1:02d}  {headline}")
            label.setWordWrap(True)
            label.setFont(mono(9))
            label.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent;")
            self._news_box.addWidget(label)


def run() -> int:
    def _hook(exc_type, exc, tb):
        try:
            with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
                f.write(f"\n{time.strftime('%H:%M:%S')} [menu-excepthook] {''.join(traceback.format_exception(exc_type, exc, tb))}\n")
        except Exception:
            pass
    sys.excepthook = _hook

    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setApplicationName("JARVIS Menu")
    app.setApplicationDisplayName("JARVIS Menu")
    _debug("menu window starting")
    win = MenuWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
