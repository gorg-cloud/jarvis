"""
jarvis/engine/speaker.py
TTS abstraction. Switches between macOS `say` (default) and ElevenLabs / Piper.
Config: env TTS_ENGINE = 'say' | 'elevenlabs' | 'piper'.
"""
import os
import subprocess
import tempfile
import urllib.request
import urllib.parse
import json


TTS_ENGINE = os.getenv("TTS_ENGINE", "say").lower()

# Preferred British English voices, in order. `say -v '?'` lists what's
# installed; Daniel is the classic en-GB male voice.
_UK_VOICES = ["Daniel", "Kate", "Serena", "Arthur", "Martha", "Oliver"]
_british_voice_cache = None


def _british_voice() -> str:
    """Return the first installed British voice (cached), or '' for default."""
    global _british_voice_cache
    if _british_voice_cache is not None:
        return _british_voice_cache
    picked = ""
    try:
        r = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=8)
        available = r.stdout or ""
        for voice in _UK_VOICES:
            if voice in available:
                picked = voice
                break
    except Exception:
        pass
    _british_voice_cache = picked
    return picked


def _say(text: str, voice: str = "") -> None:
    """macOS native `say`."""
    cmd = ["say"]
    if voice:
        cmd += ["-v", voice]
    cmd.append(text)
    try:
        subprocess.run(cmd, check=True)
    except Exception as e:
        print(f"⚠️ say failed: {e}")


def _elevenlabs(text: str) -> None:
    """
    ElevenLabs TTS. Requires ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID.
    Plays via afplay.
    """
    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    if not api_key:
        print("⚠️ ElevenLabs TTS needs ELEVENLABS_API_KEY. Falling back to `say`.")
        return _say(text)

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    payload = json.dumps({
        "text": text[:2500],
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "accept": "audio/mpeg",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            audio = resp.read()
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio)
            path = f.name
        subprocess.run(["afplay", path], check=True)
        os.unlink(path)
    except Exception as e:
        print(f"⚠️ ElevenLabs TTS failed: {e}; falling back to `say`.")
        _say(text)


# Default local Piper voice (auto-downloaded into ~/.jarvis/piper).
# Natural, offline, human-sounding neural TTS — a big step up from `say`.
_PIPER_DEFAULT_MODEL = os.path.expanduser("~/.jarvis/piper/en_GB-alan-medium.onnx")


def _piper_bin() -> str:
    """Locate the piper CLI: env override, then common install spots."""
    env = os.getenv("PIPER_BIN")
    if env:
        return env
    import shutil
    for cand in (
        os.path.expanduser("~/.jarvis/piper/piper"),
        "/usr/local/bin/piper",
        "/opt/homebrew/bin/piper",
    ):
        if os.path.exists(cand):
            return cand
    p = shutil.which("piper")
    return p or ""


def _piper(text: str) -> None:
    """
    Piper TTS (local neural TTS) — the human-sounding default.
    Needs a piper CLI (PIPER_BIN, auto-detected) + a voice model
    (PIPER_MODEL, defaults to the downloaded British voice).
    """
    bin_path = _piper_bin()
    model_path = os.getenv("PIPER_MODEL") or _PIPER_DEFAULT_MODEL
    if not bin_path or not os.path.exists(model_path):
        print(f"⚠️ Piper TTS needs a piper binary + model. Falling back to `say`.")
        return _say(text)
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            out_path = f.name
        subprocess.run(
            [bin_path, "-m", model_path, "-f", out_path],
            input=text[:1000], text=True, check=True, timeout=60,
        )
        subprocess.run(["afplay", out_path], check=True)
        os.unlink(out_path)
    except Exception as e:
        print(f"⚠️ Piper TTS failed: {e}; falling back to `say`.")
        _say(text)


def speak(text: str) -> None:
    """Speak the given text using the configured TTS engine."""
    text = (text or "").strip()
    if not text:
        return
    if TTS_ENGINE == "elevenlabs":
        _elevenlabs(text)
    elif TTS_ENGINE == "piper":
        _piper(text)
    else:
        # Default to a British voice unless SAY_VOICE is set explicitly.
        voice = os.getenv("SAY_VOICE") or _british_voice()
        _say(text, voice=voice)
