"""
jarvis/tools/briefing_tool.py
The daily briefing: calendar, weather, unread mail and the latest news in
one call. The menu window uses this to populate its TODAY bar, and the LLM
can call briefing.get to read/speak it.

Tools:
  - briefing.get {}   — gather everything
  - news (helper)     — fetch_news_headlines() used by the menu too
"""
import urllib.request

_FEEDS = [
    ("BBC", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Hacker News", "https://hnrss.org/frontpage"),
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
]


def fetch_news_headlines(limit: int = 5, timeout: float = 8.0) -> dict:
    """Return the latest headlines from the first reachable RSS feed."""
    import xml.etree.ElementTree as ET
    for name, url in _FEEDS:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                root = ET.fromstring(resp.read())
            items = []
            for item in root.iter("item"):
                title = (item.findtext("title") or "").strip()
                if title:
                    items.append(title)
                if len(items) >= limit:
                    break
            if items:
                return {"source": name, "headlines": items}
        except Exception:
            continue
    return {"error": "Could not fetch news"}


def _fetch(kind: str):
    """Fetch one briefing component; never raises."""
    try:
        if kind == "calendar":
            from .calendar_tool import next_events
            return kind, next_events(limit=3)
        if kind == "weather":
            from .weather_tool import get_weather
            return kind, get_weather()
        if kind == "mail":
            from .mail_tool import unread_count
            return kind, unread_count()
        if kind == "news":
            return kind, fetch_news_headlines(limit=3)
    except Exception as exc:
        return kind, {"error": f"{type(exc).__name__}: {exc}"}
    return kind, {}


def get_briefing() -> dict:
    """Gather today's essentials in parallel: calendar, weather, mail, news."""
    from concurrent.futures import ThreadPoolExecutor, wait

    briefing: dict = {}
    executor = ThreadPoolExecutor(max_workers=4)
    futures = {executor.submit(_fetch, kind): kind
               for kind in ("calendar", "weather", "mail", "news")}
    done, not_done = wait(futures, timeout=10)
    for fut in done:
        try:
            _, data = fut.result()
        except Exception:
            data = {"error": "failed"}
        briefing[futures[fut]] = data
    for fut in not_done:
        briefing[futures[fut]] = {"error": "timed out"}
    executor.shutdown(wait=False)

    # Compact, LLM-friendly summary
    lines = []
    weather = briefing.get("weather") or {}
    if weather.get("temp_c") is not None or weather.get("description"):
        temp = weather.get("temp_c")
        desc = weather.get("description", "")
        lines.append((f"Weather: {temp}°C {desc}" if temp is not None else f"Weather: {desc}").strip())
    cal = briefing.get("calendar") or {}
    events = cal.get("events") or []
    if events:
        nxt = events[0]
        lines.append(f"Next event: {nxt.get('title', '?')} at {nxt.get('start', '?')} ({len(events)} upcoming)")
    mail = briefing.get("mail") or {}
    if mail.get("unread") is not None:
        lines.append(f"Unread mail: {mail['unread']}")
    news = briefing.get("news") or {}
    if news.get("headlines"):
        lines.append(f"News ({news.get('source')}): {' | '.join(news['headlines'][:2])}")
    briefing["summary"] = "\n".join(lines) if lines else "Nothing notable right now."

    return briefing
