"""
jarvis/hud/server.py
Web HUD server. Serves jarvis/hud/web/ static files and broadcasts
telemetry from the existing Telemetry class over a WebSocket.

Usage:
    python -m jarvis.hud.server --port 8765

Endpoints:
    GET  /            → index.html (and other static assets)
    GET  /style.css
    GET  /widgets.js
    GET  /telemetry.js
    WS   /stream      → pushes telemetry JSON every 1s
    POST /log         → {"text": "..."} appends a line to the HUD log
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import socket
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .data import Telemetry

log = logging.getLogger("jarvis.hud.server")

WEB_DIR = Path(__file__).parent / "web"


def _local_ip() -> str:
    """Best-effort LAN IP for display in the startup banner."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def build_app(telemetry: Telemetry | None = None) -> tuple[FastAPI, "WebHub"]:
    """Build the FastAPI app. Returns (app, hub). The hub is exposed so
    the caller can also drive `push_log` from outside the WS clients."""
    if telemetry is None:
        telemetry = Telemetry(interval=1.0)
    hub = WebHub()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        telemetry.start()
        log.info("telemetry started")
        tick_task = asyncio.create_task(_tick_loop())
        try:
            yield
        finally:
            tick_task.cancel()
            telemetry.stop()
            log.info("telemetry stopped")

    async def _tick_loop() -> None:
        while True:
            await asyncio.sleep(telemetry.interval)
            if hub.clients:
                await hub.broadcast_telemetry(telemetry.latest)

    app = FastAPI(title="JARVIS HUD", version="0.1", lifespan=lifespan)

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True, "clients": len(hub.clients)}

    @app.post("/log")
    async def post_log(payload: dict) -> JSONResponse:
        text = (payload or {}).get("text", "")
        if not text:
            return JSONResponse({"ok": False, "error": "missing 'text'"}, status_code=400)
        telemetry.add_log(text)
        await hub.broadcast_log(text)
        return JSONResponse({"ok": True})

    @app.websocket("/stream")
    async def stream(ws: WebSocket) -> None:
        await ws.accept()
        hub.add(ws)
        log.info("client connected (%d total)", len(hub.clients))
        try:
            # Push the current snapshot once on connect, then keep open.
            await ws.send_text(json.dumps(telemetry.latest))
            while True:
                # We don't expect inbound messages, but reading keeps the
                # connection alive and lets the client close gracefully.
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception as e:  # noqa: BLE001
            log.warning("ws error: %s", e)
        finally:
            hub.discard(ws)
            log.info("client disconnected (%d total)", len(hub.clients))

    # Static files. Serve the web/ directory at root.
    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/style.css")
    async def style_css() -> FileResponse:
        return FileResponse(WEB_DIR / "style.css", media_type="text/css")

    @app.get("/widgets.js")
    async def widgets_js() -> FileResponse:
        return FileResponse(WEB_DIR / "widgets.js", media_type="application/javascript")

    @app.get("/telemetry.js")
    async def telemetry_js() -> FileResponse:
        return FileResponse(WEB_DIR / "telemetry.js", media_type="application/javascript")

    @app.get("/favicon.ico")
    async def favicon() -> FileResponse:
        # No favicon yet; serve an empty response so the browser stops 404ing.
        return FileResponse(WEB_DIR / "index.html")

    app.mount(
        "/static",
        StaticFiles(directory=str(WEB_DIR)),
        name="static",
    )

    return app, hub


class WebHub:
    """Track connected WS clients + drive per-tick broadcasts."""

    def __init__(self) -> None:
        self.clients: Set[WebSocket] = set()
        self._task: asyncio.Task | None = None
        self._telemetry: Telemetry | None = None

    def add(self, ws: WebSocket) -> None:
        self.clients.add(ws)

    def discard(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def broadcast_telemetry(self, data: dict) -> None:
        if not self.clients:
            return
        msg = json.dumps(data)
        dead: list[WebSocket] = []
        for ws in list(self.clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.discard(ws)

    async def broadcast_log(self, text: str) -> None:
        if not self.clients:
            return
        payload = json.dumps({"log": [text]})
        dead: list[WebSocket] = []
        for ws in list(self.clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.discard(ws)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0", help="bind address (default 0.0.0.0)")
    p.add_argument("--port", type=int, default=8765, help="port (default 8765)")
    p.add_argument("--log-level", default="info")
    args = p.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )

    telemetry = Telemetry(interval=1.0)
    app, hub = build_app(telemetry)

    import uvicorn
    ip = _local_ip()
    log.info("JARVIS HUD server starting")
    log.info("  Local:   http://localhost:%d/", args.port)
    log.info("  Network: http://%s:%d/  (open this on the TV)", ip, args.port)
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
