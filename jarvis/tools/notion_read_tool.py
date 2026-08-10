"""
jarvis/tools/notion_read_tool.py
Reads tasks back from the Notion database (closes the loop with notion.add_task).
"""
import json
import urllib.request
from ..config import NOTION_TOKEN, NOTION_DATABASE_ID


def list_tasks(limit: int = 20) -> dict:
    """List tasks from the Notion database."""
    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        return {"error": "NOTION_TOKEN / NOTION_DATABASE_ID not set"}

    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    payload = {"page_size": limit}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        tasks = []
        for page in data.get("results", []):
            props = page.get("properties", {})
            title_prop = next(
                (v for v in props.values() if v.get("type") == "title"),
                None,
            )
            title = ""
            if title_prop and title_prop.get("title"):
                title = "".join(t.get("plain_text", "") for t in title_prop["title"])
            status = ""
            status_prop = next(
                (v for v in props.values() if v.get("type") == "status"),
                None,
            )
            if status_prop and status_prop.get("status"):
                status = status_prop["status"].get("name", "")
            tasks.append({"title": title, "status": status, "url": page.get("url", "")})
        return {"count": len(tasks), "tasks": tasks}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
