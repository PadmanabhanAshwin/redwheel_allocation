"""The two charts: the build plan by month, and the supply map by week.

    plan_figure    bikes built stacked by bike, forecast, capacity, open orders at month end; per line its build time
                   and the date it holds target from, marked as a dotted line; the months a change applies shaded
                   (the deck's chart)
    supply_map_figure   every bike, week by week: customers waiting, below target, at target; one plan, or two one
                        above the other on one time axis, the second the reference"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from planner2_demo.reading import LINE_WORDS, MONTH, MONTHS, change_weeks, fdate, map_end, minus, monthly_stack, \
    plan_reading, supply_map
from ui import LINES, SIZE_RANK, SKU, WEEKS, cell, style

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




# ---------------- the supply map: every bike, every week, against its target ----------------

MAP_SCALE = [[0.0, "#8f1d1d"], [0.33, "#f3c9c9"], [0.3334, "#8d939e"], [0.66, "#e6e8ec"],
             [0.6667, "#bfe1c7"], [1.0, "#7fb88f"]]
STATES = (("customers waiting", "#c25a5a"), ("below target", "#b4b9c2"), ("at target", "#a9d5b4"))
STATE_AT = ("customers waiting", "below target", "at target")
ROW_PX, GAP_PX, TOP_PX, BOTTOM_PX = 16, 50, 66, 28


def _map_rows(rows) -> list:
    """The map's rows, top to bottom: each line's name, then its bikes. [(label, row or None)]"""
    out = []
    for ln in LINES:
        out.append((f"<b>{LINE_WORDS[ln]}</b>", None))
        out += [(r["label"], r) for r in rows if r["line"] == ln]
    return out


def _hover(r, x) -> list:
    words = [STATE_AT[min(int(z), 2)] for z in r["z"]]
    return [f"{r['label']} · week of {fdate(d)} · {s} · weeks of supply {w:.1f}, target {t:g}"
            for d, s, w, t in zip(x, words, r["wos"], r["target"])]


def supply_map_figure(V, V0=None, against=None) -> go.Figure:
    """The supply map: every bike, under its line, week by week: customers waiting (red, darker the deeper), below
    target (grey, darker the further), at target (green, darker the further above); each bike's at-target date on
    the right. With V0: V's map above V0's on one time axis, V's dates with their shift against V0. The weeks a
    change of V's applies (one that V0, or `against`, does not have) are outlined on V's map."""
    plans = [V] + ([V0] if V0 is not None else [])
    against = V0 if V0 is not None else against
    end = map_end(*plans)
    x = [WEEKS[t] for t in range(1, end + 1)]
    maps = [supply_map(P, end) for P in plans]
    n, nrows = len(plans), len(_map_rows(maps[0]))
    inner = n * nrows * ROW_PX + (n - 1) * GAP_PX
    titles = [f"<b>{P['case'].key}</b> · {P['case'].name.split(' · ', 1)[-1]}" for P in plans] if n > 1 else None
    top = TOP_PX if n > 1 else 40                         # one map: the page names the plan
    fig = make_subplots(rows=n, cols=1, shared_xaxes=True, vertical_spacing=GAP_PX / inner if n > 1 else 0.1,
                        subplot_titles=titles)
    half = pd.Timedelta(days=3.5)
    for i, rows in enumerate(maps):
        mr = _map_rows(rows)
        labels = [lab for lab, _ in mr]
        z = [r["z"] if r else [None] * end for _, r in mr]
        text = [_hover(r, x) if r else [""] * end for _, r in mr]
        fig.add_heatmap(z=z, x=x, y=labels, text=text, hovertemplate="%{text}<extra></extra>", hoverongaps=False,
                        colorscale=MAP_SCALE, zmin=0, zmax=3, showscale=False, xgap=0, ygap=1, row=i + 1, col=1)
        fig.update_yaxes(categoryorder="array", categoryarray=labels, autorange="reversed", tickfont=dict(size=11),
                         showgrid=False, ticks="", row=i + 1, col=1)
        if i == 0 and against is not None:
            for ln in LINES:
                idx = [j for j, (_, r) in enumerate(mr) if r and r["line"] == ln]
                for a, b in change_weeks(V, against, ln):
                    if a <= end:
                        fig.add_shape(type="rect", x0=WEEKS[a] - half, x1=WEEKS[min(b, end)] + half,
                                      y0=idx[0] - 0.5, y1=idx[-1] + 0.5, line=dict(color=CAPACITY_LINE, width=1.4,
                                      dash="dot"), fillcolor="rgba(0,0,0,0)", row=1, col=1)
    for name, colour in STATES:
        fig.add_scatter(x=[None], y=[None], mode="markers", name=name, marker=dict(symbol="square", size=11,
                        color=colour), row=1, col=1)
    if any(s.type == "rect" for s in fig.layout.shapes):
        fig.add_scatter(x=[None], y=[None], mode="markers", name="weeks changed", row=1, col=1,
                        marker=dict(symbol="square-open", size=11, color=CAPACITY_LINE))
    style(fig, inner + top + BOTTOM_PX)
    fig.update_layout(margin=dict(l=8, r=128, t=top, b=BOTTOM_PX), hovermode="closest",
                      legend=dict(orientation="h", x=0, y=1 + (34 if n > 1 else 8) / inner, yanchor="bottom"))
    fig.update_xaxes(tickformat="%b %Y", tickfont=dict(size=10), showgrid=False)
    fig.update_annotations(font=dict(size=13))
    held0 = {r["sku"]: r["held"] for r in maps[1]} if n > 1 else {}
    for i, rows in enumerate(maps):
        for r in rows:
            h = r["held"]
            text = fdate(WEEKS[h]) if h else "not held"
            if i == 0 and n > 1:
                h0 = held0[r["sku"]]
                if h and h0 and h != h0:
                    colour = "#b42318" if h > h0 else "#1e7b3a"
                    text += f"  <span style='color:{colour}'><b>{minus(f'{h - h0:+d} wk')}</b></span>"
                elif (h is None) != (h0 is None):
                    text += "  <span style='color:#b42318'><b>changed</b></span>"
            fig.add_annotation(x=1, xref="paper", xanchor="left", xshift=8, y=r["label"],
                               yref="y" if i == 0 else f"y{i + 1}", text=text, showarrow=False,
                               font=dict(size=10, color=CAPACITY_LINE))
    return fig
