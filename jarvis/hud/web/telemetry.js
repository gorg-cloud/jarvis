/* ====================================================================
   JARVIS HUD — telemetry.js
   Connects to ws://<host>:8765/stream, receives telemetry at 1Hz,
   updates the web widgets. Falls back to simulated data if no server.
   ==================================================================== */

(() => {
  "use strict";

  const W = window.JARVIS_WIDGETS;
  if (!W) {
    console.error("[jarvis] widgets.js failed to load");
    return;
  }

  // ---- DOM refs ------------------------------------------------------
  const $ = (id) => document.getElementById(id);

  const statusText = document.querySelector(".status__text");
  const uplinkEl   = $("meta-uplink");
  const hostEl     = $("meta-host");
  const osEl       = $("meta-os");
  const connEl     = $("conn");
  const batNameEl  = $("bat-name");
  const killBtn    = $("kill");
  const clockEl    = $("clock");
  const consoleEl  = $("console");
  const panelT     = $("panel-telemetry");
  const panelC     = $("panel-console");
  const panelS     = $("panel-system");

  // ---- widget instances ---------------------------------------------
  W.initGauges();
  const gauges = {
    cpu: document.querySelector('.gauge[data-key="cpu"]'),
    ram: document.querySelector('.gauge[data-key="ram"]'),
    bat: document.querySelector('.gauge[data-key="bat"]'),
  };
  const ramGraph = new W.MiniGraph($("ram-graph"), { maxPoints: 60 });
  const cpuGraph = new W.MiniGraph($("cpu-graph"), { maxPoints: 60 });
  const md       = new W.MarkdownStream(consoleEl, { maxLines: 300 });

  // ---- clock ---------------------------------------------------------
  function tickClock() {
    const d = new Date();
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    const ss = String(d.getSeconds()).padStart(2, "0");
    clockEl.textContent = `${hh}:${mm}:${ss}`;
  }
  tickClock();
  setInterval(tickClock, 1000);

  // ---- kill button: only closes the browser tab ---------------------
  killBtn.addEventListener("click", () => {
    if (window.confirm("Close JARVIS HUD?")) window.close();
  });

  // ---- apply a telemetry frame -------------------------------------
  function applyTelemetry(d) {
    if (typeof d.cpu === "number") {
      gauges.cpu._set(d.cpu);
      cpuGraph.push(d.cpu);
    }
    if (typeof d.ram_pct === "number") {
      gauges.ram._set(d.ram_pct);
      ramGraph.push(d.ram_pct);
    }
    if (typeof d.battery_pct === "number") {
      gauges.bat._set(d.battery_pct);
      batNameEl.textContent = d.battery_charging ? "BATTERY · CHG" : "BATTERY";
    }
    if (d.hostname) hostEl.textContent = d.hostname;
    if (d.os)       osEl.textContent   = d.os;
    if (Array.isArray(d.log) && d.log.length) {
      // Only append new tail lines to avoid replaying the buffer on every tick
      const last = md.lines.length ? md.lines[md.lines.length - 1] : null;
      const start = last && d.log[d.log.length - 1] === last ? d.log.length : 0;
      for (let i = start; i < d.log.length; i++) md.append(d.log[i]);
    }
    W.pulseActive(panelT);
    W.pulseActive(panelS);
  }

  // ---- boot lines ----------------------------------------------------
  md.append("# JARVIS HUD Online");
  md.append("* Awaiting telemetry uplink…");
  md.append("");

  // ---- websocket -----------------------------------------------------
  // Derive WS host from page location so a TV pointed at the same
  // Mac IP over the LAN uses the right origin.
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${proto}//${location.hostname}:8765/stream`;

  function setUplink(state, text) {
    statusText.textContent = state;
    uplinkEl.textContent = text;
    if (state === "ONLINE")   uplinkEl.style.color = "var(--cyan)";
    else if (state === "LINK") uplinkEl.style.color = "var(--cyan)";
    else                       uplinkEl.style.color = "var(--error)";
  }

  let ws = null;
  let reconnectDelay = 1000;
  const MAX_RECONNECT = 8000;

  function connect() {
    setUplink("LINK", `connecting ${wsUrl}`);
    try {
      ws = new WebSocket(wsUrl);
    } catch (e) {
      scheduleReconnect();
      return;
    }
    ws.addEventListener("open", () => {
      reconnectDelay = 1000;
      setUplink("ONLINE", "connected");
      md.append(`* [${ts()}] uplink established → ${wsUrl}`);
      W.pulseActive(panelC);
    });
    ws.addEventListener("message", (ev) => {
      try {
        const d = JSON.parse(ev.data);
        applyTelemetry(d);
      } catch (e) {
        console.warn("[jarvis] bad frame", e);
      }
    });
    ws.addEventListener("close", () => {
      setUplink("OFFLINE", "disconnected — retrying");
      connEl.textContent = "WS: reconnecting…";
      scheduleReconnect();
    });
    ws.addEventListener("error", () => {
      connEl.textContent = "WS: error";
    });
  }

  function scheduleReconnect() {
    setTimeout(connect, reconnectDelay);
    reconnectDelay = Math.min(MAX_RECONNECT, Math.floor(reconnectDelay * 1.6));
  }

  function ts() {
    const d = new Date();
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
  }

  connect();
})();
