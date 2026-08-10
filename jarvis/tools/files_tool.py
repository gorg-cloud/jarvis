"""
jarvis/tools/files_tool.py
Spotlight-based file finder + opener.
"""
import subprocess
from datetime import datetime, timedelta


def find_files(query: str, limit: int = 10) -> dict:
    """Spotlight search by name."""
    try:
        r = subprocess.run(
            ["mdfind", "-name", query],
            capture_output=True, text=True, timeout=10
        )
        paths = [p for p in r.stdout.splitlines() if p.strip()][:limit]
        return {
            "query": query,
            "count": len(paths),
            "files": [{"path": p, "name": p.rsplit("/", 1)[-1]} for p in paths],
        }
    except Exception as e:
        return {"query": query, "error": f"{type(e).__name__}: {e}"}


def recent_files(kind: str = "", hours: int = 24, limit: int = 10) -> dict:
    """
    Recently modified files. Optional kind: 'pdf', 'image', 'doc', etc.
    """
    since = datetime.now() - timedelta(hours=hours)
    since_str = since.strftime("%Y-%m-%d")
    query = f"kMDItemFSContentChangeDate >= $time.iso({since_str})"
    if kind:
        kind_map = {
            "pdf": "kMDItemContentType == 'com.adobe.pdf'",
            "image": "kMDItemContentTypeTree == 'public.image'",
            "doc": "kMDItemContentTypeTree == 'public.text'",
            "audio": "kMDItemContentTypeTree == 'public.audio'",
            "video": "kMDItemContentTypeTree == 'public.movie'",
        }
        if kind in kind_map:
            query += " && " + kind_map[kind]
    try:
        r = subprocess.run(
            ["mdfind", query],
            capture_output=True, text=True, timeout=15
        )
        paths = [p for p in r.stdout.splitlines() if p.strip()][:limit]
        return {
            "hours": hours,
            "kind": kind or "any",
            "count": len(paths),
            "files": [{"path": p, "name": p.rsplit("/", 1)[-1]} for p in paths],
        }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def open_file(path: str) -> dict:
    """Open a file with its default app."""
    import os
    if not os.path.exists(path):
        return {"path": path, "error": "file not found"}
    try:
        subprocess.run(["open", path], check=True, capture_output=True, timeout=10)
        return {"path": path, "status": "opened"}
    except Exception as e:
        return {"path": path, "error": str(e)}
