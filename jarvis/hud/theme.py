"""
jarvis/hud/theme.py
Stark Industries × Obsidian dark HUD palette.
"""
from PyQt6.QtGui import QColor, QFont

BG = QColor("#050507")
BG_PANEL = QColor("#0a0a0e")
BG_PANEL_BORDER = QColor("#00f0ff")
CYAN = QColor("#00f0ff")
CYAN_DIM = QColor("#00f0ff")
CYAN_ALPHA = QColor(0, 240, 255, 40)
WHITE = QColor("#e0e0e0")
WHITE_DIM = QColor("#888888")
TEXT_MONO = QFont("JetBrains Mono", 11)
TEXT_MONO.setFamily("JetBrains Mono")
TEXT_MONO_SMALL = QFont("JetBrains Mono", 9)
TEXT_MONO.setFamily("JetBrains Mono")
# Fallback monospace
FONT_FALLBACKS = [
    "JetBrains Mono", "Fira Code", "SF Mono",
    "Menlo", "Monaco", "Consolas", "monospace",
]


def mono(size: int = 11, bold: bool = False) -> QFont:
    f = QFont()
    for name in FONT_FALLBACKS:
        f.setFamily(name)
        if f.exactMatch():
            break
    f.setPointSize(size)
    f.setBold(bold)
    f.setStyleHint(QFont.StyleHint.Monospace)
    return f
