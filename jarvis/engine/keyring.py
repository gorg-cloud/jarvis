"""
jarvis/engine/keyring.py
API-key rotation with automatic failover.

JARVIS talks to OpenRouter with a pool of keys (see config._parse_keys —
comma-separated and/or numbered GEMINI_API_KEY_2/_3/_4). When a request
fails with a quota / rate-limit / auth error, that key is quarantined for
a cooldown window and the next key is tried immediately. On success the
key is marked healthy again, so a key that was temporarily rate-limited
comes back automatically once its cooldown expires.

The shared GEMINI_RING below is used by both the brain (main.py) and the
vision tool so quarantine state stays consistent across the app.
"""
from __future__ import annotations

import threading
import time

from ..config import GEMINI_API_KEYS

# Errors that mean "this key is dead for a while — try another":
#   401 unauthorized (bad key), 402 insufficient credits, 403 forbidden,
#   429 rate limited, 408 timeout, 503 unavailable, plus 4xx bodies that
#   mention quota/credit/rate.
_FAILOVER_CODES = {401, 402, 403, 408, 429, 503}
_FAILOVER_KEYWORDS = ("quota", "credit", "rate", "limit", "exhausted", "balance")


def is_failover_error(code: int, body: str = "") -> bool:
    """True when an API error should rotate to the next key."""
    if code in _FAILOVER_CODES:
        return True
    low = (body or "").lower()
    if 400 <= code < 500 and any(k in low for k in _FAILOVER_KEYWORDS):
        return True
    return False


class KeyRing:
    """Round-robin key pool with quarantine + cooldown. Thread-safe."""

    def __init__(self, keys, cooldown_seconds: float = 300.0) -> None:
        self._keys = [k for k in (keys or []) if k]
        self._cooldown = cooldown_seconds
        self._quarantine: dict = {}   # key -> epoch until which it is suspended
        self._idx = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------- state

    @property
    def count(self) -> int:
        return len(self._keys)

    def healthy_count(self) -> int:
        now = time.time()
        with self._lock:
            return sum(1 for k in self._keys
                       if k not in self._quarantine or self._quarantine[k] <= now)

    def status(self) -> str:
        with self._lock:
            n = len(self._keys)
            if n == 0:
                return "no API keys configured"
            now = time.time()
            healthy = sum(1 for k in self._keys
                          if k not in self._quarantine or self._quarantine[k] <= now)
            if self._quarantine:
                q = [k[:10] + "…" for k in self._keys if k in self._quarantine]
                return f"{healthy}/{n} keys healthy (quarantined: {', '.join(q)})"
            return f"{n} key(s) healthy"

    # ------------------------------------------------------------ access

    def current(self):
        """First non-quarantined key (advancing past dead ones), or None
        when every key is currently quarantined."""
        with self._lock:
            if not self._keys:
                return None
            now = time.time()
            for _ in range(len(self._keys)):
                key = self._keys[self._idx % len(self._keys)]
                if key not in self._quarantine or self._quarantine[key] <= now:
                    return key
                self._idx += 1
            return None

    def next(self):
        """Rotate to the next position and return its (non-quarantined) key."""
        with self._lock:
            self._idx += 1
        return self.current()

    def mark_failed(self, key) -> None:
        """Quarantine a key after a quota/rate-limit/auth error and rotate
        past it so the next request starts on a different key."""
        with self._lock:
            self._quarantine[key] = time.time() + self._cooldown
            if self._keys and self._keys[self._idx % len(self._keys)] == key:
                self._idx += 1

    def mark_ok(self, key) -> None:
        """A request succeeded — clear any quarantine on this key."""
        with self._lock:
            self._quarantine.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._quarantine.clear()
            self._idx = 0


# Shared ring for the whole app (brain + vision share quarantine state).
GEMINI_RING = KeyRing(GEMINI_API_KEYS)
