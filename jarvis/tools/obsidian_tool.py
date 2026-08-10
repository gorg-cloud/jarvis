"""
jarvis/tools/obsidian_tool.py
Obsidian vault integration for JARVIS.

Works with a local vault on this Mac — no plugin required:
  - vault discovery: reads Obsidian's registry
    (~/Library/Application Support/obsidian/obsidian.json)
  - read / search / append: direct filesystem access (vaults are just folders)
  - create / open: writes the .md file directly, then optionally opens it in
    the Obsidian app via the obsidian:// URI scheme

Config (optional, see config.py / .env):
  OBSIDIAN_VAULT       — default vault name used when none is given
  OBSIDIAN_VAULT_PATH  — direct path to a vault folder (bypasses discovery)
"""
import json
import os
import subprocess
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional

from ..config import OBSIDIAN_VAULT, OBSIDIAN_VAULT_PATH

_MAX_READ_CHARS = 50_000
_SKIP_DIRS = {".obsidian", ".trash", ".git", "node_modules"}


# ----------------------------------------------------------------------
# Vault discovery
# ----------------------------------------------------------------------

def _registry_path() -> Path:
    return Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"


def list_vaults() -> dict:
    """Return every local Obsidian vault: [{name, path, id?}]. Ordered by name."""
    if OBSIDIAN_VAULT_PATH:
        p = Path(OBSIDIAN_VAULT_PATH).expanduser()
        if p.is_dir():
            return {"vaults": [{"name": p.name, "path": str(p), "source": "env"}]}
        return {"vaults": [], "error": f"OBSIDIAN_VAULT_PATH not found: {p}"}

    reg = _registry_path()
    if not reg.exists():
        return {
            "vaults": [],
            "error": (
                "Obsidian vault registry not found. Open Obsidian once so it can "
                "register your vaults, or set OBSIDIAN_VAULT_PATH to the vault folder."
            ),
        }

    try:
        data = json.loads(reg.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"vaults": [], "error": f"Could not parse {reg}: {exc}"}

    vaults: List[Dict[str, str]] = []
    for vid, info in (data.get("vaults") or {}).items():
        vpath = (info or {}).get("path")
        if not vpath:
            continue
        p = Path(vpath)
        if not p.is_dir():
            continue
        vaults.append({"name": p.name, "path": str(p), "id": vid})

    vaults.sort(key=lambda v: v["name"].lower())
    return {"vaults": vaults}


def _pick_vault(vault: str = "") -> dict:
    """
    Resolve a vault by name/id (or the configured default, or the only vault).
    Returns {"ok": True, "name": ..., "path": Path} or an error dict.
    """
    if OBSIDIAN_VAULT_PATH:
        p = Path(OBSIDIAN_VAULT_PATH).expanduser()
        if p.is_dir():
            return {"ok": True, "name": p.name, "path": p.resolve()}
        return {"ok": False, "error": f"OBSIDIAN_VAULT_PATH not found: {p}"}

    result = list_vaults()
    vaults = result.get("vaults", [])
    if result.get("error") and not vaults:
        return {"ok": False, "error": result["error"]}

    target = vault or OBSIDIAN_VAULT or ""
    if target:
        for v in vaults:
            if v["name"].lower() == target.lower() or v.get("id") == target:
                return {"ok": True, "name": v["name"], "path": Path(v["path"]).resolve()}
        return {
            "ok": False,
            "error": f"Vault '{target}' not found. Available: {[v['name'] for v in vaults]}",
        }

    if len(vaults) == 1:
        return {"ok": True, "name": vaults[0]["name"], "path": Path(vaults[0]["path"]).resolve()}

    return {
        "ok": False,
        "error": (
            f"{len(vaults)} vaults found — please specify one: {[v['name'] for v in vaults]}"
        ),
    }


# ----------------------------------------------------------------------
# Path helpers (vault-relative, traversal-safe)
# ----------------------------------------------------------------------

def _resolve_rel(vault_path: Path, rel: str) -> Optional[Path]:
    """Resolve a vault-relative note path. Accepts 'Notes/Foo' or 'Notes/Foo.md'.
    Returns None if the path escapes the vault."""
    rel = rel.strip().lstrip("/")
    if not rel:
        return None
    if not rel.endswith(".md"):
        rel = rel + ".md"
    candidate = (vault_path / rel).resolve()
    try:
        candidate.relative_to(vault_path)
    except ValueError:
        return None
    return candidate


def _rel_from_abs(vault_path: Path, abs_path: Path) -> str:
    return str(abs_path.relative_to(vault_path)).removesuffix(".md")


def _open_obsidian_uri(vault_name: str, action: str, params: Dict[str, str]) -> dict:
    """Open an obsidian:// URI with the OS `open` command."""
    query = urllib.parse.urlencode(params)
    uri = f"obsidian://{action}?{query}"
    try:
        subprocess.run(["open", uri], check=True, capture_output=True, timeout=10)
        return {"ok": True, "uri": uri}
    except Exception as exc:
        return {"ok": False, "error": f"Could not open Obsidian: {exc}", "uri": uri}


# ----------------------------------------------------------------------
# Public tool API (returns plain dicts for the dispatcher)
# ----------------------------------------------------------------------

def create_note(title: str, content: str = "", folder: str = "", vault: str = "", open_after: bool = False) -> dict:
    """
    Create a new markdown note in the vault. Writes the file directly so
    Obsidian picks it up instantly (it watches the vault folder).
    """
    pick = _pick_vault(vault)
    if not pick["ok"]:
        return pick

    title = (title or "").strip()
    if not title:
        return {"error": "A note title is required."}

    folder = (folder or "").strip().strip("/")
    rel = (folder + "/" + title) if folder else title
    target = _resolve_rel(pick["path"], rel)
    if target is None:
        return {"error": f"Invalid note path: {rel}"}
    if target.exists():
        return {"error": f"Note already exists: {_rel_from_abs(pick['path'], target)}"}

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content or "", encoding="utf-8")
    except Exception as exc:
        return {"error": f"Failed to write note: {exc}"}

    rel_name = _rel_from_abs(pick["path"], target)
    result = {
        "status": "created",
        "vault": pick["name"],
        "note": rel_name,
        "path": str(target),
        "characters": len(content or ""),
    }
    if open_after:
        opened = _open_obsidian_uri(pick["name"], "open", {"vault": pick["name"], "file": rel_name})
        result["opened"] = opened.get("ok", False)
    return result


def read_note(path: str, vault: str = "") -> dict:
    """Read a note's content as plain text (first 50k chars)."""
    pick = _pick_vault(vault)
    if not pick["ok"]:
        return pick

    target = _resolve_rel(pick["path"], path)
    if target is None:
        return {"error": f"Invalid note path: {path}"}
    if not target.is_file():
        return {"error": f"Note not found: {path}"}

    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return {"error": f"Failed to read note: {exc}"}

    truncated = len(text) > _MAX_READ_CHARS
    return {
        "status": "read",
        "vault": pick["name"],
        "note": _rel_from_abs(pick["path"], target),
        "content": text[:_MAX_READ_CHARS],
        "truncated": truncated,
    }


def append_note(path: str, content: str, vault: str = "") -> dict:
    """Append content to an existing note (or create it if missing)."""
    if not content:
        return {"error": "Nothing to append."}
    pick = _pick_vault(vault)
    if not pick["ok"]:
        return pick

    target = _resolve_rel(pick["path"], path)
    if target is None:
        return {"error": f"Invalid note path: {path}"}

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as f:
            if target.exists() and target.stat().st_size > 0:
                f.write("\n\n")
            f.write(content)
    except Exception as exc:
        return {"error": f"Failed to append to note: {exc}"}

    return {
        "status": "appended",
        "vault": pick["name"],
        "note": _rel_from_abs(pick["path"], target),
        "characters": len(content),
    }


def search_notes(query: str, vault: str = "", limit: int = 10) -> dict:
    """Case-insensitive full-text search across the vault's markdown notes."""
    if not query:
        return {"error": "A search query is required."}
    pick = _pick_vault(vault)
    if not pick["ok"]:
        return pick

    limit = max(1, min(int(limit or 10), 50))
    matches: List[Dict[str, str]] = []
    needle = query.lower()

    for md in pick["path"].rglob("*.md"):
        if any(part.startswith(".") or part in _SKIP_DIRS for part in md.parts[len(pick["path"].parts):]):
            continue
        try:
            with open(md, "r", encoding="utf-8", errors="replace") as f:
                head = f.read(64_000)
        except OSError:
            continue
        if needle not in head.lower():
            continue
        snippet = ""
        for line in head.splitlines():
            if needle in line.lower():
                snippet = line.strip()[:200]
                break
        matches.append({
            "note": _rel_from_abs(pick["path"], md),
            "path": str(md),
            "snippet": snippet,
        })
        if len(matches) >= limit:
            break

    return {
        "status": "searched",
        "vault": pick["name"],
        "query": query,
        "count": len(matches),
        "matches": matches,
    }


def open_note(path: str, vault: str = "") -> dict:
    """Open a note in the Obsidian app."""
    pick = _pick_vault(vault)
    if not pick["ok"]:
        return pick

    target = _resolve_rel(pick["path"], path)
    if target is None:
        return {"error": f"Invalid note path: {path}"}
    if not target.is_file():
        return {"error": f"Note not found: {path}"}

    rel_name = _rel_from_abs(pick["path"], target)
    opened = _open_obsidian_uri(pick["name"], "open", {"vault": pick["name"], "file": rel_name})
    if not opened["ok"]:
        return opened
    return {"status": "opened", "vault": pick["name"], "note": rel_name}


def open_vault(vault: str = "") -> dict:
    """Open a vault (or its search UI with a query) in Obsidian."""
    pick = _pick_vault(vault)
    if not pick["ok"]:
        return pick
    opened = _open_obsidian_uri(pick["name"], "open", {"vault": pick["name"]})
    if not opened["ok"]:
        return opened
    return {"status": "opened", "vault": pick["name"]}


def search_in_obsidian(query: str, vault: str = "") -> dict:
    """Open Obsidian's search panel pre-filled with the query (UI action)."""
    pick = _pick_vault(vault)
    if not pick["ok"]:
        return pick
    opened = _open_obsidian_uri(pick["name"], "search", {"vault": pick["name"], "query": query})
    if not opened["ok"]:
        return opened
    return {"status": "searching", "vault": pick["name"], "query": query}
