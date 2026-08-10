"""
jarvis/tools/web_tool.py
Web search + URL fetch via DuckDuckGo HTML (no API key).
"""
import urllib.request
import urllib.parse
import re
import html


def web_search(query: str, limit: int = 5) -> dict:
    """Search the web. Returns list of {title, url, snippet}."""
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return {"query": query, "error": f"{type(e).__name__}: {e}"}

    results = []
    # DuckDuckGo HTML result blocks
    for m in re.finditer(
        r'<a rel="nofollow" class="result__a" href="([^"]+)">(.*?)</a>.*?'
        r'<a class="result__snippet"[^>]*>(.*?)</a>',
        body, re.DOTALL
    ):
        link = html.unescape(m.group(1))
        # Decode DDG redirect
        link_match = re.search(r"uddg=([^&]+)", link)
        if link_match:
            link = urllib.parse.unquote(link_match.group(1))
        title = re.sub(r"<[^>]+>", "", html.unescape(m.group(2))).strip()
        snippet = re.sub(r"<[^>]+>", "", html.unescape(m.group(3))).strip()
        results.append({"title": title, "url": link, "snippet": snippet})
        if len(results) >= limit:
            break

    if not results:
        # Fallback to instant answer API
        return _ddg_instant(query)

    return {"query": query, "count": len(results), "results": results}


def _ddg_instant(query: str) -> dict:
    """DuckDuckGo instant answer API as fallback."""
    url = "https://api.duckduckgo.com/?q=" + urllib.parse.quote(query) + "&format=json&no_html=1"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            import json
            data = json.loads(resp.read().decode())
        abstract = data.get("AbstractText") or data.get("Abstract") or ""
        related = [
            {"text": r.get("Text", ""), "url": r.get("FirstURL", "")}
            for r in data.get("RelatedTopics", [])[:5]
            if isinstance(r, dict) and "Text" in r
        ]
        return {
            "query": query,
            "abstract": abstract,
            "source": data.get("AbstractURL", ""),
            "related": related,
        }
    except Exception as e:
        return {"query": query, "error": f"{type(e).__name__}: {e}"}


def fetch_url(url: str, max_chars: int = 4000) -> dict:
    """Fetch a URL and return cleaned text (first max_chars)."""
    if not url.startswith("http"):
        url = "https://" + url
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        # Strip HTML tags crudely
        text = re.sub(r"<script[^>]*>.*?</script>", "", body, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return {
            "url": url,
            "title": (re.search(r"<title[^>]*>(.*?)</title>", body, re.IGNORECASE | re.DOTALL) or [None, ""])[1].strip()
                    if "<title" in body.lower() else "",
            "text": text[:max_chars],
            "length": len(text),
        }
    except Exception as e:
        return {"url": url, "error": f"{type(e).__name__}: {e}"}
