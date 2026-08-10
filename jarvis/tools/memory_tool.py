"""
jarvis/tools/memory_tool.py
JARVIS's personal memory — stored as a note in the user's Obsidian vault
(JARVIS/Memory.md). Every conversation turn also injects a cached summary
of this note into the prompt, so JARVIS remembers facts about the user.

Tools:
  - memory.remember {fact}      — append a dated fact
  - memory.recall {}            — read the whole memory note
  - memory.forget {fact}        — remove lines mentioning a fact
"""
import datetime
import time

from .obsidian_tool import _pick_vault, _resolve_rel, append_note, read_note

MEMORY_PATH = "JARVIS/Memory"

# Cache the summary so we don't hit the vault on every single turn.
_cache = {"ts": 0.0, "text": ""}
_CACHE_TTL = 30.0
_MAX_SUMMARY_CHARS = 2500


def remember(fact: str, vault: str = "") -> dict:
    """Append a dated fact to the JARVIS Memory note (creates it if missing)."""
    fact = (fact or "").strip()
    if not fact:
        return {"error": "Nothing to remember."}
    entry = f"- {datetime.date.today().isoformat()}: {fact}"
    result = append_note(MEMORY_PATH, entry, vault=vault)
    if result.get("status"):
        result["status"] = "remembered"
        _cache["ts"] = 0.0  # invalidate cache
    return result


def recall(vault: str = "") -> dict:
    """Read the entire memory note."""
    return read_note(MEMORY_PATH, vault=vault)


def forget(fact: str, vault: str = "") -> dict:
    """Remove every line of the memory note mentioning `fact`."""
    fact = (fact or "").strip().lower()
    if not fact:
        return {"error": "Nothing to forget."}
    pick = _pick_vault(vault)
    if not pick["ok"]:
        return pick
    target = _resolve_rel(pick["path"], MEMORY_PATH)
    if target is None or not target.is_file():
        return {"error": "No memory note found."}
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    keep = [line for line in lines if fact not in line.lower()]
    removed = len(lines) - len(keep)
    if removed == 0:
        return {"status": "nothing_matching"}
    target.write_text("\n".join(keep), encoding="utf-8")
    _cache["ts"] = 0.0
    return {"status": "forgotten", "removed_lines": removed}


def load_memory_summary() -> str:
    """Return the cached memory text for prompt injection ('' if unavailable)."""
    now = time.time()
    if now - _cache["ts"] < _CACHE_TTL and _cache["text"] is not None:
        return _cache["text"]
    try:
        result = read_note(MEMORY_PATH)
        text = result.get("content", "") if result.get("status") else ""
        _cache["text"] = text[:_MAX_SUMMARY_CHARS]
    except Exception:
        _cache["text"] = ""
    _cache["ts"] = now
    return _cache["text"]
