"""
jarvis/tools/notion_tool.py
Fully realized Notion integration – inserts a task row into a Notion database.
"""
import asyncio
from typing import Dict
from notion_client import Client
from ..config import NOTION_TOKEN, NOTION_DATABASE_ID

# Thread-safe Notion client (reused across calls)
notion = Client(auth=NOTION_TOKEN)


async def add_task(title: str) -> Dict:
    """
    Insert a new page (row) into the configured Notion database.

    Parameters
    ----------
    title : str
        The task title that appears in the 'Name' column.

    Returns
    -------
    dict
        Notion API response containing the new page ID and URL.
    """
    backoff = 1
    last_error = None
    for attempt in range(5):
        try:
            payload = {
                "parent": {"database_id": NOTION_DATABASE_ID},
                "properties": {
                    "Name": {
                        "title": [{"text": {"content": title}}]
                    }
                },
            }
            # notion-client is synchronous, so run it in a thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: notion.pages.create(**payload))
            return {
                "id": response.get("id"),
                "url": response.get("url"),
                "title": title,
            }
        except Exception as exc:
            last_error = exc
            if "rate" in str(exc).lower() or "limit" in str(exc).lower():
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            raise
    raise RuntimeError(f"Failed to add task to Notion after 5 retries: {last_error}")
