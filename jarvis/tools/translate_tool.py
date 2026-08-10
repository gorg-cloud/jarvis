"""
jarvis/tools/translate_tool.py
Uses Google Translate's public endpoint (no API key).
"""
import urllib.request
import urllib.parse
import json
import re


def translate(text: str, to: str = "en", source: str = "auto") -> dict:
    """
    Translate text. `to` = target language code (en, es, fr, ar, ja, ...).
    """
    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": source,
        "tl": to,
        "dt": "t",
        "q": text,
    }
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        # data[0] = list of [translated_chunk, original_chunk, ...]
        chunks = data[0] if data else []
        translated = "".join(c[0] for c in chunks if c and c[0])
        detected = data[2] if len(data) > 2 and data[2] else source
        return {
            "source": detected,
            "target": to,
            "original": text,
            "translation": translated,
        }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "text": text}
