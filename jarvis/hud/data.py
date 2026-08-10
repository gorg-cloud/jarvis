"""
jarvis/hud/data.py
Telemetry data layer. Polls CPU/RAM/battery at 1Hz.
Feeds widgets + serialises for Bluetooth/WebSocket broadcast.
"""
import json
import time
import socket
import platform
import threading
import subprocess
from typing import Dict, Any, Callable

try:
    import psutil
except ImportError:
    psutil = None


class Telemetry:
    """Polls system stats, notifies listeners on each tick."""

    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self._running = False
        self._thread = None
        self._listeners: list = []
        self.hostname = socket.gethostname()
        self.os_name = f"{platform.system()} {platform.release()}"
        self.log_entries: list = []
        self.max_log = 200
        self.latest: Dict[str, Any] = self._empty()

    def _empty(self) -> dict:
        return {
            "cpu": 0.0, "ram_pct": 0.4, "ram_gb": 0.0, "ram_total_gb": 0.0,
            "battery_pct": 0, "battery_charging": False,
            "hostname": self.hostname, "os": self.os_name,
            "timestamp": 0, "log": [],
        }

    def on_update(self, fn: Callable):
        self._listeners.append(fn)

    def add_log(self, text: str):
        ts = time.strftime("%H:%M:%S")
        self.log_entries.append(f"[{ts}] {text}")
        if len(self.log_entries) > self.max_log:
            self.log_entries = self.log_entries[-self.max_log:]

    def _poll(self):
        self.latest["timestamp"] = time.time()
        self.latest["hostname"] = self.hostname
        self.latest["os"] = self.os_name
        if psutil:
            self.latest["cpu"] = psutil.cpu_percent(interval=0)
            mem = psutil.virtual_memory()
            self.latest["ram_pct"] = mem.percent
            self.latest["ram_gb"] = round(mem.used / (1024**3), 1)
            self.latest["ram_total_gb"] = round(mem.total / (1024**3), 1)
            try:
                bat = psutil.sensors_battery()
                if bat:
                    self.latest["battery_pct"] = int(bat.percent)
                    self.latest["battery_charging"] = bat.power_plugged
            except Exception:
                pass
        # Battery fallback via the cross-platform helper
        try:
            from jarvis.platform import battery_status
            b = battery_status()
            if b.get("percent") is not None and b["percent"] >= 0:
                self.latest["battery_pct"] = b["percent"]
                self.latest["battery_charging"] = bool(b.get("charging"))
        except Exception:
            pass
        self.latest["log"] = self.log_entries[-50:]
        for fn in self._listeners:
            try:
                fn(self.latest)
            except Exception:
                pass

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            self._poll()
            time.sleep(self.interval)

    def to_json(self) -> str:
        return json.dumps(self.latest)
