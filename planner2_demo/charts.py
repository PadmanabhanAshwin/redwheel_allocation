"""The two charts: one plan by month, and two plans against the target by week.

    plan_figure    bikes built stacked by bike, forecast, capacity, open orders at month end; per line its build time
                   and the date it holds target from, marked as a dotted line; the months a change applies shaded
                   (the deck's chart)
    supply_figure  two plans: weeks of supply against target for each line that moved (bike by bike when a plan
                   re-mixes a line), the gap shaded, customers waiting below zero, the dates each is at target from"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from planner2_demo.reading import LINE_WORDS, MONTH, MONTHS, change_weeks, fdate, monthly_stack, plan_reading, \
    supply_rows
from ui import LINES, MUTED as MUTED_INK, SIZE_RANK, SKU, WEEKS, cell, style

X = [p.to_timestamp() for p in MONTHS]
TICKS = [m.strftime("%b")[0] + (f"<br>{m.year}" if i == 0 or m.month == 1 else "") for i, m in enumerate(X)]
BAR_MS = 24 * 24 * 3600 * 1000
# Ordinal blue ramp for bike size (steps 250 / 450 / 650 of the reference sequential blue), the reference's second
# categorical hue for the forecast, ink for capacity, red diamonds (shape as well as colour) for open orders.
SIZE = {"S": "#86b6ef", "M": "#2a78d6", "L": "#104281"}
FORECAST_LINE, CAPACITY_LINE, OPEN_MARK = "#eb6834", "#0b0b0b", "#e34948"
CHANGED = "#f6e3e3"                  # the deck's shading of the months a change applies (red at 12%)
HALF_MONTH = pd.Timedelta(days=15)


def _grid(titles) -> go.Figure:
    return make_subplots(rows=2, cols=2, subplot_titles=titles, shared_xaxes=True, vertical_spacing=0.14,
                         horizontal_spacing=0.07)


def _titles(V) -> list:
    held, bw = plan_reading(V)["lines"], V["case"].build_weeks
    return [f"<b>{LINE_WORDS[ln]}</b>   build time {bw[ln]:g} wk · target held {fdate(held[ln]['held_from'])}"
            for ln in LINES]


def months_shown(V) -> int:
    """The chart's months from the start: through Dec 2027 (as the deck), or two months past the last line's
    at-target date when that is later; the build plan table and the CSV keep the whole plan."""
    held = [d["held_from"] for d in plan_reading(V)["lines"].values()]
    last = max([MONTHS.index(pd.Timestamp(h).to_period("M")) for h in held if h is not None] or [len(MONTHS) - 1])
    if any(h is None for h in held):
        last = len(MONTHS) - 1
    return min(len(MONTHS), max(MONTHS.index(pd.Period("2027-12", "M")) + 1, last + 3))


def plan_figure(V, V0=None) -> go.Figure:
    """Per line, by month: bikes built stacked by bike (coloured by size), forecast demand, capacity (dashed), and
    open orders at month end (markers, where any are waiting). V0: the scenario V is built on; the months in which a
    dated change of V's (one V0 does not have) applies are shaded."""
    fig = _grid(_titles(V))
    shown, held, shaded = set(), plan_reading(V)["lines"], False
    n = months_shown(V)
    x = X[:n]
    for i, ln in enumerate(LINES):
        d, at, first = {k: (v[:n] if isinstance(v, list) else {s_: y[:n] for s_, y in v.items()})
                        for k, v in monthly_stack(V, ln).items()}, cell(i), i == 0
        for s, y in d["built"].items():
            size = SKU.at[s, "size"]
            fig.add_bar(x=x, y=y, width=BAR_MS, name=f"size {size}", marker_color=SIZE[size],
                        marker_line=dict(color="white", width=1),
                        legendgroup=size, legendrank=SIZE_RANK[size], showlegend=size not in shown,
                        hovertemplate=f"{s}: %{{y:,.0f}}<extra></extra>", **at)
            shown.add(size)
        fig.add_scatter(x=x, y=d["demand"], name="forecast", mode="lines", legendgroup="d", legendrank=10, showlegend=first,
                        line=dict(color=FORECAST_LINE, width=2), hovertemplate="forecast %{y:,.0f}<extra></extra>", **at)
        fig.add_scatter(x=x, y=d["capacity"], name="capacity", mode="lines", line_shape="hvh", legendgroup="c", legendrank=11,
                        showlegend=first, line=dict(color=CAPACITY_LINE, width=1.4, dash="dash"),
                        hovertemplate="capacity %{y:,.0f}<extra></extra>", **at)
        oo = [v if v > 0.5 else None for v in d["open_orders"]]
        fig.add_scatter(x=x, y=oo, name="open orders, month end", mode="markers", legendgroup="o", legendrank=12,
                        showlegend=first, marker=dict(symbol="diamond", size=9, color=OPEN_MARK,
                                                      line=dict(color="white", width=1.5)),
                        hovertemplate="open orders %{y:,.0f}<extra></extra>", **at)
        months = sorted({MONTHS.index(MONTH[t]) for a, b in (change_weeks(V, V0, ln) if V0 else [])
                         for t in range(a, b + 1)})
        for m in [m for m in months if m < n]:
            fig.add_vrect(x0=X[m] - HALF_MONTH, x1=X[m] + HALF_MONTH, fillcolor=CHANGED, opacity=1, layer="below",
                          line_width=0, **at)
            shaded = True
        h = held[ln]["held_from"]
        if h is not None and h < X[n - 1] + pd.offsets.MonthEnd(1):   # the week it holds target from
            fig.add_vline(x=h, line=dict(color=CAPACITY_LINE, width=1.2, dash="dot"), **at)
    fig.add_scatter(x=[None], y=[None], mode="lines", name="target held", legendrank=13,
                    line=dict(color=CAPACITY_LINE, width=1.2, dash="dot"), **cell(0))
    if shaded:
        fig.add_scatter(x=[None], y=[None], mode="markers", name="weeks changed", legendrank=14, hoverinfo="skip",
                        marker=dict(symbol="square", size=12, color=CHANGED), **cell(0))
    fig.update_yaxes(rangemode="tozero")
    fig.update_xaxes(tickvals=x, ticktext=TICKS[:n], tickfont=dict(size=10), tickangle=0)
    fig.update_layout(barmode="stack")
    style(fig, 560)
    fig.update_annotations(font=dict(size=13))
    return fig


# ---------------- two plans: weeks of supply against target ----------------

REF_LINE, SCEN_LINE, WAITING = "#8a909c", "#2a78d6", "#fbeaea"
BEHIND, AHEAD = "rgba(185,28,28,0.20)", "rgba(21,128,61,0.22)"


def supply_figure(V, V0):
    """One panel per line that moved (bike by bike where a plan re-mixes a line's bikes): weeks of supply of both
    plans against the target, the gap shaded (red where V is behind V0, green where ahead), customers waiting below
    zero, and the date each plan is at target from. None when nothing moved by half a week."""
    rows, end = supply_rows(V, V0)
    if not rows:
        return None
    k, k0 = V["case"].key, V0["case"].key
    n = len(rows)
    cols = {1: 1, 2: 2, 3: 3, 4: 2}.get(n, 3)
    nr = -(-n // cols)
    panel, gap, top, bottom = 200, 64, 78, 8
    inner = nr * panel + (nr - 1) * gap
    fig = make_subplots(rows=nr, cols=cols, subplot_titles=[r["title"] for r in rows], shared_yaxes="all",
                        horizontal_spacing=0.05, vertical_spacing=gap / inner if nr > 1 else 0.1)
    x = [WEEKS[t] for t in range(1, end + 1)]
    lo = min(min(r["a"][:end].min(), r["b"][:end].min()) for r in rows)
    tmax = max(r["target"][:end].max() for r in rows)
    hi = min(max(max(r["a"][:end].max(), r["b"][:end].max()) for r in rows), tmax + 6)
    shown = set()
    rank = {k: 1, k0: 2, "target": 3, f"{k} behind {k0}": 4, f"{k} ahead of {k0}": 5}

    def legend(name):
        first = name not in shown
        shown.add(name)
        return dict(name=name, legendgroup=name, showlegend=first, legendrank=rank[name])

    for i, r in enumerate(rows):
        at = dict(row=i // cols + 1, col=i % cols + 1)
        a, b, t = r["a"][:end], r["b"][:end], r["target"][:end]
        fig.add_hrect(y0=lo - 5, y1=0, fillcolor=WAITING, line_width=0, layer="below", exclude_empty_subplots=False,
                      **at)
        for edge, colour, name in ((np.minimum(a, b), BEHIND, f"{k} behind {k0}"),
                                   (np.maximum(a, b), AHEAD, f"{k} ahead of {k0}")):
            if np.abs(edge - a).max() < 1e-9:
                continue
            fig.add_scatter(x=x, y=a, mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip", **at)
            fig.add_scatter(x=x, y=edge, mode="lines", line=dict(width=0), fill="tonexty", fillcolor=colour,
                            hoverinfo="skip", **legend(name), **at)
        fig.add_scatter(x=x, y=t, mode="lines", line=dict(color=CAPACITY_LINE, width=1, dash="dash"), line_shape="hv",
                        hovertemplate="target %{y:.1f} wk<extra></extra>", **legend("target"), **at)
        fig.add_scatter(x=x, y=a, mode="lines", line=dict(color=REF_LINE, width=1.6, dash="dot"),
                        hovertemplate=f"{k0} %{{y:.1f}} wk<extra></extra>", **legend(k0), **at)
        fig.add_scatter(x=x, y=b, mode="lines", line=dict(color=SCEN_LINE, width=2.2),
                        hovertemplate=f"{k} %{{y:.1f}} wk<extra></extra>", **legend(k), **at)
        h0, h = r["held"]
        early = h is not None and h0 is not None and h < h0          # the labels point away from each other
        for w, colour, pos, same in ((h0, REF_LINE, "bottom right" if early else "bottom left", h0 == h),
                                     (h, SCEN_LINE, "bottom left" if early else "bottom right", False)):
            if w is None or w > end or same:
                continue
            fig.add_scatter(x=[WEEKS[w]], y=[t[w - 1]], mode="markers+text", marker=dict(size=8, color=colour),
                            text=[fdate(WEEKS[w])], textposition=pos, cliponaxis=False, showlegend=False,
                            textfont=dict(size=10, color=MUTED_INK if colour == REF_LINE else CAPACITY_LINE),
                            hovertemplate=f"at target from {fdate(WEEKS[w])}<extra></extra>", **at)
    fig.add_scatter(x=[None], y=[None], mode="markers", marker=dict(symbol="square", size=11, color=WAITING),
                    name="below 0: customers waiting", legendrank=1000, row=1, col=1)
    style(fig, inner + top + bottom)
    fig.update_layout(margin=dict(l=8, r=8, t=top, b=bottom), hovermode="closest",
                      legend=dict(orientation="h", x=0, y=1 + 46 / inner, yanchor="bottom"))
    fig.update_yaxes(range=[lo - 1, hi + 2.5], zeroline=False)
    fig.update_yaxes(title_text="weeks of supply", col=1)
    fig.update_xaxes(range=[x[0] - pd.Timedelta(days=3), x[-1] + pd.Timedelta(days=3)], tickformat="%b %Y",
                     tickfont=dict(size=10))
    fig.update_annotations(font=dict(size=13))
    return fig
