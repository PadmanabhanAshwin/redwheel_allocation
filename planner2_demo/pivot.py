"""The build plan table, drawn in the browser as a pivot.

Rows: line → bike → metric. Columns: Start, fiscal year → quarter → month, Total; a year or quarter opens and closes
on a click on its header. A toolbar switches metric rows and subtotals (per line, all lines, per period) on and off.
Every figure comes from reading.pivot_data; the page only shows and hides cells, so nothing is recomputed."""
from __future__ import annotations

import json

import streamlit.components.v1 as components

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><style>
:root {--ink:#31333f; --muted:#808495; --grid:#e8e8e6; --tint:#f6f6f4; --sub:#efefec; --bad:#fde3df; --badt:#b42318;
       --full:#e3e6ea; --accent:#2a78d6;}
* {box-sizing: border-box;}
body {margin: 0; font: 13px/1.35 "Source Sans Pro", "Source Sans 3", -apple-system, BlinkMacSystemFont, "Segoe UI",
      Helvetica, Arial, sans-serif; color: var(--ink); background: #fff;}
#bar {display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; padding: 2px 0 10px 0;}
#bar .grp {display: flex; flex-wrap: wrap; align-items: center; gap: 6px;}
#bar .k {color: var(--muted); font-size: 12px; margin-right: 2px;}
.chip {border: 1px solid #d6d6d3; border-radius: 999px; padding: 2px 10px; cursor: pointer; user-select: none;
       color: var(--muted); background: #fff; transition: all .15s;}
.chip.on {border-color: var(--ink); color: var(--ink); background: var(--tint);}
.seg {display: inline-flex; border: 1px solid #d6d6d3; border-radius: 999px; overflow: hidden;}
.seg span {padding: 2px 11px; cursor: pointer; color: var(--muted); user-select: none; transition: all .15s;}
.seg span + span {border-left: 1px solid #d6d6d3;}
.seg span.on {background: var(--ink); color: #fff;}
#wrap {overflow: auto; border: 1px solid var(--grid); border-radius: 8px;}
table {border-collapse: separate; border-spacing: 0; font-variant-numeric: tabular-nums;}
th, td {padding: 0 10px; height: 27px; white-space: nowrap; border-bottom: 1px solid var(--grid); text-align: right;
        background: #fff;}
thead th {position: sticky; z-index: 2; color: var(--muted); font-weight: 600; font-size: 12px;}
thead tr:nth-child(1) th {top: 0;} thead tr:nth-child(2) th {top: 27px;} thead tr:nth-child(3) th {top: 54px;}
th.open, th.shut {cursor: pointer; color: var(--ink);}
th.open {text-align: center; border-bottom: 2px solid var(--grid);}
th.shut::after {content: " ▸"; color: var(--muted);}
th.open::after {content: " ▾"; color: var(--muted);}
th.shut:hover, th.open:hover {background: var(--tint);}
.c1, .c2, .c3 {position: sticky; text-align: left; z-index: 1;}
thead .c1, thead .c2, thead .c3 {z-index: 3;}
.c1 {left: 0; min-width: 110px; max-width: 110px;} .c2 {left: 110px; min-width: 104px; max-width: 104px;}
.c3 {left: 214px; min-width: 132px; max-width: 132px; border-right: 1px solid var(--grid);}
td.c2 small {color: var(--muted); margin-left: 4px;}
tr.line td {background: var(--tint); font-weight: 600; cursor: pointer;}
tr.em td.c1, tr.em td.c2 {background: #fff;}
tr.line td.c1::before {content: "▾ "; color: var(--muted);}
tr.line.closed td.c1::before {content: "▸ ";}
tr.em td {background: #f3f6fb; font-weight: 600;}
tr.sub td {background: var(--sub); font-weight: 600;}
tr.sub.em td {background: #e6ecf5;}
tr.all td {background: #e9e9e6; font-weight: 700;}
tr.first td {border-top: 1px solid #d6d6d3;}
td.psub, th.psub {background: var(--tint);}
tr.sub td.psub, tr.all td.psub {background: #e4e4e0;}
td.neg {color: var(--badt);}
td.pos {color: #1c5cab;}
td.same {color: var(--muted); font-weight: 400; text-align: left;}
td.below {background: var(--bad); color: var(--badt);}
td.full {background: var(--full);}
td.c3 {color: var(--muted);}
.new {animation: in .22s ease-out;}
@keyframes in {from {opacity: 0;} to {opacity: 1;}}
</style></head><body>
<div id="bar"></div><div id="wrap"><table id="t"></table></div>
<script>
const D = __DATA__, MAX_H = __MAX_H__;
const kids = {}, byId = {};
D.columns.forEach(c => { byId[c.id] = c; if (c.parent) (kids[c.parent] = kids[c.parent] || []).push(c); });
const open = {}; D.columns.forEach(c => { if (c.level === "Y") open[c.id] = true; if (c.level === "Q") open[c.id] = false; });
const on = {}; D.metrics.forEach(m => on[m.key] = m.on);
const sub = {line: true, all: true, period: false};
const shut = {};
let shown = new Set();
let mode = D.modes ? "diff" : null;                  // compare: 'diff' (B − A), 'a' or 'b'
let changedOnly = !!D.modes;
const keyOf = r => `${r.line}|${r.sku}|${r.metric}`;
const changed = {}; if (D.modes) D.modes.diff.forEach(r => changed[keyOf(r)] = r.changed);
const rowsNow = () => D.modes ? D.modes[mode] : D.rows;
let visNow = [];                                     // the columns on screen: 'changed' is judged on them
const moves = r => visNow.some(({c}) => { const v = D.modes.diff.find(x => keyOf(x) === keyOf(r)).values[c.id];
  return v !== null && v !== undefined && Math.abs(v) > 1e-9; });
const keep = r => !(changedOnly && mode) || moves(r);

function leaves(c) {
  const k = kids[c.id] || [];
  if (!k.length || !open[c.id]) return [{c: c, sub: false}];
  const out = k.flatMap(leaves);
  if (sub.period) out.push({c: c, sub: true});
  return out;
}
function fmt(m, v, of) {
  if (v === null || v === undefined) return ["", ""];
  if (mode === "diff") {
    if (Math.abs(v) < (m.kind === "ratio" ? 0.05 : m.kind === "share" ? 0.005 : 0.5)) return ["", ""];
    const t = m.kind === "share" ? Math.round(v * 100) + " pts" : m.kind === "ratio" ? v.toFixed(1)
            : Math.round(v).toLocaleString("en-US");
    return [(v > 0 ? "+" : "") + t.replace("-", "−"), v > 0 ? "pos" : "neg"];
  }
  if (m.kind === "share") return [Math.round(v * 100) + "%", v >= 0.995 ? "full" : ""];
  if (m.kind === "ratio") return [v.toFixed(1).replace("-", "−"), ""];
  if (m.kind === "flag") return of ? [v + " of " + of, v < of ? "below" : ""] : [v >= 0.5 ? "✓" : "✗", v >= 0.5 ? "" : "below"];
  const s = Math.round(v).toLocaleString("en-US").replace("-", "−");
  return [s, v < -0.5 ? "neg" : ""];
}
let scale = {};                                      // differences: the largest on screen per measure and row kind
const kindOf = r => r.sku ? "bike" : r.line ? "line" : "all";
const shaded = ({c, sub: isSub}) => !isSub && c.id !== "total";   // sums (Total, period totals) stay plain
function scales(rows, vis) {
  scale = {};
  rows.forEach(r => vis.filter(shaded).forEach(({c}) => {
    const v = r.values[c.id], k = r.metric + "|" + kindOf(r);
    if (v !== null && v !== undefined) scale[k] = Math.max(scale[k] || 0, Math.abs(v));
  }));
}
function heat(key, v) {                              // a difference's cell shaded by its size: blue more, red fewer
  if (mode !== "diff" || v === null || v === undefined || !scale[key]) return "";
  const a = Math.min(1, Math.abs(v) / scale[key]);
  return ` style="background: rgba(${v > 0 ? "42,120,214" : "180,35,24"},${(0.06 + 0.34 * a).toFixed(3)})"`;
}
function chip(label, active, fn) {
  const b = document.createElement("span");
  b.className = "chip" + (active ? " on" : ""); b.textContent = label; b.onclick = fn; return b;
}
function bar() {
  const el = document.getElementById("bar"); el.innerHTML = "";
  const g1 = document.createElement("div"); g1.className = "grp";
  g1.innerHTML = "<span class='k'>Measures</span>";
  D.metrics.forEach(m => g1.appendChild(chip(m.label, on[m.key], () => { on[m.key] = !on[m.key]; draw(); })));
  const g2 = document.createElement("div"); g2.className = "grp";
  g2.innerHTML = "<span class='k'>Subtotals</span>";
  [["line", "Line"], ["all", "All lines"], ["period", "Period"]].forEach(([k, lab]) =>
    g2.appendChild(chip(lab, sub[k], () => { sub[k] = !sub[k]; draw(); })));
  const g3 = document.createElement("div"); g3.className = "grp";
  g3.innerHTML = "<span class='k'>Columns</span>";
  g3.appendChild(seg(["Years", "Quarters", "Months"], colDepth(), d => { setCols(d); draw(); }));
  g3.insertAdjacentHTML("beforeend", "<span class='k' style='margin-left:10px'>Rows</span>");
  g3.appendChild(seg(["Lines", "Bikes"], rowDepth(), d => { D.lines.forEach(l => shut[l.id] = d === "Lines"); draw(); }));
  if (D.modes) {
    const g0 = document.createElement("div"); g0.className = "grp";
    g0.innerHTML = "<span class='k'>Values</span>";
    const names = {diff: D.labels.diff, a: D.labels.a, b: D.labels.b};
    g0.appendChild(seg(Object.values(names), names[mode], v => { mode = Object.keys(names).find(k => names[k] === v); draw(); }));
    if (mode === "diff") g0.appendChild(chip("Changed only", changedOnly, () => { changedOnly = !changedOnly; draw(); }));
    el.append(g0, g3, g1, g2);
    return;
  }
  el.append(g3, g1, g2);
}
function seg(options, active, fn) {
  const w = document.createElement("span"); w.className = "seg";
  options.forEach(o => { const b = document.createElement("span"); b.textContent = o;
    if (o === active) b.className = "on"; b.onclick = () => fn(o); w.appendChild(b); });
  return w;
}
const Y = D.columns.filter(c => c.level === "Y"), Q = D.columns.filter(c => c.level === "Q");
function colDepth() {
  if (Y.every(c => !open[c.id])) return "Years";
  if (Y.every(c => open[c.id]) && Q.every(c => !open[c.id])) return "Quarters";
  if (Y.every(c => open[c.id]) && Q.every(c => open[c.id])) return "Months";
  return null;
}
function setCols(d) {
  Y.forEach(c => open[c.id] = d !== "Years");
  Q.forEach(c => open[c.id] = d === "Months");
}
function rowDepth() {
  if (D.lines.every(l => shut[l.id])) return "Lines";
  if (D.lines.every(l => !shut[l.id])) return "Bikes";
  return null;
}
function head(vis) {
  const top = D.columns.filter(c => !c.parent);
  const r = [[], [], []];
  r[0].push("<th class='c1' rowspan='3'>Line</th><th class='c2' rowspan='3'>Bike</th><th class='c3' rowspan='3'>Measure</th>");
  const cell = (c, cls, span, rows, label) =>
    `<th class='${cls}' data-id='${c.id}' colspan='${span}' rowspan='${rows}'>${label}</th>`;
  top.forEach(y => {
    const ky = kids[y.id] || [];
    if (!ky.length) { r[0].push(cell(y, "", 1, 3, y.label)); return; }
    if (!open[y.id]) { r[0].push(cell(y, "shut", 1, 3, y.label)); return; }
    r[0].push(cell(y, "open", leaves(y).length, 1, y.label));
    ky.forEach(q => {
      const kq = kids[q.id] || [];
      if (!open[q.id]) { r[1].push(cell(q, "shut", 1, 2, q.label)); return; }
      r[1].push(cell(q, "open", leaves(q).length, 1, q.label));
      kq.forEach(mo => r[2].push(cell(mo, "", 1, 1, mo.label)));
      if (sub.period) r[2].push(cell(q, "psub", 1, 1, q.label + " total"));
    });
    if (sub.period) r[1].push(cell(y, "psub", 1, 2, y.label + " total"));
  });
  return "<thead>" + r.map(x => "<tr>" + x.join("") + "</tr>").join("") + "</thead>";
}
function row(cls, c1, c2, c3, m, vals, of, bad, vis, fresh) {
  let h = `<tr class='${cls}'><td class='c1'>${c1}</td><td class='c2'>${c2}</td><td class='c3'>${c3}</td>`;
  const key = m.key + "|" + (/\ball\b/.test(cls) ? "all" : /\bsub\b/.test(cls) ? "line" : "bike");
  vis.forEach(({c, sub: isSub}) => {
    const [txt, k] = fmt(m, vals[c.id], of);
    const b = bad && bad[c.id] ? " below" : "";
    const style = txt && shaded({c, sub: isSub}) ? heat(key, vals[c.id]) : "";
    h += `<td class='${k}${b}${isSub ? " psub" : ""}${fresh.has(c.id + isSub) ? " new" : ""}'${style}>${txt}</td>`;
  });
  return h + "</tr>";
}
function draw() {
  bar();
  const vis = D.columns.filter(c => !c.parent).flatMap(leaves);
  visNow = vis;
  const now = new Set(vis.map(v => v.c.id + v.sub));
  const fresh = new Set([...now].filter(x => shown.size && !shown.has(x)));
  shown = now;
  const ms = D.metrics.filter(m => on[m.key] && !(mode === "diff" && m.kind === "flag"));
  const R = rowsNow();
  if (mode === "diff") scales(R, vis);
  let body = "";
  D.lines.forEach(ln => {
    body += `<tr class='line${shut[ln.id] ? " closed" : ""}' data-line='${ln.id}'><td class='c1' colspan='3'>${ln.label}</td>`
          + `<td colspan='${vis.length}'></td></tr>`;
    const lineRows = R.filter(r => r.line === ln.id);
    if (changedOnly && mode && !lineRows.some(keep)) {
      const by = {Years: "year", Quarters: "quarter", Months: "month"}[colDepth()];
      const note = !lineRows.some(r => changed[keyOf(r)]) ? "no change"
                 : by ? `no change by ${by}` : "no change in the columns shown";
      body = body.replace(/<td colspan='\d+'><\/td><\/tr>$/, `<td colspan='${vis.length}' class='same'>${note}</td></tr>`);
      return;
    }
    if (!shut[ln.id]) {
      const bikes = [...new Set(lineRows.filter(r => r.sku).map(r => r.sku))];
      bikes.forEach(s => {
        const b = D.bikes[s];
        ms.filter(m => m.scope === "bike").map(m => [m, R.find(x => x.sku === s && x.metric === m.key)])
          .filter(([m, r]) => keep(r)).forEach(([m, r], i) => {
          body += row((i === 0 ? "first" : "") + (m.em ? " em" : ""), "", i === 0 ? `${s}<small>${b.size}</small>` : "", m.label,
                      m, r.values, null, mode === "diff" ? null : r.bad, vis, fresh);
        });
      });
    }
    if (sub.line || shut[ln.id]) {
      ms.filter(m => m.kind !== "ratio").map(m => [m, R.find(x => x.line === ln.id && !x.sku && x.metric === m.key)])
        .filter(([m, r]) => keep(r)).forEach(([m, r], i) => {
        body += row("sub" + (i === 0 ? " first" : "") + (m.em ? " em" : ""), "", i === 0 ? "Line total" : "", m.label, m, r.values, r.of, null, vis, fresh);
      });
    }
  });
  if (sub.all) {
    ms.filter(m => m.kind !== "ratio").map(m => [m, R.find(x => x.line === null && x.metric === m.key)])
      .filter(([m, r]) => keep(r)).forEach(([m, r], i) => {
      body += row("all" + (i === 0 ? " first" : ""), i === 0 ? "All lines" : "", "", m.label, m, r.values, r.of, null, vis, fresh);
    });
  }
  const t = document.getElementById("t");
  t.innerHTML = head(vis) + "<tbody>" + body + "</tbody>";
  t.querySelectorAll("th.open, th.shut").forEach(th => th.onclick = () => { open[th.dataset.id] = !open[th.dataset.id]; draw(); });
  t.querySelectorAll("tr.line").forEach(tr => tr.onclick = () => { shut[tr.dataset.line] = !shut[tr.dataset.line]; draw(); });
  fit();
}
window.addEventListener("resize", fit);
function fit() {                                     // the frame takes the table's height, up to MAX_H; then it scrolls
  const bar = document.getElementById("bar").offsetHeight, table = document.getElementById("t").offsetHeight + 2;
  if (!bar) return;                                  // not on screen yet: fitted when it is (resize)
  const h = Math.min(MAX_H, bar + table + 2);
  document.getElementById("wrap").style.maxHeight = (h - bar - 2) + "px";
  try {                                              // the frame and its container take the table's height
    const f = window.frameElement; f.style.height = h + "px"; f.height = h;
    if (f.parentElement) f.parentElement.style.height = h + "px";
  } catch (e) {}
}
draw();
</script></body></html>"""


def html(data: dict, max_height: int = 720) -> str:
    return PAGE.replace("__DATA__", json.dumps(data)).replace("__MAX_H__", str(int(max_height)))


def render(data: dict, height: int = 720):
    """The table; its frame shrinks to the rows shown, up to `height`, and scrolls beyond it."""
    components.html(html(data, height), height=height, scrolling=False)
