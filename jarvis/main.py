import asyncio
import json
import os
import datetime
from typing import List, Dict, Any
import urllib.request
import urllib.error

from .config import (
    MODEL_PROVIDER,
    GEMINI_MODEL,
    GEMINI_API_KEY,
    OLLAMA_FIRST,
)
from .engine.dispatcher import dispatch_calls
from .engine.keyring import GEMINI_RING, is_failover_error
from .engine import ollama
from .tools.memory_tool import load_memory_summary

# ----------------------------------------------------------------------
# LLM request helpers — OpenRouter (cloud) with multi-key failover, then
# Ollama (local) as the offline safety net. Built-in libs only.
# ----------------------------------------------------------------------

# JARVIS's strict output contract — every provider is forced to this shape
# (OpenRouter via response_format.json_schema, Ollama via format).
_JARVIS_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
        "calls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "args": {"type": "object"},
                },
                "required": ["name", "args"],
            },
        },
    },
    "required": ["message", "calls"],
}


def _call_openrouter(system_prompt: str, user_prompt: str) -> str:
    """Try the OpenRouter key pool, rotating to the next key on quota /
    rate-limit / auth errors (see engine.keyring)."""
    url = "https://openrouter.ai/api/v1/chat/completions"

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "No API key configured. Add GEMINI_API_KEY to ~/.jarvis/.env "
            "(multiple keys can be comma-separated for automatic failover)."
        )

    # Try each healthy key in turn; stop early if we run out of options.
    attempts = max(1, min(3, GEMINI_RING.count))
    for _attempt in range(attempts):
        key = GEMINI_RING.current()
        if not key:
            raise RuntimeError(
                f"All API keys are cooling down (quota/rate-limit). "
                f"{GEMINI_RING.status()} — retry in a few minutes."
            )

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": GEMINI_MODEL,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "jarvis_response",
                    "strict": True,
                    "schema": _JARVIS_SCHEMA,
                },
            },
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)

        try:
            with urllib.request.urlopen(req) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                GEMINI_RING.mark_ok(key)
                return res_data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            if is_failover_error(e.code, error_body):
                GEMINI_RING.mark_failed(key)
                print(f"⚠ API key {key[:8]}… failed ({e.code}) — trying next key")
                continue
            raise RuntimeError(f"OpenRouter API Error: {e.code} - {error_body}")
        except Exception as e:
            raise RuntimeError(f"Network error connecting to OpenRouter: {e}")

    raise RuntimeError(
        f"All API keys failed or are cooling down. {GEMINI_RING.status()}"
    )


def call_openrouter(system_prompt: str, user_prompt: str) -> str:
    """Ask JARVIS's brain. Provider chain:
      1. OpenRouter key pool (multi-key failover), then
      2. local Ollama as an automatic offline fallback.
    OLLAMA_FIRST=true flips the order (Ollama first, cloud keys as backup)."""
    errors: List[str] = []

    def _try_ollama():
        try:
            out = ollama.chat(system_prompt, user_prompt, schema=_JARVIS_SCHEMA)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Ollama: {exc}")
            return None
        if out:
            return out
        errors.append("Ollama: empty response")
        return None

    if OLLAMA_FIRST:
        out = _try_ollama()
        if out is not None:
            return out
        try:
            return _call_openrouter(system_prompt, user_prompt)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"OpenRouter: {exc}")
    else:
        try:
            return _call_openrouter(system_prompt, user_prompt)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"OpenRouter: {exc}")
        out = _try_ollama()
        if out is not None:
            return out

    raise RuntimeError("All providers failed — " + " | ".join(errors))

SYSTEM_INSTRUCTION = """
You are JARVIS, a sharp, professional AI assistant that controls the user's Mac. You speak with a refined British gentleman's manner — courteous, dry-witted, and a touch formal ("sir").
Respond ONLY with JSON of the form:
{
  "message": "The conversational reply to speak aloud (answer questions directly here)",
  "calls": [{"name": "tool_name", "args": { ... }}]
}

Available tools:
- "notion.add_task", {"title": "string"}
- "notion.list_tasks", {"limit": "int (default 20)"}
- "reminders.create", {"title": "string", "due": "string YYYY-MM-DD HH:MM:SS"}
- "alarms.create", {"time_str": "string HH:MM"}

Obsidian (second brain):
- "obsidian.create_note", {"title": "string", "content": "string (optional)", "folder": "string (optional, e.g. Inbox)", "vault": "string (optional, default from config)", "open_after": "boolean (optional)"}
- "obsidian.read_note", {"path": "string (vault-relative, e.g. Projects/Foo)", "vault": "string (optional)"}
- "obsidian.append_note", {"path": "string", "content": "string", "vault": "string (optional)"}
- "obsidian.search", {"query": "string", "vault": "string (optional)", "limit": "int (default 10)"} — full-text search, returns note paths
- "obsidian.open_note", {"path": "string", "vault": "string (optional)"} — open in the Obsidian app
- "obsidian.open_vault", {"vault": "string (optional)"}
- "obsidian.search_ui", {"query": "string", "vault": "string (optional)"} — open Obsidian search panel with a query
- "obsidian.list_vaults", {} — list discovered vaults; call this if no vault is given and you're unsure which to use

System control:
- "system.open_app", {"app_name": "string"}
- "system.open_url", {"url": "string"}
- "system.set_wifi", {"state": "boolean"}
- "system.set_bluetooth", {"state": "boolean"}
- "system.sleep", {}
- "system.screensaver", {}
- "system.set_volume", {"level": "int 0-100"}
- "system.get_volume", {}
- "system.mute", {}
- "system.unmute", {}
- "system.set_brightness", {"level": "float 0.0-1.0"}
- "system.toggle_dnd", {"state": "boolean"}
- "system.battery", {}
- "system.uptime", {}
- "system.start_timer", {"name": "string", "minutes": "float", "message": "string (optional)"}
- "system.list_timers", {}
- "system.notify", {"title": "string", "message": "string", "sound": "string (optional)"}

Apps & media:
- "apps.send_message", {"contact": "string (name or phone)", "message": "string"}
- "apps.music", {"action": "string (play, pause, next track, previous track)"}
- "apps.spotify", {"action": "string (play, pause, playpause, next, previous)"}
- "apps.spotify_status", {}

Contacts & calling:
- "contacts.search", {"query": "string", "limit": "int (default 10)"}
- "contacts.call", {"contact": "string (name, phone, or email)", "mode": "string (audio or video, default audio)"}

Email:
- "mail.draft", {"to": "string", "subject": "string", "body": "string", "send": "boolean (default false → save draft)"}
- "mail.unread_count", {}

Calendar:
- "calendar.next_events", {"limit": "int (default 5)"}
- "calendar.free_at", {"time_str": "string YYYY-MM-DD HH:MM"}

Clipboard:
- "clipboard.read", {}
- "clipboard.write", {"text": "string"}

Context (what user is looking at):
- "context.frontmost_app", {}
- "context.selected_text", {}
- "context.active", {}

Weather:
- "weather.current", {"location": "string (optional, empty = auto)"}
- "weather.forecast", {"location": "string (optional)", "hours": "int (default 6)"}

Vision:
- "vision.analyze_screen", {"question": "string (default: describe screen)"}
- "vision.screenshot", {"path": "string (optional)"}

Web:
- "web.search", {"query": "string", "limit": "int (default 5)"}
- "web.fetch", {"url": "string", "max_chars": "int (default 4000)"}

Files:
- "files.find", {"query": "string", "limit": "int (default 10)"}
- "files.recent", {"kind": "string (pdf, image, doc, audio, video, empty=any)", "hours": "int (default 24)"}
- "files.open", {"path": "string"}

Other:
- "translate", {"text": "string", "to": "string (lang code, e.g. en, ar, fr, ja)", "source": "string (default auto)"}
- "findmy.device", {"device": "string"}

Menu interface:
- "menu.open", {} — open the JARVIS menu window (big arc reactor, latest news headlines, current Spotify track)
- "menu.close", {} — close the menu window

JARVIS camera / gesture control (webcam — MODE 1):
- "camera.start", {} — open the JARVIS camera/gesture-control window: your webcam feed with hand tracking; move your index finger to move the mouse, pinch thumb+index to click
- "camera.stop", {} — close the JARVIS camera window
Use camera.start whenever the user asks to "open the camera", "camera mode", "gesture control", "use the camera to control the Mac", "move the mouse with my hand/finger", or "pinch to click". Do NOT use system.open_app for this — the JARVIS camera is a built-in window (camera.start), never the Photo Booth app.

Memory (user profile, stored in the Obsidian vault as JARVIS/Memory):
- "memory.remember", {"fact": "string"} — save a durable personal fact about the user
- "memory.recall", {} — read the user's memory note
- "memory.forget", {"fact": "string"} — remove facts mentioning this text

Focus mode (real blocking — apps are quit and kept closed):
- "focus.start", {"minutes": "int (default 25)", "apps": "list of app names (optional; defaults to Safari/Chrome/Messages/Slack/Discord/Instagram/TikTok/Netflix)"}
- "focus.stop", {}
- "focus.status", {}

Daily briefing:
- "briefing.get", {} — calendar, weather, unread mail and news headlines in one call

Shell / coding:
- "shell.run", {"command": "string", "cwd": "string (optional)", "timeout": "int seconds (default 30)"} — run a shell command, returns output
- "shell.write_file", {"path": "string", "content": "string"} — write a script/code file
- "shell.read_file", {"path": "string"} — read a file

HUD:
- "hud.launch", {"preview": "boolean (optional, default false → fullscreen on TV)"}
- "hud.close", {}
- "hud.preview", {} — open the PyQt HUD as a window on the primary display (local preview, no TV)
- "hud.launch_on_tv", {"receiver": "string (TV name from hud.list_receivers, optional)"} — mirror the HUD window to an AirPlay receiver
- "hud.launch_web", {"port": "int (default 8765)"} — start the web HUD server (universal fallback for non-AirPlay TVs; returns a URL)
- "hud.stop_web", {}
- "hud.list_receivers", {} — list visible AirPlay receiver names
- "hud.stop_airplay", {} — turn off the current AirPlay mirroring session

App positioning (for HUD or general use):
- "apps.open_positioned", {"app_name": "string", "position": "string (left|right|center|top-left|top-right|bottom-left|bottom-right|top-half|bottom-half|left-half|right-half|full)", "screen": "string (optional, empty=main, external=first non-primary)", "x": "int (optional, override)", "y": "int (optional, override)", "width": "int (optional, override)", "height": "int (optional, override)"}

Calendar:
- "calendar.week_events", {"days": "int (default 7)"}

Rules:
- If answering a general question, put the answer in "message" and leave "calls" empty.
- Call tools when the user's intent maps to a tool. Put a brief confirmation in "message".
- For Obsidian: capture thoughts/meeting notes/tasks into the user's vault. When no vault is specified and one is ambiguous, call obsidian.list_vaults first. Prefer obsidian.search for retrieval questions about the user's notes.
- MEMORY: You maintain a personal memory note in Obsidian (JARVIS/Memory). When the user reveals a durable fact about themselves (name, preferences, routines, people), call memory.remember. Before answering personal questions, call memory.recall.
- FOCUS: For focus mode use focus.start with real app names; default list blocks Safari/Chrome/Messages/Slack/Discord. Always confirm which apps before starting.
- CODING: For coding tasks use shell.run / shell.write_file / shell.read_file. Write scripts to ~/ or /tmp first, run them, read errors, and iterate. NEVER run destructive commands (rm -rf, diskutil, mkfs, sudo) without explicit confirmation.
- BRIEFING: When the user asks for a daily briefing or morning summary, call briefing.get and summarize the result.
- If you need more information before calling a tool (e.g. who to message), ask in "message".
- Prefer resolving contact names via contacts.search when ambiguous.
- Use web.search for anything time-sensitive or recent.
- Do NOT include any free‑form text outside the JSON object.
"""

# ----------------------------------------------------------------------
# Core async processing & History State
# ----------------------------------------------------------------------
conversation_history = []

async def process_user_input(user_text: str) -> dict:
    global conversation_history
    conversation_history.append({"role": "user", "content": user_text})
    if len(conversation_history) > 16:
        conversation_history = conversation_history[-16:]
        
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history_text = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in conversation_history])
    prompt = f"Current Time: {now_str}\n\n"
    # Inject the user's Obsidian-backed memory profile so JARVIS remembers them.
    try:
        memory_text = load_memory_summary()
        if memory_text:
            prompt += f"User Memory (from Obsidian):\n{memory_text}\n\n"
    except Exception:
        pass
    prompt += f"Conversation History:\n{history_text}\n\nRespond ONLY in JSON:"

    try:
        # Offload blocking network code to a background thread
        raw = await asyncio.to_thread(call_openrouter, SYSTEM_INSTRUCTION, prompt)
    except Exception as network_exc:
        return {"error": f"⚠️ OpenRouter Call failed: {network_exc}"}
    
    try:
        payload = json.loads(raw)
        calls: List[Dict[str, Any]] = payload.get("calls", [])
        message: str = payload.get("message", "")
    except Exception as exc:
        return {"error": f"⚠️ LLM returned non‑JSON: {raw}\nError: {exc}"}

    summary_lines = []
    if calls:
        results = await dispatch_calls(calls)
        for call, result in zip(calls, results):
            name = call.get("name")
            if isinstance(result, Exception):
                summary_lines.append(f"❌ {name} failed: {result}")
            else:
                summary_lines.append(f"✅ {name} succeeded: {json.dumps(result, default=str)}")
    
    if message:
        conversation_history.append({"role": "assistant", "content": message})
        
    return {
        "message": message,
        "logs": "\n".join(summary_lines) if summary_lines else "✅ No tool calls"
    }

# ----------------------------------------------------------------------
# Simple console REPL
# ----------------------------------------------------------------------
async def main() -> None:
    print("🟢 JARVIS console started – type your request (Ctrl‑C to quit)")
    while True:
        try:
            user_text = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input("\n🗣️  You: ")
            )
            if not user_text.strip():
                continue
            reply = await process_user_input(user_text)
            if reply.get("message"):
                print("\n🤖 JARVIS:", reply["message"])
            if reply.get("logs"):
                print("   Logs:", reply["logs"])
            if reply.get("error"):
                print("   Error:", reply["error"])
        except (KeyboardInterrupt, EOFError):
            print("\n🛑 Shutting down JARVIS …")
            break

if __name__ == "__main__":
    asyncio.run(main())