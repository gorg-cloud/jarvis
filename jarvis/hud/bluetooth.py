"""
jarvis/hud/bluetooth.py
Bluetooth RFCOMM server for HUD data broadcast.
Master broadcasts JSON telemetry + log lines to any connected BT client.

Usage:
    server = BTServer(port=1)
    server.start()   # background thread

Client (target PC) connects via:
    rfcomm connect /dev/rfcomm0 <MAC> 1
    cat /dev/rfcomm0 | python client.py
"""
import json
import socket
import threading
import time
from typing import Optional


class BTServer:
    """RFCOMM socket server. Streams newline-delimited JSON."""

    def __init__(self, port: int = 1, host: str = ""):
        self.port = port
        self.host = host
        self._sock: Optional[socket.socket] = None
        self._clients: list = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._data_callback = None  # called to get current telemetry dict

    def set_data_source(self, fn):
        """fn() -> dict — called every tick to get telemetry."""
        self._data_callback = fn

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        for c in self._clients:
            try:
                c.close()
            except Exception:
                pass
        self._clients.clear()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass

    def broadcast(self, data: dict):
        """Send JSON line to all connected clients."""
        msg = json.dumps(data) + "\n"
        raw = msg.encode("utf-8")
        dead = []
        for c in self._clients:
            try:
                c.sendall(raw)
            except Exception:
                dead.append(c)
        for c in dead:
            self._clients.remove(c)

    def _accept_loop(self):
        try:
            self._sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind((self.host, self.port))
            self._sock.listen(1)
        except Exception as e:
            # Bluetooth not available (no adapter / not on Linux)
            print(f"[BT] RFCOMM init failed: {e} — BT disabled")
            return
        print(f"[BT] Listening on RFCOMM :{self.port}")
        self._sock.settimeout(1.0)
        while self._running:
            try:
                conn, addr = self._sock.accept()
                self._clients.append(conn)
                print(f"[BT] Client connected: {addr}")
            except socket.timeout:
                continue
            except Exception:
                if self._running:
                    continue
                break
