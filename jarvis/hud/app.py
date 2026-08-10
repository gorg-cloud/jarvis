"""
jarvis/hud/app.py
Main JARVIS HUD application. Full-screen Stark Industries layout.
Detects external displays. Forces fullscreen on TV/external monitor.
"""
import sys
import subprocess
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QScreen, QGuiApplication
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QSplitter, QGraphicsOpacityEffect,
)

from .theme import BG, BG_PANEL, BG_PANEL_BORDER, CYAN, CYAN_DIM, WHITE, WHITE_DIM, mono
from .data import Telemetry
from .widgets import Panel, GaugeCircle, MiniGraph, MarkdownStream, KillButton, NowPlayingWidget, CalendarWidget


class HUDApp(QWidget):
    """Full-screen HUD on external display."""

    # Signal to push log from any thread
    log_signal = pyqtSignal(str)

    def __init__(self, screen: Optional[QScreen] = None, parent=None):
        super().__init__(parent)
        self._telemetry = Telemetry(interval=1.0)
        self._bt_server = None
        self._ram_history: list = []
        self._cpu_history: list = []

        # Apply to specific screen
        if screen:
            self.setScreen(screen)
            self.move(screen.geometry().topLeft())
            self.resize(screen.geometry().size())

        self._build_ui()
        self._wire_signals()
        self._start_telemetry()

    def set_log_callback(self, fn):
        """External caller pushes log lines into the HUD."""
        self.log_signal.connect(fn)

    def _build_ui(self):
        self.setWindowTitle("JARVIS HUD")
        self.setStyleSheet(f"background: {BG.name()};")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 8)
        root.setSpacing(10)

        # Top bar
        top = QHBoxLayout()
        top.setSpacing(16)
        title = QLabel("JARVIS")
        title.setFont(mono(18, bold=True))
        title.setStyleSheet(f"color: {CYAN.name()}; background: transparent; border: none;")
        top.addWidget(title)

        self._status_label = QLabel("● ONLINE")
        self._status_label.setFont(mono(10))
        self._status_label.setStyleSheet(f"color: {CYAN_DIM.name()}; background: transparent; border: none;")
        top.addWidget(self._status_label)

        top.addStretch()

        self._clock_label = QLabel("00:00:00")
        self._clock_label.setFont(mono(14, bold=True))
        self._clock_label.setStyleSheet(f"color: {WHITE.name()}; background: transparent; border: none;")
        top.addWidget(self._clock_label)

        kill = KillButton()
        kill.clicked.connect(self.close)
        top.addWidget(kill)
        root.addLayout(top)

        # Main content: 3-column splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(f"""
            QSplitter::handle {{ background: {BG_PANEL_BORDER.name()}; width: 1px; }}
        """)

        # LEFT: Telemetry gauges
        left_panel = Panel("TELEMETRY")
        left_v = QVBoxLayout()
        left_v.setSpacing(20)
        left_v.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._cpu_gauge = GaugeCircle("CPU", max_val=100, unit="%")
        self._ram_gauge = GaugeCircle("RAM", max_val=100, unit="%")
        self._bat_gauge = GaugeCircle("BATTERY", max_val=100, unit="%")
        for g in (self._cpu_gauge, self._ram_gauge, self._bat_gauge):
            left_v.addWidget(g, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Network graph
        self._ram_graph = MiniGraph("MEMORY %", max_points=60)
        left_v.addWidget(self._ram_graph)

        left_inner = QWidget()
        left_inner.setLayout(left_v)
        left_panel.add(left_inner)
        splitter.addWidget(left_panel)

        # CENTER: Markdown stream
        center_panel = Panel("CONSOLE")
        self._md_stream = MarkdownStream()
        center_panel.add(self._md_stream)
        splitter.addWidget(center_panel)

        # RIGHT: Connection info + secondary graphs
        right_panel = Panel("SYSTEM")
        right_v = QVBoxLayout()
        right_v.setSpacing(8)

        self._host_label = QLabel()
        self._host_label.setFont(mono(10))
        self._host_label.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent; border: none;")
        right_v.addWidget(self._host_label)

        self._os_label = QLabel()
        self._os_label.setFont(mono(10))
        self._os_label.setStyleSheet(f"color: {WHITE_DIM.name()}; background: transparent; border: none;")
        right_v.addWidget(self._os_label)

        right_v.addSpacing(10)

        # CPU graph
        self._cpu_graph = MiniGraph("CPU %", max_points=60)
        right_v.addWidget(self._cpu_graph)

        # Connection log (mini)
        self._conn_label = QLabel("BT: waiting...")
        self._conn_label.setFont(mono(9))
        self._conn_label.setStyleSheet(f"color: {CYAN_DIM.name()}; background: transparent; border: none;")
        self._conn_label.setWordWrap(True)
        right_v.addWidget(self._conn_label)

        right_v.addStretch()

        # Spotify Now Playing
        self._now_playing = NowPlayingWidget()
        right_v.addWidget(self._now_playing)

        # Calendar
        self._cal_widget = CalendarWidget()
        right_v.addWidget(self._cal_widget)

        right_v.addStretch()

        right_inner = QWidget()
        right_inner.setLayout(right_v)
        right_panel.add(right_inner)
        splitter.addWidget(right_panel)

        # Splitter ratios: 25 : 50 : 25
        splitter.setSizes([300, 500, 300])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 1)

        root.addWidget(splitter, stretch=1)

    def _wire_signals(self):
        self.log_signal.connect(self._md_stream.append)
        self._telemetry.on_update(self._on_telemetry)

        # Clock ticker
        self._clock_timer = QTimer()
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)

        # Spotify poll every 3s
        self._spotify_timer = QTimer()
        self._spotify_timer.timeout.connect(self._poll_spotify)
        self._spotify_timer.start(3000)

        # Calendar poll every 60s
        self._cal_timer = QTimer()
        self._cal_timer.timeout.connect(self._poll_calendar)
        self._cal_timer.start(60000)

    def _update_clock(self):
        import time
        self._clock_label.setText(time.strftime("%H:%M:%S"))

    def _on_telemetry(self, data: dict):
        # Gauges
        self._cpu_gauge.set_value(data.get("cpu", 0))
        self._ram_gauge.set_value(data.get("ram_pct", 0))
        self._bat_gauge.set_value(data.get("battery_pct", 0))

        # Graphs
        self._cpu_graph.push(data.get("cpu", 0))
        self._ram_graph.push(data.get("ram_pct", 0))

        # System info
        self._host_label.setText(f"HOST: {data.get('hostname', '?')}")
        self._os_label.setText(f"OS: {data.get('os', '?')}")

        # Push log entries
        for entry in data.get("log", [])[-10:]:
            self._md_stream.append(entry)

    def _start_telemetry(self):
        self._telemetry.start()
        self._md_stream.append("# JARVIS HUD Online")
        self._md_stream.append(f"* Host: {self._telemetry.hostname}")
        self._md_stream.append(f"* OS: {self._telemetry.os_name}")
        self._md_stream.append("")

    def _poll_spotify(self):
        script = '''
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
        try:
            r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                parts = r.stdout.strip().split("|", 3)
                self._now_playing.update_track({
                    "state": parts[0] if len(parts) > 0 else "stopped",
                    "track": parts[1] if len(parts) > 1 else "",
                    "artist": parts[2] if len(parts) > 2 else "",
                    "album": parts[3] if len(parts) > 3 else "",
                })
        except Exception:
            pass

    def _poll_calendar(self):
        try:
            from jarvis.tools.calendar_tool import week_events
            result = week_events(days=7)
            if result.get("events"):
                self._cal_widget.set_events(result["events"])
        except Exception:
            pass

    def push_log(self, text: str):
        """Thread-safe log push from external sources."""
        self.log_signal.emit(text)
        self._telemetry.add_log(text)

    def start_bluetooth(self, port: int = 1):
        from .bluetooth import BTServer
        self._bt_server = BTServer(port=port)
        self._bt_server.set_data_source(lambda: self._telemetry.latest)
        self._bt_server.start()

    def closeEvent(self, event):
        self._telemetry.stop()
        if self._bt_server:
            self._bt_server.stop()
        event.accept()

    @staticmethod
    def find_external_screen() -> Optional[QScreen]:
        """Find a non-primary screen (TV/external monitor)."""
        app = QApplication.instance()
        if not app:
            return None
        primary = app.primaryScreen()
        for screen in app.screens():
            if screen != primary:
                return screen
        return None

    @staticmethod
    def launch(preview: bool = False):
        """Launch the HUD. If external screen found, goes fullscreen there.
        If preview=True, opens in a normal window on primary screen."""
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv)

        screen = None
        if not preview:
            screen = HUDApp.find_external_screen()

        window = HUDApp(screen=screen)
        if screen and not preview:
            window.showFullScreen()
        else:
            window.resize(1280, 800)
            window.show()

        return app, window


if __name__ == "__main__":
    preview = "--preview" in sys.argv
    app, win = HUDApp.launch(preview=preview)
    sys.exit(app.exec())
