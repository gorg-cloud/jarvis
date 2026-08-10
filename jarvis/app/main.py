"""
jarvis/app/main.py
Ties the desktop app together: QApplication, menu-bar (tray) icon,
the chat window, voice manager, web hub, and HUD launcher.
"""
import os
import subprocess
import sys
import time
import traceback

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from jarvis.app import recent
from jarvis.app import status as app_status

_DEBUG_LOG = os.path.expanduser("~/.jarvis/debug.log")


def _install_excepthook() -> None:
    """Route uncaught exceptions to ~/.jarvis/debug.log (packaged app has no stderr)."""

    def _hook(exc_type, exc, tb):
        try:
            with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
                f.write(f"\n{time.strftime('%H:%M:%S')} [excepthook] {''.join(traceback.format_exception(exc_type, exc, tb))}\n")
        except Exception:
            pass

    sys.excepthook = _hook

from jarvis.app.make_icon import load_icon
from jarvis.app.voice_thread import VOICE_MODES, VoiceManager
from jarvis.app.window import ChatWindow


class Controller:
    """Shared state + actions used by both the tray menu and the window."""

    def __init__(self) -> None:
        self.voice = VoiceManager()

    def launch_hud(self, preview: bool = True) -> None:
        """Launch the PyQt HUD. In the packaged app we re-enter the bundle
        with --hud; in development we run python -m jarvis.hud.app."""
        try:
            if getattr(sys, "frozen", False):
                cmd = [sys.executable, "--hud"] + (["--preview"] if preview else [])
            else:
                cmd = [sys.executable, "-m", "jarvis.hud.app"] + (["--preview"] if preview else [])
            subprocess.Popen(cmd, start_new_session=True)
        except Exception as exc:
            print(f"⚠️ Could not launch HUD: {exc}")

    def quit(self) -> None:
        self.voice.stop()
        QApplication.quit()


def _show_window(window: ChatWindow) -> None:
    window.show()
    window.raise_()
    window.activateWindow()


def _fill_ask_menu(menu: QMenu, window: ChatWindow) -> None:
    """Rebuild the tray ASK submenu from persisted recent commands."""
    menu.clear()
    recents = recent.load()
    if not recents:
        act = menu.addAction("No recent commands yet")
        act.setEnabled(False)
        return
    for cmd in recents:
        label = cmd if len(cmd) <= 46 else cmd[:45] + "…"
        act = menu.addAction("⌘ " + label)
        act.triggered.connect(lambda _=False, c=cmd: (window.submit_command(c), _show_window(window)))
    menu.addSeparator()
    act_clear = menu.addAction("Clear history")
    act_clear.triggered.connect(lambda: (recent.clear(), _fill_ask_menu(menu, window)))


def _build_tray(controller: Controller, window: ChatWindow) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(load_icon())
    tray.setToolTip("JARVIS — Desktop Assistant")

    menu = QMenu()

    # ---- Live status strip -------------------------------------------------
    status_act = menu.addAction("● ONLINE")
    status_act.setFont(QFont("Menlo", 11))
    status_act.triggered.connect(lambda: _show_window(window))

    def _update_status() -> None:
        try:
            status_act.setText(app_status.status_line())
        except Exception:
            pass

    _update_status()
    timer = QTimer(tray)
    timer.setInterval(4000)
    timer.timeout.connect(_update_status)
    timer.start()

    menu.addSeparator()

    # ---- Quick actions ------------------------------------------------------
    act_open = menu.addAction("Open JARVIS")
    act_open.triggered.connect(lambda: _show_window(window))

    act_camera = menu.addAction("Open Camera")
    act_camera.triggered.connect(lambda: window._open_camera())

    act_hud = menu.addAction("HUD Preview")
    act_hud.triggered.connect(lambda: controller.launch_hud(preview=True))

    act_settings = menu.addAction("Settings…")
    act_settings.triggered.connect(lambda: window._open_settings())

    voice_menu = menu.addMenu("Voice ▸")
    act_v1 = voice_menu.addAction("One command")
    act_v1.triggered.connect(lambda: controller.voice.start(VOICE_MODES["once"]))
    act_v2 = voice_menu.addAction("Conversational")
    act_v2.triggered.connect(lambda: controller.voice.start(VOICE_MODES["conversational"]))
    act_v3 = voice_menu.addAction("Wake word (say “JARVIS”)")
    act_v3.triggered.connect(lambda: controller.voice.start(VOICE_MODES["wake"]))
    act_vstop = voice_menu.addAction("Stop voice")
    act_vstop.triggered.connect(controller.voice.stop)

    menu.addSeparator()

    # ---- ASK: recent commands -----------------------------------------------
    ask_menu = menu.addMenu("ASK ▸")
    ask_menu.aboutToShow.connect(lambda: _fill_ask_menu(ask_menu, window))
    _fill_ask_menu(ask_menu, window)

    menu.addSeparator()

    act_quit = menu.addAction("Quit JARVIS")
    act_quit.triggered.connect(controller.quit)

    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: _show_window(window) if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
    return tray


def run() -> int:
    _install_excepthook()
    app = QApplication(sys.argv)
    app.setApplicationName("JARVIS")
    app.setApplicationDisplayName("JARVIS")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(load_icon())

    controller = Controller()
    window = ChatWindow(controller)
    tray = _build_tray(controller, window)
    tray.show()

    if "--hidden" not in sys.argv:
        _show_window(window)

    return app.exec()
