"""
jarvis/app/prefs.py
Tiny JSON settings store at ~/.jarvis/prefs.json (always-on-top, etc.).
"""
import json
import os

_PATH = os.path.expanduser("~/.jarvis/prefs.json")


def _load() -> dict:
    try:
        with open(_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get(key: str, default=None):
    return _load().get(key, default)


def set_(key: str, value) -> None:
    data = _load()
    data[key] = value
    try:
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass
