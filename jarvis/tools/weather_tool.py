"""
jarvis/tools/weather_tool.py
Uses wttr.in (no API key required).
"""
import json
import urllib.request
import urllib.error


def _wttr(query: str, fmt: str = "j1") -> dict:
    url = f"https://wttr.in/{urllib.parse.quote(query)}?format={fmt}"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return {"ok": True, "body": body}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def get_weather(location: str = "") -> dict:
    """Current weather + short forecast. Empty location = auto-detect by IP."""
    if not location:
        location = ""
    r = _wttr(location, "j1")
    if not r["ok"]:
        return {"location": location, "error": r["error"]}

    try:
        data = json.loads(r["body"])
        cur = data.get("current_condition", [{}])[0]
        area = data.get("nearest_area", [{}])[0]
        weather = cur.get("weatherDesc", [{}])[0].get("value", "")
        return {
            "location": area.get("areaName", [{}])[0].get("value", location),
            "country": area.get("country", [{}])[0].get("value", ""),
            "temp_c": cur.get("temp_C"),
            "temp_f": cur.get("temp_F"),
            "feels_c": cur.get("FeelsLikeC"),
            "feels_f": cur.get("FeelsLikeF"),
            "humidity": cur.get("humidity"),
            "description": weather,
            "wind_kph": cur.get("windspeedKmph"),
            "wind_dir": cur.get("winddir16Point"),
        }
    except Exception as e:
        return {"location": location, "error": f"parse: {e}", "raw": r["body"][:200]}


def get_forecast(location: str = "", hours: int = 6) -> dict:
    """Next N hours of forecast."""
    r = _wttr(location, "j1")
    if not r["ok"]:
        return {"location": location, "error": r["error"]}
    try:
        data = json.loads(r["body"])
        out = []
        for day in data.get("weather", [])[:1]:  # today
            for h in day.get("hourly", []):
                out.append({
                    "time": h.get("time"),
                    "temp_c": h.get("tempC"),
                    "chance_rain": h.get("chanceofrain"),
                    "desc": h.get("weatherDesc", [{}])[0].get("value", ""),
                })
                if len(out) >= hours:
                    break
        area = data.get("nearest_area", [{}])[0]
        return {
            "location": area.get("areaName", [{}])[0].get("value", location),
            "hours": out,
        }
    except Exception as e:
        return {"location": location, "error": f"parse: {e}"}
