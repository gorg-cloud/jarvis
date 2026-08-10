"""
jarvis/app/voice_thread.py
Runs JARVIS voice modes on a worker thread so the GUI stays responsive,
and tracks the active session so only one voice loop runs at a time.
"""
import threading

from PyQt6.QtCore import QThread

from jarvis.voice import listen_loop

# mode: None → wake word ('jarvis'), 'once', or 'conversational'
VOICE_MODES = {"wake": None, "once": "once", "conversational": "conversational"}


class VoiceThread(QThread):
    """One voice session. `mode` is None (wake word), 'once', or 'conversational'."""

    def __init__(self, mode=None, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.stop_event = threading.Event()

    def run(self) -> None:
        try:
            listen_loop(mode=self.mode, stop_event=self.stop_event)
        except Exception as exc:  # pragma: no cover — defensive
            print(f"❌ Voice thread error: {exc}")
        finally:
            self.stop_event.set()

    def stop(self) -> None:
        self.stop_event.set()


class VoiceManager:
    """Only one voice session at a time; exposes start/stop for the UI."""

    def __init__(self):
        self._current: VoiceThread | None = None

    @property
    def active(self) -> bool:
        return self._current is not None and self._current.isRunning()

    def start(self, mode=None) -> str:
        if self.active:
            return "busy"
        thread = VoiceThread(mode=mode)
        thread.finished.connect(self._on_finished)
        self._current = thread
        thread.start()
        return "started"

    def stop(self) -> None:
        if self._current is not None:
            self._current.stop()

    def _on_finished(self) -> None:
        self._current = None
