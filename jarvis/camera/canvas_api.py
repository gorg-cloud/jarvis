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


def add_image_url(url: str = "") -> dict:
    """Download an image from the internet and pin it to the canvas."""
    import os
    import tempfile
    import urllib.request
    if not url:
        return {"error": "no url given"}
    path = ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh)"})
        data = urllib.request.urlopen(req, timeout=15).read()
        with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as f:
            f.write(data)
            path = f.name
        pm = QPixmap(path)
        if pm.isNull():
            return {"error": "the downloaded file is not a usable image"}
        c = _canvas()
        c.add_image_item(pm)
        return {"status": f"pinned image from the web: {url}"}
    except Exception as exc:
        return {"error": f"could not download image: {exc}"}
    finally:
        if path:
            try:
                os.unlink(path)
            except Exception:
                pass


def add_plan(title: str = "", steps=None) -> dict:
    """Lay out a titled plan as a card on the canvas: title + numbered steps."""
    c = _canvas()
    c.add_plan_item(title, steps or [])
    return {"status": f"plan laid out on the canvas: {title}"}


def add_schedule(title: str = "", events=None) -> dict:
    """Lay out an Excel-style schedule table. `events` is a list of rows,
    e.g. [{"time": "09:00", "event": "Standup"}, ...]. Column headers are
    derived from the first row's keys (time gets its own column)."""
    c = _canvas()
    rows, columns = [], []
    for ev in (events or []):
        if isinstance(ev, dict):
            rows.append([str(v) for v in ev.values()])
        else:
            rows.append([str(ev)])
    if events and isinstance(events[0], dict):
        keys = list(events[0].keys())
        # Put a time column first when present.
        if "time" in keys and keys[0] != "time":
            keys = ["time"] + [k for k in keys if k != "time"]
        columns = [str(k).upper() for k in keys]
    elif rows:
        columns = (["TIME", "EVENT"] if len(rows[0]) >= 2 else ["TIME"])[:len(rows[0])]
    c.add_schedule_item(title, columns, rows)
    return {"status": f"schedule table added to the canvas: {title}"}


def add_flowchart(title: str = "", steps=None) -> dict:
    """Lay out a flowchart: title + step boxes connected by arrows."""
    c = _canvas()
    c.add_flow_item(title, steps or [])
    return {"status": f"flowchart added to the canvas: {title}"}


def zoom(factor: float = 1.25) -> dict:
    """Zoom the canvas view (factor > 1 zooms in, < 1 zooms out)."""
    c = _canvas()
    c.zoom_at(float(factor))
    return {"status": f"canvas zoomed {factor}x"}


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
