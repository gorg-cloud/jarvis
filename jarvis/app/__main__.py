"""
jarvis/app/__main__.py
Entry point for `python -m jarvis.app` and for the packaged JARVIS.app
(PyInstaller). Also acts as a subprocess re-entry point for the HUD in the
bundled app, where `python -m jarvis.hud.app` is not available.
"""
import sys


def main() -> None:
    # Packaged-app subprocess re-entry: JARVIS.app --hud [--preview]
    if "--hud" in sys.argv:
        from jarvis.hud.app import HUDApp
        app, win = HUDApp.launch(preview="--preview" in sys.argv)
        sys.exit(app.exec())

    # Packaged-app subprocess re-entry: JARVIS.app --menu
    if "--menu" in sys.argv:
        from jarvis.menu import run as run_menu
        sys.exit(run_menu())

    # Packaged-app subprocess re-entry: JARVIS.app --gestures
    if "--gestures" in sys.argv:
        from jarvis.camera.window import run as run_gestures
        sys.exit(run_gestures())

    # Diagnostic: what can this process do without Accessibility?
    if "--gesture-selftest" in sys.argv:
        from jarvis.camera.selftest import run as run_selftest
        sys.exit(run_selftest())

    from jarvis.app.main import run
    sys.exit(run())


if __name__ == "__main__":
    main()
