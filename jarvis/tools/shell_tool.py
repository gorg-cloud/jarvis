"""
jarvis/tools/shell_tool.py
Gives JARVIS coding + command capability: run shell commands, write code
files, and read them back. Every command is logged to ~/.jarvis/shell.log.

Tools:
  - shell.run {command, cwd, timeout}
  - shell.write_file {path, content}
  - shell.read_file {path, max_chars}
"""
import os
import signal
import subprocess
import time

SHELL_LOG = os.path.expanduser("~/.jarvis/shell.log")
_MAX_OUTPUT = 4000


def _log(command: str, cwd: str, ok: bool, note: str = "") -> None:
    try:
        with open(SHELL_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ok={ok} cwd={cwd} cmd={command[:300]} {note}\n")
    except Exception:
        pass


def run_shell(command: str, cwd: str = "", timeout: int = 30) -> dict:
    """Run a shell command and return its output (capped)."""
    command = (command or "").strip()
    if not command:
        return {"error": "empty command"}
    timeout = max(1, min(int(timeout or 30), 300))
    workdir = os.path.expanduser(cwd) if cwd else os.path.expanduser("~")

    try:
        proc = subprocess.Popen(
            command, shell=True, cwd=workdir,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
            out, err = proc.communicate()
            _log(command, workdir, False, "TIMEOUT")
            return {"error": f"Command timed out after {timeout}s", "output": (out + err)[-_MAX_OUTPUT:]}
    except Exception as exc:
        _log(command, workdir, False, str(exc))
        return {"error": f"{type(exc).__name__}: {exc}"}

    output = (out or "") + (("\n" + err) if err else "")
    _log(command, workdir, proc.returncode == 0, output[:200])
    return {
        "exit_code": proc.returncode,
        "output": output[:_MAX_OUTPUT],
        "truncated": len(output) > _MAX_OUTPUT,
    }


def write_file(path: str, content: str = "") -> dict:
    """Write (or overwrite) a file — used for creating scripts and code."""
    if not path:
        return {"error": "a path is required"}
    try:
        p = os.path.abspath(os.path.expanduser(path))
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content or "")
        return {"status": "written", "path": p, "characters": len(content or "")}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def read_file(path: str, max_chars: int = 6000) -> dict:
    """Read a file's contents (capped)."""
    if not path:
        return {"error": "a path is required"}
    try:
        p = os.path.abspath(os.path.expanduser(path))
        if not os.path.isfile(p):
            return {"error": f"file not found: {path}"}
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(max_chars)
        total = os.path.getsize(p)
        return {"path": p, "content": text, "truncated": total > max_chars}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
