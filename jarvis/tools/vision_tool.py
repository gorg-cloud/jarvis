"""
jarvis/tools/vision_tool.py
Screenshot + send to vision-capable LLM via OpenRouter.
"""
import base64
import os
import subprocess
import tempfile
import urllib.request
import urllib.error
import json

from ..config import GEMINI_API_KEY, GEMINI_MODEL
from ..engine.keyring import GEMINI_RING, is_failover_error

# Default vision model (OpenRouter). Override via env VISION_MODEL.
# Free vision-capable models: google/gemma-4-26b-a4b-it:free (good), nvidia/nemotron-nano-12b-v2-vl:free (small)
VISION_MODEL = os.getenv("VISION_MODEL", "google/gemma-4-26b-a4b-it:free")


def screenshot(path: str = "") -> dict:
    """Take a screenshot. Default: temp file."""
    if not path:
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
    try:
        r = subprocess.run(["screencapture", "-x", path], capture_output=True, text=True, timeout=10)
        if r.returncode != 0 or not os.path.exists(path) or os.path.getsize(path) < 1000:
            err = r.stderr.strip() or "screenshot failed (likely Screen Recording permission)"
            return {"path": path, "error": err}
        size = os.path.getsize(path)
        return {"path": path, "size": size, "status": "ok"}
    except Exception as e:
        return {"path": path, "error": f"{type(e).__name__}: {e}"}


def _analyze_image(img_b64: str, question: str) -> dict:
    """Analyze an image: OpenRouter key pool first (multi-key failover),
    then the local Ollama vision model as an automatic offline fallback."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    last_err = None

    if GEMINI_API_KEY:
        attempts = max(1, min(3, GEMINI_RING.count))
        for _attempt in range(attempts):
            key = GEMINI_RING.current()
            if not key:
                break  # all keys cooling down -> Ollama
            payload = {
                "model": VISION_MODEL,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/png;base64,{img_b64}"
                        }},
                    ]
                }],
                "max_tokens": 800,
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    data = json.loads(resp.read().decode())
                text = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                GEMINI_RING.mark_ok(key)
                return {"answer": text.strip()}
            except urllib.error.HTTPError as e:
                body = e.read().decode()[:400]
                if is_failover_error(e.code, body):
                    GEMINI_RING.mark_failed(key)
                    continue
                last_err = f"OpenRouter HTTP {e.code}: {body}"
                break
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                break

    # Cloud keys exhausted, rate-limited, or missing — local Ollama vision.
    try:
        from ..engine.ollama import vision as ollama_vision
        answer = ollama_vision(question, img_b64)
        if answer:
            return {"answer": answer}
    except Exception as exc:  # noqa: BLE001
        last_err = (f"{last_err}; " if last_err else "") + f"Ollama: {exc}"
        return {"error": last_err}

    return {"error": last_err or "No vision provider available"}


def analyze_screen(question: str = "Describe what's on screen concisely.") -> dict:
    """Capture screen + ask LLM about it."""
    shot = screenshot()
    if "error" in shot:
        return shot
    path = shot["path"]
    try:
        with open(path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
    except Exception as e:
        return {"error": f"read: {e}"}
    result = _analyze_image(img_b64, question)
    result["question"] = question
    result["image"] = path
    return result


def analyze_image_file(path: str, question: str = "Describe this image.") -> dict:
    """Analyze any local image file."""
    if not os.path.exists(path):
        return {"error": f"file not found: {path}"}
    try:
        with open(path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
    except Exception as e:
        return {"error": f"read: {e}"}
    result = _analyze_image(img_b64, question)
    result["question"] = question
    result["image"] = path
    return result
