"""
jarvis/engine/ollama.py
Ollama (local LLM) integration — JARVIS's offline fallback provider.

Talks to Ollama's native API (/api/chat) on this Mac, which supports
JSON-schema output formatting and base64 image input. That lets local
models (gemma4, llava, ornith…) follow JARVIS's strict JSON tool-calling
contract and answer questions about screenshots — with zero API cost and
no quota, so it's the perfect safety net when the OpenRouter keys run out.

Config (see config.py):
  OLLAMA_URL        default http://localhost:11434
  OLLAMA_MODEL      chat model, default gemma4:12b
  OLLAMA_VISION_MODEL  vision model, default gemma4:12b
  OLLAMA_FIRST      "true" → try Ollama before the cloud keys
  OLLAMA_ENABLED    "false" → never use Ollama
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from ..config import OLLAMA_DISABLED, OLLAMA_MODEL, OLLAMA_URL, OLLAMA_VISION_MODEL

_available: dict = {"at": 0.0, "ok": False}


def available() -> bool:
    """True when Ollama is enabled AND reachable. Result cached 30s so the
    hot path (every chat message) doesn't ping the server each time."""
    if OLLAMA_DISABLED:
        return False
    now = time.time()
    if now - _available["at"] < 30:
        return _available["ok"]
    ok = False
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=2) as resp:
            ok = resp.status == 200
    except Exception:
        ok = False
    _available["at"] = now
    _available["ok"] = ok
    return ok


def _post(path: str, payload: dict, timeout: float = 90.0) -> dict:
    req = urllib.request.Request(
        f"{OLLAMA_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def chat(system_prompt: str, user_prompt: str, schema: dict | None = None) -> str:
    """Ask the local model. `schema` (a JSON Schema object) is passed to
    Ollama's `format` field so the reply is forced to valid, schema-shaped
    JSON — critical for JARVIS's tool-calling contract."""
    if not available():
        raise RuntimeError(
            "Ollama is not running. Start it (open the Ollama app, or run "
            "`ollama serve`), then try again."
        )
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.3},
        # Keep the model resident so repeat JARVIS messages skip the cold
        # load (first reply ~40s, warm replies ~10s).
        "keep_alive": "10m",
    }
    if schema:
        payload["format"] = schema
    try:
        data = _post("/api/chat", payload)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"Ollama HTTP {exc.code}: {body[:300]}") from exc
    except Exception as exc:
        raise RuntimeError(f"Ollama error: {exc}") from exc
    return (data.get("message") or {}).get("content", "").strip()


def vision(question: str, img_b64: str) -> str:
    """Ask a local vision model about a base64 PNG (e.g. a screenshot)."""
    if not available():
        raise RuntimeError(
            "Ollama is not running. Start it (open the Ollama app, or run "
            "`ollama serve`), then try again."
        )
    payload = {
        "model": OLLAMA_VISION_MODEL,
        "messages": [{"role": "user", "content": question, "images": [img_b64]}],
        "stream": False,
        "keep_alive": "10m",
    }
    try:
        data = _post("/api/chat", payload, timeout=120.0)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"Ollama HTTP {exc.code}: {body[:300]}") from exc
    except Exception as exc:
        raise RuntimeError(f"Ollama error: {exc}") from exc
    return (data.get("message") or {}).get("content", "").strip()
