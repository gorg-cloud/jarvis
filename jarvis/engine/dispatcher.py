"""
jarvis/engine/dispatcher.py
Maps LLM-generated function-call names to real Python callables
and executes them concurrently via asyncio.gather.
"""
import asyncio
from typing import Any, Callable, Dict, List

from ..tools.notion_tool import add_task
from ..tools.notion_read_tool import list_tasks
from ..tools.reminders_tool import create_reminder
from ..tools.alarms_tool import create_alarm
from ..tools.system_tools import open_app, open_url, set_wifi, set_bluetooth, sleep_mac, start_screensaver
from ..tools.system_extras import (
    set_volume, get_volume, mute, unmute, set_brightness, toggle_dnd,
    battery_status, system_uptime, start_timer, list_timers,
)
from ..tools.mac_apps import send_message as _mac_send_message, control_music
from ..tools.contacts_tools import search_contacts, call_contact, send_message as contacts_send_message
from ..tools.clipboard_tool import read_clipboard, write_clipboard
from ..tools.context_tool import frontmost_app, selected_text, active_context
from ..tools.spotify_tool import control_spotify, spotify_status
from ..tools.weather_tool import get_weather, get_forecast
from ..tools.calendar_tool import next_events, free_at
from ..tools.mail_tool import draft_email, unread_count
from ..tools.vision_tool import analyze_screen, screenshot
from ..tools.web_tool import web_search, fetch_url
from ..tools.files_tool import find_files, recent_files, open_file
from ..tools.translate_tool import translate
from ..tools.findmy_tool import find_device
from ..tools.notify_tool import notify
from ..tools.hud_tool import (
    launch_hud, close_hud,
    launch_hud_preview, launch_hud_on_tv, launch_hud_web, stop_hud_web,
    list_airplay_receivers, stop_airplay_session,
)
from ..tools.app_position_tool import open_app_positioned
from ..tools.calendar_tool import week_events
from ..tools.menu_tool import open_menu, close_menu
from ..tools.memory_tool import remember, recall, forget
from ..tools.focus_tool import start_focus, stop_focus, focus_status
from ..tools.shell_tool import run_shell, write_file as shell_write_file, read_file as shell_read_file
from ..tools.briefing_tool import get_briefing
from ..tools.gestures_tool import start_gestures, stop_gestures, start_project, stop_project
from ..camera.canvas_api import (
    add_text as canvas_add_text,
    add_image as canvas_add_image,
    add_image_url as canvas_add_image_url,
    add_plan as canvas_add_plan,
    add_schedule as canvas_add_schedule,
    add_flowchart as canvas_add_flowchart,
    zoom as canvas_zoom,
    remove_last as canvas_remove_last,
    clear_canvas as canvas_clear,
)
from ..tools.obsidian_tool import (
    list_vaults as obsidian_list_vaults,
    create_note as obsidian_create_note,
    read_note as obsidian_read_note,
    append_note as obsidian_append_note,
    search_notes as obsidian_search_notes,
    open_note as obsidian_open_note,
    open_vault as obsidian_open_vault,
    search_in_obsidian as obsidian_search_ui,
)

# -------------------------------------------------------------------
# Tool registry – add new tools here as you build them
# -------------------------------------------------------------------
TOOL_REGISTRY: Dict[str, Callable] = {
    # Notes / tasks
    "notion.add_task":      add_task,
    "notion.list_tasks":    list_tasks,
    "reminders.create":     create_reminder,
    "alarms.create":        create_alarm,
    # System
    "system.open_app":      open_app,
    "system.open_url":      open_url,
    "system.set_wifi":      set_wifi,
    "system.set_bluetooth": set_bluetooth,
    "system.sleep":         sleep_mac,
    "system.screensaver":   start_screensaver,
    "system.set_volume":    set_volume,
    "system.get_volume":    get_volume,
    "system.mute":          mute,
    "system.unmute":        unmute,
    "system.set_brightness": set_brightness,
    "system.toggle_dnd":    toggle_dnd,
    "system.battery":       battery_status,
    "system.uptime":        system_uptime,
    "system.start_timer":   start_timer,
    "system.list_timers":   list_timers,
    "system.notify":        notify,
    # Apps
    "apps.send_message":    contacts_send_message,
    "apps.music":           control_music,
    "apps.spotify":         control_spotify,
    "apps.spotify_status":  spotify_status,
    # Contacts / comms
    "contacts.search":      search_contacts,
    "contacts.call":        call_contact,
    # Email
    "mail.draft":           draft_email,
    "mail.unread_count":    unread_count,
    # Calendar
    "calendar.next_events": next_events,
    "calendar.free_at":     free_at,
    # Clipboard
    "clipboard.read":       read_clipboard,
    "clipboard.write":      write_clipboard,
    # Context
    "context.frontmost_app": frontmost_app,
    "context.selected_text": selected_text,
    "context.active":       active_context,
    # Weather
    "weather.current":      get_weather,
    "weather.forecast":     get_forecast,
    # Vision
    "vision.analyze_screen": analyze_screen,
    "vision.screenshot":    screenshot,
    # Web
    "web.search":           web_search,
    "web.fetch":            fetch_url,
    # Files
    "files.find":           find_files,
    "files.recent":         recent_files,
    "files.open":           open_file,
    # Translate
    "translate":            translate,
    # Find My
    "findmy.device":        find_device,
    # HUD
    "hud.launch":           launch_hud,
    "hud.close":            close_hud,
    "hud.preview":          launch_hud_preview,
    "hud.launch_on_tv":     launch_hud_on_tv,
    "hud.launch_web":       launch_hud_web,
    "hud.stop_web":         stop_hud_web,
    "hud.list_receivers":   list_airplay_receivers,
    "hud.stop_airplay":     stop_airplay_session,
    # App positioning (HUD embedded apps)
    "apps.open_positioned":  open_app_positioned,
    # Calendar week view
    "calendar.week_events": week_events,
    # JARVIS menu interface
    "menu.open":              open_menu,
    "menu.close":             close_menu,
    # Memory (Obsidian-backed profile)
    "memory.remember":        remember,
    "memory.recall":          recall,
    "memory.forget":          forget,
    # Focus mode (real app blocking)
    "focus.start":            start_focus,
    "focus.stop":             stop_focus,
    "focus.status":           focus_status,
    # Daily briefing
    "briefing.get":           get_briefing,
    # Shell / coding
    "shell.run":              run_shell,
    "shell.write_file":       shell_write_file,
    "shell.read_file":        shell_read_file,
    # Obsidian notes (second brain)
    "obsidian.list_vaults":   obsidian_list_vaults,
    "obsidian.create_note":   obsidian_create_note,
    "obsidian.read_note":     obsidian_read_note,
    "obsidian.append_note":   obsidian_append_note,
    "obsidian.search":        obsidian_search_notes,
    "obsidian.search_ui":     obsidian_search_ui,
    "obsidian.open_note":     obsidian_open_note,
    "obsidian.open_vault":    obsidian_open_vault,
    # JARVIS camera / gesture control (webcam cursor + pinch-to-click)
    "gestures.start":         start_gestures,
    "gestures.stop":          stop_gestures,
    "camera.start":           start_gestures,
    "camera.stop":            stop_gestures,
    # PROJECT canvas (Mode 3 — the Iron Man workshop)
    "project.start":          start_project,
    "project.stop":           stop_project,
    "canvas.add_text":        canvas_add_text,
    "canvas.add_image":       canvas_add_image,
    "canvas.add_image_url":   canvas_add_image_url,
    "canvas.add_plan":        canvas_add_plan,
    "canvas.add_schedule":    canvas_add_schedule,
    "canvas.add_flowchart":   canvas_add_flowchart,
    "canvas.zoom":            canvas_zoom,
    "canvas.remove_last":     canvas_remove_last,
    "canvas.clear":           canvas_clear,
}


async def invoke_tool(name: str, args: Dict[str, Any]) -> Any:
    """
    Look up a tool by name and call it with the supplied arguments.
    Sync functions are automatically offloaded to a thread pool.
    """
    if name not in TOOL_REGISTRY:
        raise ValueError(f"Unknown tool '{name}'. Registered tools: {list(TOOL_REGISTRY)}")

    func = TOOL_REGISTRY[name]

    if asyncio.iscoroutinefunction(func):
        return await func(**args)
    else:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(**args))


async def dispatch_calls(calls: List[Dict[str, Any]]) -> List[Any]:
    """
    Execute a list of LLM-generated function calls concurrently.

    Parameters
    ----------
    calls : list[dict]
        Each dict must have {"name": "tool_name", "args": {...}}.

    Returns
    -------
    list
        Results (or Exception objects) in the same order as the input calls.
    """
    tasks = [invoke_tool(c["name"], c.get("args", {})) for c in calls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return list(results)
