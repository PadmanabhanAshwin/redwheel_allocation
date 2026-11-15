"""The planning grid: one figure, months across, and for each line a row of capacity used with its SKUs' weeks of
supply under it, so the cause (a full line) sits above its effect (SKUs below target).

Colour carries one meaning each (see theme): dark = the line is full; orange = a SKU below target, darker the further
below; blue-grey = above target; near white = at target (no number, nothing to read). An orange outline marks the
months an event touches."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from planner2.charts import LINE_WORDS
from planner3 import theme as T
from planner3.reading import fdate
from ui import LINES

ROW = 21                       # pixels per row
DEEP = 8                       # weeks below target from which a cell is dark orange (white text)


def _wos_text(w, tg) -> str:
    """Whole weeks, but one decimal near the target (14.6 against 15 must not read 15) and near zero (no "−0")."""
    return (f"{w:.1f}" if abs(w - tg) < 1 or abs(w) < 0.5 else f"{w:.0f}").replace("-", "−")


def grid_figure(g: dict) -> go.Figure:
    months = g["months"]
    n = len(months) + 1                                   # column 0 is the start, 1.. the months
    xs = list(range(n))
    keys, labels, kinds = [], [], []
    for i, ln in enumerate(LINES):
        keys.append(f"L:{ln}"), labels.append(f"<b>{LINE_WORDS[ln]}</b>"), kinds.append("line")
        for r in g["lines"][ln]["rows"]:
            keys.append(f"S:{ln}:{r['label']}"), labels.append(f"{r['label']} · {r['size']}"), kinds.append("sku")
        if i < len(LINES) - 1:
            keys.append(f"_:{ln}"), labels.append(""), kinds.append("gap")
    row_of = {k: i for i, k in enumerate(keys)}

    layers = {name: (np.full((len(keys), n), np.nan), np.full((len(keys), n), "", dtype=object),
                     np.full((len(keys), n), "", dtype=object))
              for name in ("full", "part", "deep", "below", "above", "at")}

    def put(layer, i, j, z, text, hover):
        Z, TX, HV = layers[layer]
        Z[i, j], TX[i, j], HV[i, j] = z, text, hover

    for ln in LINES:
        d = g["lines"][ln]
        i = row_of[f"L:{ln}"]
        for j, p in enumerate(months, start=1):
            b, c, u = d["built"][j - 1], d["capacity"][j - 1], d["use"][j - 1]
            when = p.strftime("%b %Y")
            if c == 0:
                put("full", i, j, 1, "down", f"{LINE_WORDS[ln]} · {when}<br>no capacity this month")
            else:
                hover = f"{LINE_WORDS[ln]} · {when}<br>built {b:,.0f} of {c:,.0f} capacity ({u:.0%})"
                put("full" if d["full"][j - 1] else "part", i, j, 1 if d["full"][j - 1] else u, f"{u * 100:.0f}", hover)
        for r in d["rows"]:
            i = row_of[f"S:{ln}:{r['label']}"]
            for j in range(n):
                w, tg, ok = r["wos"][j], r["target"][j], r["ok"][j]
                when = "at the start (7 Sep 2026)" if j == 0 else f"end of {months[j - 1].strftime('%b %Y')}"
                hover = (f"{r['label']} · {when}<br>{w:,.1f} weeks of supply · target {tg:g}<br>net inventory "
                         f"{r['net'][j]:,.0f}" + ("" if r["built"][j] is None else f" · built in the month {r['built'][j]:,.0f}"))
                gap = w - tg
                if not ok:
                    put("deep" if -gap >= DEEP else "below", i, j, min(-gap, 25.0), _wos_text(w, tg), hover)
                elif gap >= 1:
                    put("above", i, j, min(gap, 30.0), _wos_text(w, tg), hover)
                else:
                    put("at", i, j, 0, "", hover)

    styles = {   # layer: (colorscale, zmin, zmax, text colour)
        "full": ([[0, T.INK], [1, T.INK]], 0, 1, "white"),
        "part": ([[0, "#FFFFFF"], [1, "#AEB6C1"]], 0, 1, T.INK),
        "deep": ([[0, "#EE7B4A"], [1, "#A93A0C"]], DEEP, 25, "white"),
        "below": ([[0, "#FDEDE4"], [1, "#F4A47E"]], 0, DEEP, T.INK),
        "above": ([[0, "#E9EEF4"], [1, "#9DB0C6"]], 1, 30, T.INK),
        "at": ([[0, "#F3F4F6"], [1, "#F3F4F6"]], 0, 1, T.INK),
    }
    fig = go.Figure()
    for name, (Z, TX, HV) in layers.items():
        scale, lo, hi, color = styles[name]
        fig.add_trace(go.Heatmap(x=xs, y=keys, z=Z, text=TX, hovertext=HV, texttemplate="%{text}",
                                 textfont=dict(size=10, color=color, family=T.FONT), colorscale=scale, zmin=lo,
                                 zmax=hi, showscale=False, xgap=2, ygap=2, name=name,
                                 hovertemplate="%{hovertext}<extra></extra>"))

    for ln in LINES:
        d = g["lines"][ln]
        sets_date = ln == g["limit"]
        held = f"at target from {fdate(d['held'])}" if d["held"] is not None else "not at target by the end"
        fig.add_annotation(x=1, xref="paper", xanchor="left", xshift=8, y=f"L:{ln}", yref="y", showarrow=False,
                           text=f"<b>{held}</b>" if sets_date or d["held"] is None else held,
                           font=dict(size=11, color=T.ACCENT if sets_date or d["held"] is None else T.MUTED))
        if d["events"]:
            top, bottom = row_of[f"L:{ln}"], row_of[f"S:{ln}:{d['rows'][-1]['label']}"]
            a, b = min(d["events"]) + 1, max(d["events"]) + 1
            fig.add_shape(type="rect", x0=a - 0.5, x1=b + 0.5, y0=top - 0.5, y1=bottom + 0.5, xref="x", yref="y",
                          line=dict(color=T.ACCENT, width=2), fillcolor="rgba(0,0,0,0)", layer="above")

    ticks = ["Start"] + [p.strftime("%b<br>%Y") if (j == 0 or p.month == 1) else p.strftime("%b")
                         for j, p in enumerate(months)]
    fig.update_layout(height=ROW * len(keys) + 56, margin=dict(l=8, r=150, t=44, b=6), plot_bgcolor="white",
                      paper_bgcolor="white", font=dict(family=T.FONT, color=T.INK, size=11), showlegend=False,
                      hovermode="closest", hoverlabel=dict(font=dict(family=T.FONT, size=12), bgcolor="white"))
    fig.update_xaxes(side="top", tickvals=xs, ticktext=ticks, showgrid=False, zeroline=False, ticks="",
                     tickfont=dict(size=10, color=T.MUTED), range=[-0.5, n - 0.5], fixedrange=True)
    fig.update_yaxes(tickvals=keys, ticktext=labels, autorange="reversed", showgrid=False, zeroline=False, ticks="",
                     tickfont=dict(size=11, color=T.INK), fixedrange=True)
    return fig
