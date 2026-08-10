"""
jarvis/tools/mail_tool.py
Draft/send email via Mail.app.
"""
import subprocess

from jarvis.platform import macos_only


def draft_email(to: str, subject: str, body: str, send: bool = False) -> dict:
    """
    Create a new outgoing message in Mail.app.

    Parameters
    ----------
    to : str
        Recipient email (or name — Mail resolves from Contacts).
    subject : str
        Email subject.
    body : str
        Email body.
    send : bool
        False (default) → save as draft for user to review.
        True → send immediately.
    """
    blocked = macos_only("Mail")
    if blocked:
        return {"to": to, "status": "failed", "error": blocked}
    safe_to = to.replace('"', '\\"')
    safe_subj = subject.replace('"', '\\"')
    safe_body = body.replace('"', '\\"').replace("\\", "\\\\")
    verb = "send" if send else "save"
    script = f'''
    tell application "Mail"
        set newMsg to make new outgoing message with properties {{subject:"{safe_subj}", content:"{safe_body}", visible:true}}
        tell newMsg
            make new to recipient at end of to recipients with properties {{address:"{safe_to}"}}
            {verb}
        end tell
    end tell
    '''
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode != 0:
            return {"to": to, "status": "failed", "error": r.stderr.strip()}
        return {"to": to, "subject": subject, "action": verb, "status": "ok"}
    except Exception as e:
        return {"to": to, "status": "failed", "error": f"{type(e).__name__}: {e}"}


def unread_count() -> dict:
    """Count of unread messages across all accounts."""
    blocked = macos_only("Mail")
    if blocked:
        return {"error": blocked}
    script = '''
    tell application "Mail"
      set total to 0
      repeat with a in accounts
        repeat with mb in mailboxes of a
          try
            set total to total + (count of (messages of mb whose read status is false))
          end try
        end repeat
      end repeat
      return total
    end tell
    '''
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            return {"error": r.stderr.strip()}
        return {"unread": int(r.stdout.strip() or 0)}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
