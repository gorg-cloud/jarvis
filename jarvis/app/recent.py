"""
jarvis/app/recent.py
Persisted recent commands for the ASK menu. Stored at ~/.jarvis/recent.json.
"""
import json
import os

_PATH = os.path.expanduser("~/.jarvis/recent.json")
MAX = 8


def load() -> list:
    try:
        with open(_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return [str(x) for x in data if str(x).strip()][:MAX]
    except Exception:
        return []


def add(command: str) -> None:
    """Record a command at the front, deduped, capped at MAX."""
    command = command.strip()
    if not command:
        return
    items = [x for x in load() if x != command]
    items.insert(0, command)
    items = items[:MAX]
    try:
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2)
    except Exception:
        pass


def clear() -> None:
    """Empty the recent-commands history."""
    try:
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)
    except Exception:
        pass
