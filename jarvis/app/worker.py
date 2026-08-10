"""
jarvis/app/worker.py
Runs a JARVIS query off the Qt main thread. Each query gets its own
asyncio event loop so the GUI never blocks on network/LLM calls.
"""
import asyncio
import os
import time
import traceback

from PyQt6.QtCore import QThread, pyqtSignal

from jarvis.main import process_user_input

_DEBUG_LOG = os.path.expanduser("~/.jarvis/debug.log")


def _debug(msg: str) -> None:
    try:
        with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} [worker] {msg}\n")
    except Exception:
        pass


class JarvisWorker(QThread):
    """Execute one user request and emit the reply dict."""

    finished_with = pyqtSignal(dict)

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            reply = loop.run_until_complete(process_user_input(self._text))
        except Exception as exc:  # defensive — process_user_input handles its own errors
            reply = {"error": f"{type(exc).__name__}: {exc}"}
        finally:
            loop.close()
        _debug(f"worker emits message={reply.get('message')!r} logs={reply.get('logs', '')[:60]!r}")
        self.finished_with.emit(reply)
