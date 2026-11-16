"""The phase strips: for each line, and for each bike of a line opened by a click, two strips over the plan's weeks,
one per plan (the plan compared against first): customers waiting, then stock below target, then at target. The date
each is at target from is written on its strip and the shift in weeks beside it; weeks a change applies are shaded.
The deck's colours and words. Every figure comes from reading.phase_data."""
from __future__ import annotations

import json

import streamlit.components.v1 as components

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><style>
:root {--ink:#31333f; --muted:#808495; --grid:#ececea;}
* {box-sizing: border-box;}
html, body {margin: 0; background: #fff; overflow: hidden;}
body {font: 13px/1.3 "Source Sans Pro", "Source Sans 3", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica,
      Arial, sans-serif; color: var(--ink);}
#legend {display: flex; flex-wrap: wrap; gap: 4px 18px; align-items: center; height: 24px; font-size: 12px;
         color: var(--ink);}
#legend i {display: inline-block; width: 12px; height: 12px; border-radius: 2px; margin-right: 6px;
           vertical-align: -1px;}
#legend i.hatch {background: repeating-linear-gradient(135deg, #31333f 0 1.2px, transparent 1.2px 4px); outline: 1px solid #31333f; outline-offset: -1px;}
svg text {font-family: inherit;}
.name {cursor: pointer; user-select: none;}
.name:hover text {fill: #000;}
#tip {position: fixed; pointer-events: none; background: #fff; border: 1px solid #d6d6d3; border-radius: 6px;
      padding: 5px 8px; font-size: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.08); display: none; white-space: nowrap;}
#tip b {font-weight: 600;}
</style></head><body>
<div id="legend"></div><div id="chart"></div><div id="tip"></div>
<script>
const D = __DATA__;
const COL = {w: "#dc8e8e", b: "#d1d5db", a: "#8ac09e"};
const MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const NAME_W = 132, KEY_W = 54, DELTA_W = 70, LINE_H = 15, BIKE_H = 10, GAP = 3, GROUP = 14, BIKE_GAP = 7, AXIS = 24;
const open = {}; D.rows.forEach(r => open[r.id] = r.open);
const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
const tip = document.getElementById("tip");

const hasBands = D.rows.some(r => r.bands.length);
document.getElementById("legend").innerHTML =
  Object.entries(D.names).map(([k, n]) => `<span><i style="background:${COL[k]}"></i>${n}</span>`).join("")
  + (hasBands ? `<span><i class="hatch"></i>weeks changed</span>` : "");

function width(text, size, bold) {
  const c = width.c || (width.c = document.createElement("canvas").getContext("2d"));
  c.font = `${bold ? 600 : 400} ${size}px "Source Sans Pro", -apple-system, Helvetica, Arial, sans-serif`;
  return c.measureText(text).width;
}

function draw() {
  const W = document.body.clientWidth, end = D.end;
  if (!W) return;                                    // not on screen yet: drawn when it is (resize)
  const x0 = NAME_W + KEY_W, x1 = W - DELTA_W;
  const X = w => x0 + (w - 1) * (x1 - x0) / end;
  const out = [], labels = [];                       // labels are drawn last, above the change weeks
  let y = 4;

  function strips(item, top, h, size, tipName) {
    item.runs.forEach((runs, i) => {
      const yy = top + i * (h + GAP), scen = i === 1;
      out.push(`<text x="${x0 - 8}" y="${yy + h - 2}" font-size="${size}" text-anchor="end" fill="${scen ? "#31333f" : "#808495"}" font-weight="${scen ? 600 : 400}">${esc(D.keys[i])}</text>`);
      runs.forEach(([p, a, b]) => {
        if (a > end) return;
        const bb = Math.min(b, end);
        out.push(`<rect x="${X(a).toFixed(1)}" y="${yy}" width="${(X(bb + 1) - X(a)).toFixed(1)}" height="${h}" fill="${COL[p]}" data-t="${esc(D.keys[i] + " · " + tipName)}" data-p="${p}" data-a="${a}" data-b="${b}"/>`);
      });
      const held = item.held[i], last = item.runs[i][item.runs[i].length - 1];
      if (held && last[1] <= end) {
        const tw = width(held, size - 1, scen), xs = X(last[1]);
        const right = xs + 4 + tw <= x1;
        labels.push(`<text x="${(right ? xs + 4 : xs - 4).toFixed(1)}" y="${yy + h - 3}" font-size="${size - 1}" text-anchor="${right ? "start" : "end"}" fill="#1f2a1f" font-weight="${scen ? 600 : 400}" pointer-events="none">${esc(held)}</text>`);
      }
      if (scen) {
        const s = item.shift;
        let txt = "same", fill = "#808495", bg = null;
        if (item.held[1] === null) { txt = "not held"; fill = "#b42318"; bg = "#fde8e6"; }
        else if (s > 0) { txt = `+${s} wk`; fill = "#b42318"; bg = "#fde8e6"; }
        else if (s < 0) { txt = `−${-s} wk`; fill = "#1e7b3a"; bg = "#e4f4e8"; }
        const tw = width(txt, size - 1, true) + 12, xr = W - 2 - tw;
        if (bg) out.push(`<rect x="${xr}" y="${yy - 1}" width="${tw}" height="${h + 2}" rx="${(h + 2) / 2}" fill="${bg}"/>`);
        out.push(`<text x="${xr + tw / 2}" y="${yy + h - 2}" font-size="${size - 1}" text-anchor="middle" fill="${fill}" font-weight="600">${txt}</text>`);
      }
    });
    return top + 2 * h + GAP;
  }

  D.rows.forEach(r => {
    const top = y;
    out.push(`<g class="name" data-id="${r.id}"><rect x="0" y="${y - 2}" width="${NAME_W}" height="${2 * LINE_H + GAP + 4}" fill="transparent"/>`
      + `<text x="0" y="${y + LINE_H + 3}" font-size="14" font-weight="600"><tspan fill="#808495" font-weight="400">${open[r.id] ? "▾" : "▸"} </tspan>${esc(r.label)}</text></g>`);
    y = strips(r, y, LINE_H, 12, r.label);
    if (open[r.id]) r.bikes.forEach(b => {
      y += BIKE_GAP;
      out.push(`<text x="16" y="${y + BIKE_H + 3}" font-size="12">${esc(b.label)} <tspan fill="#808495">${esc(b.size)}</tspan></text>`);
      y = strips(b, y, BIKE_H, 11, b.label);
    });
    r.bands.forEach(([a, b]) => {
      if (a > end) return;
      out.push(`<rect x="${X(a).toFixed(1)}" y="${top - 3}" width="${(X(Math.min(b, end) + 1) - X(a)).toFixed(1)}" height="${y - top + 6}" fill="url(#hatch)" stroke="#31333f" stroke-width="1" pointer-events="none"/>`);
    });
    y += GROUP;
  });

  const grid = [], ticks = [];
  D.iso.forEach((d, i) => {
    const t = i + 1, m = +d.slice(5, 7), day = +d.slice(8, 10);
    if (t > end || day > 7 || ![1, 5, 9].includes(m)) return;
    const x = X(t).toFixed(1), lab = `${MON[m - 1]} ${d.slice(0, 4)}`;
    grid.push(`<line x1="${x}" x2="${x}" y1="0" y2="${y - GROUP + 4}" stroke="var(--grid)"/>`);
    ticks.push(`<text x="${x}" y="${y + 6}" font-size="12" fill="#808495" text-anchor="middle">${lab}</text>`);
  });
  const H = y + AXIS - 6;
  document.getElementById("chart").innerHTML =
    `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><defs><pattern id="hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="5" stroke="#31333f" stroke-width="1.3"/></pattern></defs>${grid.join("")}${out.join("")}${labels.join("")}${ticks.join("")}</svg>`;
  const total = document.body.scrollHeight;
  try {                                              // the frame and its container take the content's height
    const f = window.frameElement; f.style.height = total + "px"; f.height = total;
    if (f.parentElement) f.parentElement.style.height = total + "px";
  } catch (e) {}
}

document.getElementById("chart").addEventListener("click", e => {
  const g = e.target.closest(".name");
  if (g) { open[g.dataset.id] = !open[g.dataset.id]; draw(); }
});
document.getElementById("chart").addEventListener("mousemove", e => {
  const r = e.target.closest("rect[data-p]");
  if (!r) { tip.style.display = "none"; return; }
  const a = +r.dataset.a, b = +r.dataset.b, n = b - a + 1;
  tip.innerHTML = `<b>${r.dataset.t}</b><br>${D.names[r.dataset.p]} · weeks of ${D.weeks[a - 1]} to ${D.weeks[b - 1]} (${n})`;
  tip.style.display = "block";
  const x = Math.min(e.clientX + 12, document.body.clientWidth - tip.offsetWidth - 4);
  tip.style.left = x + "px"; tip.style.top = (e.clientY + 14) + "px";
});
document.getElementById("chart").addEventListener("mouseleave", () => tip.style.display = "none");
window.addEventListener("resize", draw);
draw();
</script></body></html>"""


def html(data: dict) -> str:
    return PAGE.replace("__DATA__", json.dumps(data))


def height(data: dict) -> int:
    """The frame's height with the lines open as given (the page resizes it when a line is opened or closed)."""
    h = 24 + 4 + 24
    for r in data["rows"]:
        h += 2 * 15 + 3 + 14 + (len(r["bikes"]) * (7 + 2 * 10 + 3) if r["open"] else 0)
    return h + 4


def render(data: dict):
    components.html(html(data), height=height(data), scrolling=False)
