"""
jarvis/voice.py
Voice loop for JARVIS. Supports three modes:
  1. --once          Single-shot, exits after one command (default for hotkey).
  2. --conversational  Keep mic open for follow-ups until silence/no-op.
  3. (default)       Wake-word "jarvis" triggered.

Configurable STT/TTS via env: STT_ENGINE, TTS_ENGINE.
"""
import os
import sys
import asyncio
import subprocess
import threading
from typing import Optional

import speech_recognition as sr

from .engine.stt import make_stt
from .engine.speaker import speak
from .main import process_user_input


# How many silent turns before exiting conversational mode
MAX_IDLE_TURNS = 2


def _beep(sound: str = "Tink") -> None:
    try:
        if os.name == "nt":
            import winsound  # noqa: PLC0415
            winsound.MessageBeep()
        else:
            subprocess.run(["afplay", f"/System/Library/Sounds/{sound}.aiff"], check=False)
    except Exception:
        pass


async def _handle_command(stt, command_text: str) -> dict:
    """Run user text through engine, speak reply, return reply dict."""
    reply = await process_user_input(command_text)
    message = reply.get("message")
    error = reply.get("error")
    logs = reply.get("logs", "")

    if error or "❌" in logs:
        speak("I encountered an error while executing that command, sir.")
    elif message:
        speak(message)
    elif "✅ No tool calls" in logs:
        speak("I didn't take any action on that.")
    else:
        speak("Done, sir.")
    return reply


def _listen_once(stt, microphone, phrase_time_limit: int = 30):
    """Listen + recognize once. Returns text or None on failure."""
    try:
        _beep("Tink")
        with microphone as source:
            print("🎙️  Listening...")
            audio = stt.listen(source, phrase_time_limit=phrase_time_limit)
        text = stt.recognize(audio)
        print(f"🗣️  You: {text}")
        return text
    except sr.UnknownValueError:
        return None
    except sr.WaitTimeoutError:
        return None
    except sr.RequestError as e:
        print(f"⚠️ STT network error: {e}")
        speak("I'm having trouble connecting to the speech service.")
        return None
    except Exception as e:
        print(f"⚠️ Listen error: {e}")
        return None


def _run_once_mode(stt, microphone, stop_event: Optional[threading.Event] = None) -> None:
    """Hotkey single-shot. Listens, replies, exits."""
    speak("Yes, sir?")
    fail_count = 0
    while fail_count < MAX_IDLE_TURNS + 1:
        if stop_event and stop_event.is_set():
            return
        text = _listen_once(stt, microphone, phrase_time_limit=30)
        if not text:
            fail_count += 1
            if fail_count >= 2:
                speak("I'm having trouble hearing you. Shutting down.")
                return
            speak("I didn't catch that, sir.")
            continue
        fail_count = 0

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            reply = loop.run_until_complete(_handle_command(stt, text))
        finally:
            loop.close()

        # Continue only if it was a question with no tool call (follow-up expected)
        message = reply.get("message", "")
        logs = reply.get("logs", "")
        if "✅ No tool calls" in logs and "?" in message:
            continue
        return


def _run_conversational(stt, microphone, stop_event: Optional[threading.Event] = None) -> None:
    """Always-listening conversational mode. No wake word needed."""
    speak("Jarvis is online. I'm listening.")
    idle_turns = 0
    while idle_turns < MAX_IDLE_TURNS + 2:
        if stop_event and stop_event.is_set():
            return
        text = _listen_once(stt, microphone, phrase_time_limit=30)
        if not text:
            idle_turns += 1
            continue
        idle_turns = 0
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_handle_command(stt, text))
        finally:
            loop.close()
    speak("Going quiet. Call me when you need me.")


def _run_wake_word(stt, microphone, stop_event: Optional[threading.Event] = None) -> None:
    """Wake word 'jarvis' triggers a command. Loops until stopped."""
    speak("Jarvis is online and listening.")
    while True:
        if stop_event and stop_event.is_set():
            speak("Stopping voice mode.")
            return
        try:
            with microphone as source:
                audio = stt.listen(source, phrase_time_limit=5)
            try:
                text = stt.recognize(audio).lower()
            except sr.UnknownValueError:
                continue
            except sr.RequestError as e:
                print(f"⚠️ STT network error: {e}")
                continue

            if "jarvis" in text:
                print("🎯 Wake word detected!")
                speak("Yes, sir?")
                cmd = _listen_once(stt, microphone, phrase_time_limit=30)
                if not cmd:
                    continue
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(_handle_command(stt, cmd))
                finally:
                    loop.close()
        except sr.WaitTimeoutError:
            pass
        except Exception as e:
            print(f"⚠️ Unexpected error: {e}")


def listen_loop(mode: Optional[str] = None, stop_event: Optional[threading.Event] = None) -> None:
    """Entry point. Picks mode based on argv flags, unless `mode` is given
    ('once' | 'conversational' | 'wake'). `stop_event` lets a host app
    (e.g. the desktop app) stop a long-running loop."""
    try:
        microphone = sr.Microphone()
    except OSError as e:
        print(f"❌ Microphone error: {e}")
        print("Grant mic permission in System Settings → Privacy & Security → Microphone.")
        return

    stt = make_stt()
    print(f"🎙️  JARVIS voice ready (STT={type(stt).__name__}, TTS={os.getenv('TTS_ENGINE', 'say')}).")

    if mode is None:
        conversational = "--conversational" in sys.argv or os.getenv("JARVIS_MODE") == "conversational"
        single_shot = "--once" in sys.argv or os.getenv("JARVIS_MODE") == "once"
    else:
        conversational = mode == "conversational"
        single_shot = mode == "once"

    if single_shot:
        _run_once_mode(stt, microphone, stop_event)
    elif conversational:
        _run_conversational(stt, microphone, stop_event)
    else:
        _run_wake_word(stt, microphone, stop_event)


if __name__ == "__main__":
    listen_loop()
