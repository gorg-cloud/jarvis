"""
jarvis/tools/contacts_tools.py
Reads macOS Contacts and places calls via FaceTime audio.
"""
import subprocess
from typing import List, Optional

from jarvis.platform import macos_only, open_url


def _run_applescript(script: str, timeout: int = 15) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout.strip()


def _run_jxa(script: str, timeout: int = 20) -> str:
    """Run JavaScript-for-Automation (richer Contacts API access)."""
    result = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout.strip()


def search_contacts(query: str, limit: int = 10) -> dict:
    """
    Search contacts by name, email, or phone number.

    Returns up to `limit` matches with name + phones + emails.
    """
    blocked = macos_only("Contacts")
    if blocked:
        return {"query": query, "error": blocked}
    safe_query = query.replace('"', '\\"').replace("\\", "\\\\")
    # JXA gives us proper access to multi-value phone/email fields.
    jxa = f'''
    function run(argv) {{
      const Q = "{safe_query}".toLowerCase();
      const app = Application("Contacts");
      const out = [];
      const people = app.people();
      for (const p of people) {{
        let name = p.name();
        let phones = [];
        try {{
          const pv = p.phones();
          for (const ph of pv) {{ phones.push(ph.value()); }}
        }} catch (e) {{}}
        let emails = [];
        try {{
          const ev = p.emails();
          for (const em of ev) {{ emails.push(em.value()); }}
        }} catch (e) {{}}
        let hay = (name + " " + phones.join(" ") + " " + emails.join(" ")).toLowerCase();
        if (hay.indexOf(Q) !== -1) {{
          out.push({{name: name, phones: phones, emails: emails}});
          if (out.length >= {limit}) break;
        }}
      }}
      return JSON.stringify(out);
    }}
    '''
    try:
        raw = _run_jxa(jxa)
        import json
        matches = json.loads(raw) if raw else []
        return {"query": query, "count": len(matches), "contacts": matches}
    except subprocess.CalledProcessError as e:
        return {"query": query, "error": e.stderr.strip() or "Contacts access failed"}
    except Exception as e:
        return {"query": query, "error": f"{type(e).__name__}: {e}"}


def call_contact(contact: str, mode: str = "audio") -> dict:
    """
    Place a call via FaceTime.

    Parameters
    ----------
    contact : str
        Name, phone, or email of the contact.
    mode : str
        'audio' (default) or 'video'.
    """
    mode = mode.lower()
    if mode not in ("audio", "video"):
        return {"contact": contact, "status": "failed", "error": "mode must be 'audio' or 'video'"}

    blocked = macos_only("FaceTime calls")
    if blocked:
        return {"contact": contact, "status": "failed", "error": blocked}
    # Resolve name → phone/email first so FaceTime has a reachable handle.
    handle = contact
    if not any(c.isdigit() for c in contact) and "@" not in contact:
        lookup = search_contacts(contact, limit=1)
        matches = lookup.get("contacts") or []
        if not matches:
            return {"contact": contact, "status": "failed", "error": "No matching contact found"}
        c0 = matches[0]
        handle = (c0.get("phones") or c0.get("emails") or [None])[0]
        if not handle:
            return {"contact": contact, "status": "failed", "error": "Contact has no phone or email"}
        resolved_name = c0.get("name")
    else:
        resolved_name = contact

    # FaceTime has no AppleScript dictionary for placing calls directly.
    # Use the facetime:// URL scheme handled by FaceTime.app.
    scheme = "facetime-prompt://" if mode == "audio" else "facetime-prompt://"
    # facetime-audio:// for audio, facetime:// for video — both open FaceTime
    if mode == "audio":
        scheme = "facetime-audio://"
    else:
        scheme = "facetime://"

    try:
        subprocess.run(["open", f"{scheme}{handle}"], check=True, capture_output=True, text=True)
        return {
            "contact": contact,
            "resolved_to": handle,
            "name": resolved_name,
            "mode": mode,
            "status": "dialing",
        }
    except subprocess.CalledProcessError as e:
        return {"contact": contact, "status": "failed", "error": e.stderr.strip()}


def send_message(contact: str, message: str) -> dict:
    """
    Look up contact by name and iMessage/SMS them.
    Falls back to treating `contact` as a raw phone/email if no match.
    """
    blocked = macos_only("Messages")
    if blocked:
        return {"contact": contact, "status": "failed", "error": blocked}
    handle = contact
    if not any(c.isdigit() for c in contact) and "@" not in contact:
        lookup = search_contacts(contact, limit=1)
        matches = lookup.get("contacts") or []
        if matches:
            handle = (matches[0].get("phones") or [contact])[0]
        # else: leave handle as-is and let Messages decide

    safe_handle = handle.replace('"', '\\"')
    safe_msg = message.replace('"', '\\"').replace("\\", "\\\\")
    script = f'''
    tell application "Messages"
        set targetService to 1st service whose service type is iMessage
        set theBuddy to buddy "{safe_handle}" of targetService
        send "{safe_msg}" to theBuddy
    end tell
    '''
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
        return {"contact": contact, "handle": handle, "message": message, "status": "sent"}
    except subprocess.CalledProcessError as e:
        return {"contact": contact, "status": "failed", "error": e.stderr.strip()}
