# 🦾 JARVIS — A macOS AI Butler

> *"At your service, sir."*

JARVIS is a personal AI assistant for macOS that talks, listens, watches, remembers, and runs your machine — a Stark-Industries-style desktop companion built as a native Mac app (PyQt6 + PyInstaller).

This project was built **with AI assistance** — most of the code was written by [Codebuff](https://codebuff.com), an AI pair programmer, in close collaboration with its human operator. That's not a secret we're hiding; it's the entire point of the project. Every feature below was designed together, then implemented and debugged with the AI.

---

## ✨ What it does

### 💬 Chat that feels alive
- Full chat window with the **menu bar** (voice, camera, HUD, settings) and a **tray menu** with a live status strip: `● ONLINE · 100% ⚡ · 21:47 · ♪ Moonlight o…` — battery, clock, and your current Spotify track, refreshing every few seconds
- **ASK ▸** menu remembers your last 8 commands — one click re-sends anything, even from the tray
- ⌘-shortcuts for everything: `⌘1` camera · `⌘2` HUD · `⌘3` voice · `⌘,` settings

### 🗣 A voice that doesn't sound like a robot
- **Piper** — local neural text-to-speech with a British male voice (`en_GB-alan-medium`), fully offline. No more robotic macOS `say` voices
- ElevenLabs supported if you add a key; `say` as a fallback
- Speech-to-text via Google or Whisper — talk to JARVIS and he talks back

### 🧠 A brain that never goes down
- **OpenRouter** cloud models, with **automatic multi-key failover**: add `GEMINI_API_KEY="key1,key2,key3"` (or `GEMINI_API_KEY_2`, `_3`, …) and when a key hits quota or rate-limits, it's quarantined for 5 minutes and the next key takes over — mid-conversation, no errors shown to you
- **Ollama fallback**: when every cloud key is exhausted, JARVIS drops to a local model (`ornith:latest`) — free, private, unlimited. `OLLAMA_FIRST=true` flips the priority

### 📷 Camera modes (hand tracking via MediaPipe)
The camera is the Iron Man part — your hands are the interface:

| Mode | What you can do |
|------|-----------------|
| **1 · CURSOR** | Your index finger moves the mouse; **pinch = click**, thumb+middle = right-click. Hand-size-normalized pinch with hold-to-confirm so it's precise at any distance. **Peace sign held 3s = close app**, **fist swipe = switch desktops** |
| **2 · WHITEBOARD** | **Pinch to write** — draw on a canvas with your finger, pick marker color (`1`–`6` keys) and size, and JARVIS **auto-converts your handwriting to text** (Apple Vision OCR) in a whiteboard font. 💾 Save to Obsidian |
| **3 · PROJECT** | *(in progress)* The animated holo-canvas — a synthwave grid workspace with the JARVIS rail on the side and a Spotify chip. See below |

Both camera modes have a live settings panel (speed, smoothing, pinch sensitivity) and an anti-shake pipeline (moving-average smoothing + dead zone).

### 📝 Actually remembers things (Obsidian)
- Writes to your **Obsidian vault** — whiteboards, project notes, and memory notes land in `Vault / JARVIS / …` as real Markdown
- Auto-discovers the active vault via Obsidian's registry

### 🛠 A full toolbox
Calendar, reminders, alarms, weather, email, contacts, files, clipboard, shell, web search, translation, Spotify control, Notion, Find My, notifications, focus mode, app launching, system status, news briefings, and more — all callable through natural language.

---

## 🚀 Getting started

```bash
# 1. Clone
git clone https://github.com/gorg-cloud/jarvis.git
cd jarvis

# 2. Python 3.9+ environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env      # add your OpenRouter key(s) at minimum

# 4. (Optional) Hand tracking model
#    Place MediaPipe hand_landmarker.task in jarvis/camera/

# 5. Run
./jarvis/run_app.sh       # or: python -m jarvis.main
```

Requires macOS. Ollama (for the local fallback) at [ollama.com](https://ollama.com). Piper voices (optional, for the neural voice) go in `~/.jarvis/piper/`.

## 🔨 Building the .app

```bash
# From the repo root:
.venv/bin/python -m PyInstaller --noconfirm jarvis/jarvis-app.spec
# Result: dist/JARVIS.app — drag to /Applications
```

`build_app.sh` wraps this with codesigning using your identity.

## 📂 Layout

```
jarvis/
├── app/          # chat window, tray menu, worker, status/recents/prefs
├── camera/       # hand tracking, gesture engine, cursor & whiteboard modes
├── engine/       # speaker (TTS), STT, keyring (API failover), Ollama provider
├── tools/        # 30+ tools: obsidian, spotify, calendar, shell, vision, …
├── hud/          # heads-up display
├── main.py       # entry point
├── config.py     # all configuration
└── jarvis-app.spec
```

## ⚙️ Configuration

See [`.env.example`](.env.example) for every knob: provider keys, voice engine, Ollama settings, integrations, and more.

## 🗺 Roadmap

- **MODE 3 · PROJECT** — the holo-canvas: an animated synthwave grid workspace you control with your hands. Say *"JARVIS, start a new project"* and a canvas opens with JARVIS on the side (voice + text), a Spotify chip, and hand-drawn notes that OCR into project notes in Obsidian
- Air gestures → command dispatch (draw a circle = open menu)
- Presenter mode (hand as laser pointer)

## 📜 License

Personal project — use it, learn from it, remix it. No warranty, and JARVIS may or may not save you from falling off a cliff.
