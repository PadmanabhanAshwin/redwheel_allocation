"""The scenario chart: one panel per line, by month.

    plan_figure    bikes built stacked by bike, forecast, capacity, open orders at month end; per line its build time
                   and the date it holds target from, marked as a dotted line; the months a change applies shaded
                   (the deck's chart)"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from planner2_demo.reading import LINE_WORDS, MONTH, MONTHS, change_weeks, fdate, monthly_stack, plan_reading
from ui import LINES, SIZE_RANK, SKU, cell, style

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
