/* ====================================================================
   JARVIS HUD — widgets.js
   Ports of the PyQt widgets (GaugeCircle, MiniGraph, MarkdownStream).
   Same line-classification rules as widgets.py:MarkdownStream._paint_line.
   ==================================================================== */

(() => {
  "use strict";

  const FONT_MONO = "11px 'JetBrains Mono', ui-monospace, monospace";
  const FONT_MONO_SM = "9px 'JetBrains Mono', ui-monospace, monospace";
  const FONT_MONO_BIG = "30px 'JetBrains Mono', ui-monospace, monospace";

  // ---- GaugeCircle (SVG) --------------------------------------------
  // PyQt version draws a 270° arc starting at 225° (bottom-left → bottom-right sweep).
  // We rotate the SVG by 135° in CSS and use stroke-dasharray to draw the 270° arc.
  // The "value" portion is 270 * (value / max). Full circumference ≈ 364; 270° ≈ 273.
  const ARC_270 = 273; // 270° in stroke-dasharray units (approx, with our stroke length)

  function initGauges() {
    document.querySelectorAll(".gauge").forEach((g) => {
      const valEl = g.querySelector(".gauge__num");
      const arc = g.querySelector(".gauge__value");
      g._set = (v) => {
        const clamped = Math.max(0, Math.min(100, Number(v) || 0));
        valEl.textContent = Math.round(clamped);
        // 0% → offset = ARC_270 (fully hidden), 100% → offset = 0
        arc.style.strokeDashoffset = String(ARC_270 - (clamped / 100) * ARC_270);
      };
      g._set(0);
    });
  }

  // ---- MiniGraph (canvas) -------------------------------------------
  // Rolling line graph with grid lines and a cyan gradient fill underneath.
  class MiniGraph {
    constructor(canvas, { maxPoints = 60 } = {}) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.data = [];
      this.maxPoints = maxPoints;
      this.label = canvas.dataset.label || "";
      this._resize();
      window.addEventListener("resize", () => this._resize());
    }

    _resize() {
      const dpr = window.devicePixelRatio || 1;
      const rect = this.canvas.getBoundingClientRect();
      this.canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      this.canvas.height = Math.max(1, Math.floor(rect.height * dpr));
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this._w = rect.width;
      this._h = rect.height;
      this._draw();
    }

    push(v) {
      this.data.push(Number(v) || 0);
      if (this.data.length > this.maxPoints) {
        this.data = this.data.slice(-this.maxPoints);
      }
      this._draw();
    }

    _draw() {
      const ctx = this.ctx;
      const w = this._w, h = this._h;
      if (!w || !h) return;
      ctx.clearRect(0, 0, w, h);
      const margin = 2;
      const gw = w - margin * 2;
      const gh = h - margin * 2 - 14;
      const gx0 = margin, gy0 = margin;

      // grid lines
      ctx.strokeStyle = "rgba(255,255,255,0.06)";
      ctx.lineWidth = 1;
      for (const f of [0.25, 0.5, 0.75]) {
        const y = gy0 + Math.floor(gh * (1 - f));
        ctx.beginPath();
        ctx.moveTo(gx0, y);
        ctx.lineTo(w - gx0, y);
        ctx.setLineDash([1, 3]);
        ctx.stroke();
      }
      ctx.setLineDash([]);

      if (this.data.length < 2) {
        this._drawLabel();
        return;
      }
      const maxV = Math.max(...this.data, 1);

      // fill
      ctx.beginPath();
      ctx.moveTo(gx0, gy0 + gh);
      this.data.forEach((v, i) => {
        const x = gx0 + (i * gw) / (this.data.length - 1);
        const y = gy0 + gh * (1 - v / maxV);
        ctx.lineTo(x, y);
      });
      ctx.lineTo(gx0 + gw, gy0 + gh);
      ctx.closePath();
      const grad = ctx.createLinearGradient(0, gy0, 0, gy0 + gh);
      grad.addColorStop(0, "rgba(0,240,255,0.32)");
      grad.addColorStop(1, "rgba(0,240,255,0)");
      ctx.fillStyle = grad;
      ctx.fill();

      // stroke
      ctx.beginPath();
      this.data.forEach((v, i) => {
        const x = gx0 + (i * gw) / (this.data.length - 1);
        const y = gy0 + gh * (1 - v / maxV);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = "rgba(0,240,255,0.9)";
      ctx.lineWidth = 1.5;
      ctx.stroke();

      this._drawLabel(maxV);
    }

    _drawLabel(maxV) {
      const ctx = this.ctx;
      ctx.font = FONT_MONO_SM;
      ctx.fillStyle = "rgba(0,240,255,0.7)";
      ctx.textBaseline = "bottom";
      ctx.textAlign = "left";
      ctx.fillText(this.label, 2, this._h - 2);
      if (maxV != null) {
        ctx.fillStyle = "rgba(136,136,136,0.9)";
        ctx.textAlign = "right";
        ctx.fillText(String(Math.round(maxV)), this._w - 2, this._h - 2);
      }
    }
  }

  // ---- MarkdownStream (line classification) -------------------------
  // Mirrors widgets.py:MarkdownStream._paint_line rules.
  function classifyLine(line) {
    const s = line.trimStart();
    if (s.startsWith("###")) return { cls: "h3", text: s.slice(3).trim() };
    if (s.startsWith("##"))  return { cls: "h2", text: s.slice(2).trim() };
    if (s.startsWith("# "))  return { cls: "h1", text: s.slice(1).trim() };
    if (s.startsWith("* ") || s.startsWith("- ")) return { cls: "bullet", text: s.slice(2) };
    if (s.startsWith("```")) return { cls: "code", text: "▎" + s };
    if (s.startsWith("  ") || s.startsWith("\t")) return { cls: "code", text: s };
    if (/^\[\d{2}:\d{2}:\d{2}\]/.test(s)) {
      const end = s.indexOf("]") + 1;
      return { cls: "ts", ts: s.slice(0, end), rest: s.slice(end) };
    }
    if (s.includes("❌") || /error|failed/i.test(s)) return { cls: "error", text: s };
    if (s.includes("✅")) return { cls: "ok", text: s };
    return { cls: "", text: s };
  }

  class MarkdownStream {
    constructor(el, { maxLines = 300 } = {}) {
      this.el = el;
      this.maxLines = maxLines;
      this.lines = [];
      this._render();
    }
    append(text) {
      const parts = String(text).split("\n");
      for (const p of parts) this.lines.push(p);
      if (this.lines.length > this.maxLines) {
        this.lines = this.lines.slice(-this.maxLines);
      }
      this._render(true);
    }
    _render(autoScroll = false) {
      const frag = document.createDocumentFragment();
      for (const line of this.lines) {
        const cls = classifyLine(line);
        const div = document.createElement("div");
        div.className = "console__line" + (cls.cls ? " console__line--" + cls.cls : "");
        if (cls.cls === "ts") {
          const ts = document.createElement("span");
          ts.className = "console__ts";
          ts.textContent = cls.ts;
          const rest = document.createTextNode(cls.rest);
          div.appendChild(ts);
          div.appendChild(rest);
        } else {
          div.textContent = cls.text;
        }
        frag.appendChild(div);
      }
      this.el.replaceChildren(frag);
      if (autoScroll) this.el.scrollTop = this.el.scrollHeight;
    }
  }

  // ---- panel activation: highlight panel whose data just changed ---
  // Subtle. Brightens border for 1.2s, then fades back to rest.
  function pulseActive(panelEl) {
    if (!panelEl) return;
    panelEl.classList.add("panel--active");
    clearTimeout(panelEl._pulseT);
    panelEl._pulseT = setTimeout(() => {
      panelEl.classList.remove("panel--active");
    }, 1200);
  }

  // ---- exports --------------------------------------------------------
  window.JARVIS_WIDGETS = {
    initGauges,
    MiniGraph,
    MarkdownStream,
    pulseActive,
  };
})();
