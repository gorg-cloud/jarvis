# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for JARVIS.app (macOS).

Build from the PROJECT ROOT (the folder containing the `jarvis` package):
    ../.venv/bin/python -m PyInstaller --noconfirm --clean jarvis/app.spec

or just run ./jarvis/build_app.sh
"""
import os

from PyInstaller.utils.hooks import collect_all

# SPECPATH = the `jarvis` package dir; PKG = project root (parent).
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

# --- jarvis modules loaded dynamically (uvicorn import strings, subprocess re-entry)
hiddenimports += ["jarvis.hud.server", "jarvis.camera"]

# --- Third-party packages: bundle data/binaries + hidden imports -----------
# (PyQt6 and PyAudio are handled by PyInstaller's built-in hooks.)
for _pkg in (
    "fastapi", "starlette", "uvicorn", "pydantic", "websockets",
    "dotenv", "httpx", "requests", "speech_recognition", "notion_client",
    "pyaudio", "cv2", "mediapipe", "matplotlib", "AVFoundation", "ApplicationServices",
    "Vision", "Foundation",
):
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception as _exc:  # noqa: BLE001 — optional dep
        print(f"note: could not collect '{_pkg}' ({_exc}); continuing")

# --- Bundle -----------------------------------------------------------------
a = Analysis(
    [os.path.join(SPECPATH, "app", "__main__.py")],
    pathex=[PKG],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "notebook", "IPython"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="JARVIS",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="JARVIS",
)

app = BUNDLE(
    coll,
    name="JARVIS.app",
    icon=os.path.join(SPECPATH, "app", "icon.icns"),
    bundle_identifier="com.jarvis.assistant",
    info_plist={
        "CFBundleName": "JARVIS",
        "CFBundleDisplayName": "JARVIS",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        # Privacy / TCC usage descriptions — required for prompts to appear.
        "NSMicrophoneUsageDescription": "JARVIS uses the microphone for voice commands.",
        "NSSpeechRecognitionUsageDescription": "JARVIS uses speech recognition to transcribe voice commands.",
        "NSAppleEventsUsageDescription": "JARVIS controls apps like Obsidian, Spotify and System Settings via AppleScript.",
        "NSScreenCaptureUsageDescription": "JARVIS can capture the screen to answer questions about what you are looking at.",
        "NSAccessibilityUsageDescription": "JARVIS reads the frontmost app and selected text to assist with context.",
        "NSCameraUsageDescription": "JARVIS uses the camera for gesture control (move the mouse with your finger, pinch to click).",
    },
)
