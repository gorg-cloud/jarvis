"""
jarvis/app/make_icon.py
Renders the JARVIS "arc reactor" icon with QPainter — no image assets needed.

  - load_icon()      : QIcon for runtime use (dock + menu bar)
  - write_icon_png() : writes app/icon.png (1024px)
  - write_icns()     : builds app/icon.icns via `iconutil` (macOS, build time)

Run directly (from the project root, with a PyQt6-enabled python):
    python -m jarvis.app.make_icon --icns
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPixmap, QRadialGradient
from PyQt6.QtWidgets import QApplication

BG = QColor("#050507")
CYAN = QColor("#00f0ff")
CYAN_DIM = QColor(0, 240, 255, 60)

_APP = None


def _ensure_app() -> None:
    """QPixmap painting needs a QGuiApplication; create one when rendering
    outside the desktop app (e.g. the build step)."""
    global _APP
    if QApplication.instance() is None:
        _APP = QApplication(["jarvis-icon"])


def render_pixmap(size: int = 256) -> QPixmap:
    """Paint the JARVIS arc-reactor mark onto a square pixmap."""
    _ensure_app()
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    margin = size * 0.06
    rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)

    # Dark rounded-square body
    body = QLinearGradient(rect.topLeft(), rect.bottomRight())
    body.setColorAt(0.0, QColor("#10141c"))
    body.setColorAt(1.0, QColor("#06070b"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(body)
    p.drawRoundedRect(rect, size * 0.16, size * 0.16)

    # Cyan border ring
    ring = QRectF(rect.adjusted(size * 0.05, size * 0.05, -size * 0.05, -size * 0.05))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(CYAN_DIM)
    p.drawEllipse(ring)

    # Outer glow ring
    glow = QRadialGradient(rect.center(), rect.width() * 0.55)
    glow.setColorAt(0.0, QColor(0, 240, 255, 120))
    glow.setColorAt(1.0, QColor(0, 240, 255, 0))
    p.setBrush(glow)
    p.drawEllipse(rect.adjusted(size * 0.16, size * 0.16, -size * 0.16, -size * 0.16))

    # Thin arc (partially open ring) — the "reactor"
    arc = QRectF(rect.adjusted(size * 0.12, size * 0.12, -size * 0.12, -size * 0.12))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(CYAN)
    p.drawPie(arc, 16 * 30, 16 * 120)      # upper arc
    p.drawPie(arc, 16 * 210, 16 * 120)     # lower arc

    # Core dot
    core = QRectF(rect.center().x() - size * 0.08, rect.center().y() - size * 0.08,
                  size * 0.16, size * 0.16)
    core_glow = QRadialGradient(core.center(), core.width())
    core_glow.setColorAt(0.0, QColor("#ffffff"))
    core_glow.setColorAt(0.35, CYAN)
    core_glow.setColorAt(1.0, QColor(0, 240, 255, 0))
    p.setBrush(core_glow)
    p.drawEllipse(core)

    p.end()
    return pm


def load_icon() -> QIcon:
    """Runtime icon for dock/tray (rendered in-memory, no file needed)."""
    return QIcon(render_pixmap(256))


def write_icon_png(path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    render_pixmap(1024).save(str(path), "PNG")
    return path


def write_ico(out_path: Path) -> Path:
    """Build a Windows .ico from the rendered pixmap (multi-size PNG-ICO)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    source = render_pixmap(256)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = []
    for s in sizes:
        pm = source.scaled(s, s, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        from PyQt6.QtCore import QBuffer  # noqa: PLC0415
        qbuf = QBuffer()
        qbuf.open(QBuffer.OpenModeFlag.WriteOnly)
        pm.save(qbuf, "PNG")
        images.append((s, bytes(qbuf.data())))

    import struct  # noqa: PLC0415
    with open(out_path, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(images)))
        offset = 6 + 16 * len(images)
        for s, png in images:
            w = s if s < 256 else 0
            h = s if s < 256 else 0
            f.write(struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(png), offset))
            offset += len(png)
        for _, png in images:
            f.write(png)
    return out_path


def write_icns(out_path: Path, png_path: Path) -> Path:
    """Build a .icns from the 1024px PNG using an iconset + iconutil (macOS)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="jarvis-icon-"))
    iconset = tmp / "icon.iconset"
    iconset.mkdir()

    source = render_pixmap(1024)
    for size in (16, 32, 128, 256, 512):
        source.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation) \
            .save(str(iconset / f"icon_{size}x{size}.png"), "PNG")
        source.scaled(size * 2, size * 2, Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation) \
            .save(str(iconset / f"icon_{size}x{size}@2x.png"), "PNG")

    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(out_path)],
        check=True, capture_output=True,
    )
    shutil.rmtree(tmp, ignore_errors=True)
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate JARVIS app icons.")
    ap.add_argument("--icns", action="store_true", help="also build icon.icns (macOS)")
    ap.add_argument("--ico", action="store_true", help="also build icon.ico (Windows)")
    args = ap.parse_args()

    here = Path(__file__).resolve().parent
    png = write_icon_png(here / "icon.png")
    print(f"wrote {png}")
    if args.icns:
        icns = write_icns(here / "icon.icns", png)
        print(f"wrote {icns}")
    if args.ico:
        ico = write_ico(here / "icon.ico")
        print(f"wrote {ico}")


if __name__ == "__main__":
    main()
