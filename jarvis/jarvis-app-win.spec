# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for JARVIS.exe (Windows).

Build from the PROJECT ROOT (the folder containing the `jarvis` package):
    python -m PyInstaller --noconfirm --clean jarvis/jarvis-app-win.spec

or run scripts/build_windows.ps1
"""
import os

from PyInstaller.utils.hooks import collect_all

PKG = os.path.dirname(SPECPATH)

datas = []
binaries = []
hiddenimports = []

# --- Static assets the app serves at runtime -------------------------------
datas += [
    (os.path.join(SPECPATH, "hud", "web"), "jarvis/hud/web"),
    # MediaPipe hand-landmark model for gesture control
    (os.path.join(SPECPATH, "camera", "hand_landmarker.task"), "jarvis/camera"),
]

hiddenimports += ["jarvis.hud.server", "jarvis.camera"]

# --- Third-party packages: bundle data/binaries + hidden imports -----------
# (macOS-only pyobjc frameworks are deliberately NOT collected here.)
for _pkg in (
    "fastapi", "starlette", "uvicorn", "pydantic", "websockets",
    "dotenv", "httpx", "requests", "speech_recognition", "notion_client",
    "cv2", "mediapipe", "matplotlib",
):
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception as _exc:  # noqa: BLE001 — optional dep
        print(f"note: could not collect '{_pkg}' ({_exc}); continuing")

a = Analysis(
    [os.path.join(SPECPATH, "app", "__main__.py")],
    pathex=[PKG],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "notebook", "IPython", "AVFoundation", "ApplicationServices",
              "Vision", "Quartz", "Foundation", "PyObjCTools"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="JARVIS",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=os.path.join(SPECPATH, "app", "icon.ico"),
)
