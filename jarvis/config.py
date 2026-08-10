import os
from pathlib import Path

# python-dotenv is preferred but optional — a tiny fallback parser keeps the
# package importable (and testable) without it.
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


def _load_dotenv(path: Path) -> None:
    """Load KEY=VALUE pairs from a file without overriding existing env vars."""
    if load_dotenv is not None:
        try:
            load_dotenv(path)
        except Exception:
            pass
        return
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if not key:
                continue
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
    except Exception:
        pass


# Load .env from the project root, plus a few fallback locations so the
# packaged JARVIS.app (PyInstaller bundle) can find keys too:
#   - <project>/.env                      (development)
#   - ~/.jarvis/.env  and  ~/.jarvis.env  (packaged app)
#   - ./.env                              (current working directory)
BASE_DIR = Path(__file__).resolve().parent.parent
_ENV_CANDIDATES = [
    BASE_DIR / ".env",
    Path.home() / ".jarvis" / ".env",
    Path.home() / ".jarvis.env",
    Path.cwd() / ".env",
]
for _env_path in _ENV_CANDIDATES:
    _load_dotenv(_env_path)

# ------------ AI MODEL SETTINGS ------------
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "gemini")  # "gemini" or "anthropic"


def _parse_keys(*env_names: str) -> list:
    """Collect API keys from several env vars. Each value may be a
    comma-separated list; duplicates are dropped, order preserved.

    Usage — all of these feed the same failover pool:
        GEMINI_API_KEY="key1,key2"
        GEMINI_API_KEY_2="key3"   (numbered variants, up to _4)
        GEMINI_API_KEYS="key4"    (explicit list alias)
    """
    keys: list = []
    for name in env_names:
        for part in (os.getenv(name, "") or "").split(","):
            part = part.strip()
            if part and part not in keys:
                keys.append(part)
    return keys


GEMINI_API_KEYS = _parse_keys(
    "GEMINI_API_KEYS",
    "GEMINI_API_KEY",
    "GEMINI_API_KEY_2",
    "GEMINI_API_KEY_3",
    "GEMINI_API_KEY_4",
)
GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else None
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "nemotron-3-nano-30b-a3b:free")
ANTHROPIC_MODEL = "claude-3-sonnet-20240229"

# ------------ OLLAMA (LOCAL LLM) SETTINGS ------------
# Ollama runs on this Mac and acts as the offline fallback when the
# OpenRouter keys are exhausted / rate-limited (or first if OLLAMA_FIRST=true).
# No API key needed. Models must be pulled first: `ollama pull gemma4:12b`.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "ornith:latest")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "gemma4:12b")
OLLAMA_FIRST = os.getenv("OLLAMA_FIRST", "").strip().lower() in ("1", "true", "yes", "on")
OLLAMA_DISABLED = os.getenv("OLLAMA_ENABLED", "").strip().lower() in ("0", "false", "no", "off")

# ------------ NOTION SETTINGS ------------
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

# ------------ OBSIDIAN SETTINGS ------------
# Vaults are auto-discovered from Obsidian's registry. Override if needed:
#   OBSIDIAN_VAULT       — default vault name to use when none is given
#   OBSIDIAN_VAULT_PATH  — direct path to a vault folder (bypasses discovery)
OBSIDIAN_VAULT = os.getenv("OBSIDIAN_VAULT", "") or None
OBSIDIAN_VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", "") or None

# ------------ ALARM SETTINGS ------------
USE_SHORTCUT = False  # Use AppleScript fallback (Calendar alarms)
ALARM_SHORTCUT_NAME = "CreateAlarm"

# ------------ MQTT SETTINGS (optional) ------------
MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))

# ------------ DEVICE REGISTRY ------------
DEVICES_CONFIG = BASE_DIR / "config" / "devices.json"
if DEVICES_CONFIG.exists():
    import json
    with open(DEVICES_CONFIG) as f:
        DEVICES = json.load(f)
else:
    DEVICES = {}
