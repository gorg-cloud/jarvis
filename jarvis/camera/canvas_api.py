"""
jarvis/camera/canvas_api.py
Bridge between the LLM tool dispatcher and the live PROJECT canvas.

When the Mode 3 canvas is open, its JARVIS panel runs JarvisWorker in the
SAME process as the canvas, so the dispatcher tools below mutate it directly:
    - "add a note saying X"  -> canvas.add_text
    - "pin this picture"      -> canvas.add_image
    - "remove that"           -> canvas.remove_last
    - "clear the canvas"      -> canvas.clear

In the chat app process (no canvas open) they answer with a friendly error.
"""
from PyQt6.QtGui import QPixmap

_target = None


def set_target(canvas) -> None:
    """Register the live canvas (called when Mode 3 opens)."""
    global _target
    _target = canvas


def clear_target() -> None:
    """Unregister the canvas (called when Mode 3 closes)."""
    global _target
    _target = None


def _canvas():
    if _target is None:
        raise ValueError(
            "The PROJECT canvas isn't open. Say 'start a new project' to open it first."
        )
    return _target


def add_text(text: str = "") -> dict:
    """Drop a typed note onto the canvas."""
    c = _canvas()
    c.add_text_item(str(text))
    return {"status": f"added note to the canvas: {text}"}


def add_image(path: str = "") -> dict:
    """Pin an image file onto the canvas."""
    if not path:
        return {"error": "no image path given"}
    c = _canvas()
    pm = QPixmap(path)
    if pm.isNull():
        return {"error": f"could not load image: {path}"}
    c.add_image_item(pm)
    return {"status": f"added image to the canvas: {path}"}


def remove_last() -> dict:
    """Remove the most recently added element (note, image or stroke)."""
    c = _canvas()
    removed = c.remove_last_item()
    return {"status": "removed the last element"} if removed else {"status": "the canvas is empty"}


def clear_canvas() -> dict:
    """Wipe everything off the canvas."""
    c = _canvas()
    c.clear()
    return {"status": "canvas cleared"}
