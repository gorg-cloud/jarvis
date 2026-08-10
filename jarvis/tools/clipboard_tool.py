"""
jarvis/tools/clipboard_tool.py
macOS pasteboard read/write via pbcopy/pbpaste.
"""
import subprocess


def read_clipboard() -> dict:
    """Return current clipboard contents (text)."""
    try:
        out = subprocess.run(
            ["pbpaste", "-Prefer", "txt"],
            capture_output=True, text=True, check=True, timeout=5
        )
        text = out.stdout
        return {
            "text": text,
            "length": len(text),
            "empty": len(text.strip()) == 0,
        }
    except subprocess.CalledProcessError as e:
        return {"error": e.stderr.strip() or "pbpaste failed"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def write_clipboard(text: str) -> dict:
    """Write text to the clipboard."""
    try:
        subprocess.run(
            ["pbcopy"],
            input=text, text=True, check=True, timeout=5
        )
        return {"length": len(text), "status": "copied"}
    except subprocess.CalledProcessError as e:
        return {"error": e.stderr.strip() or "pbcopy failed"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
