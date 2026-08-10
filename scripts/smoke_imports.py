"""Cross-platform import smoke test (run by CI, works on macOS/Linux/Windows).

Verifies every module that must load on all platforms imports cleanly.
"""
import sys

sys.path.insert(0, ".")


def main() -> int:
    mods = [
        "jarvis.platform",
        "jarvis.camera.window",
        "jarvis.camera.selftest",
        "jarvis.camera.project",
        "jarvis.engine.speaker",
        "jarvis.voice",
        "jarvis.menu",
        "jarvis.tools.obsidian_tool",
        "jarvis.tools.spotify_tool",
        "jarvis.tools.calendar_tool",
        "jarvis.tools.system_tools",
        "jarvis.tools.files_tool",
        "jarvis.tools.notify_tool",
        "jarvis.tools.system_extras",
        "jarvis.tools.focus_tool",
        "jarvis.tools.clipboard_tool",
        "jarvis.tools.context_tool",
        "jarvis.tools.mail_tool",
        "jarvis.tools.contacts_tools",
        "jarvis.tools.mac_apps",
        "jarvis.tools.alarms_tool",
        "jarvis.tools.findmy_tool",
        "jarvis.tools.app_position_tool",
        "jarvis.tools.reminders_tool",
        "jarvis.app.main",
    ]
    failed = []
    for name in mods:
        try:
            __import__(name)
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{name}: {type(exc).__name__}: {exc}")
    if failed:
        print("IMPORT FAILURES:")
        for f in failed:
            print("  ", f)
        return 1
    print(f"ALL IMPORTS OK on {sys.platform} ({len(mods)} modules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
