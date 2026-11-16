"""Charts by month (bikes per week, averaged over the month), one panel per line.

    plan_figure    one plan, monthly totals: bikes built stacked by bike, forecast, capacity, open orders at month end;
                   the at-target date per line
    side_by_side_figure   two plans, by quarter or month: for each line that moved, the reference's builds (faded)
                          beside the scenario's, stacked by bike; material differences labelled
    ahead_figure          two plans, week by week: cumulative builds of the scenario ahead of or behind the reference,
                          per bike and per line; the weeks a change applies shaded"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from planner2.reading import LINE_WORDS, MONTHS, ahead_behind, built_by_period, change_weeks, compare_periods, \
    fdate, monthly_stack, period_labels, plan_reading
from ui import GRID, LINES, SIZE_RANK, SKU, WEEKS, cell, style

X = [p.to_timestamp() for p in MONTHS]
WEEK_X = list(WEEKS)
BAR_MS = 24 * 24 * 3600 * 1000
# Ordinal blue ramp for bike size (steps 250 / 450 / 650 of the reference sequential blue), the reference's second
# categorical hue for the forecast, ink for capacity, red diamonds (shape as well as colour) for open orders.
SIZE = {"S": "#86b6ef", "M": "#2a78d6", "L": "#104281"}
FORECAST_LINE, CAPACITY_LINE, OPEN_MARK = "#eb6834", "#0b0b0b", "#e34948"


def _grid(titles) -> go.Figure:
    return make_subplots(rows=2, cols=2, subplot_titles=titles, shared_xaxes=True, vertical_spacing=0.14,
                         horizontal_spacing=0.07)


def _titles(V) -> list:
    held = plan_reading(V)["lines"]
    return [f"<b>{LINE_WORDS[ln]}</b> · at target {fdate(held[ln]['held_from'])}" for ln in LINES]


def plan_figure(V) -> go.Figure:
    """Per line, by month: bikes built stacked by bike (coloured by size), forecast demand, capacity (dashed), and
    open orders at month end (markers, where any are waiting)."""
    fig = _grid(_titles(V))
    shown = set()
    for i, ln in enumerate(LINES):
        d, at, first = monthly_stack(V, ln), cell(i), i == 0
        for s, y in d["built"].items():
            size = SKU.at[s, "size"]
            fig.add_bar(x=X, y=y, width=BAR_MS, name=f"size {size}", marker_color=SIZE[size],
                        marker_line=dict(color="white", width=1),
                        legendgroup=size, legendrank=SIZE_RANK[size], showlegend=size not in shown,
                        hovertemplate=f"{s}: %{{y:,.0f}}<extra></extra>", **at)
            shown.add(size)
        fig.add_scatter(x=X, y=d["demand"], name="forecast", legendgroup="d", legendrank=10, showlegend=first,
                        line=dict(color=FORECAST_LINE, width=2), hovertemplate="forecast %{y:,.0f}<extra></extra>", **at)
        fig.add_scatter(x=X, y=d["capacity"], name="capacity", line_shape="hvh", legendgroup="c", legendrank=11,
                        showlegend=first, line=dict(color=CAPACITY_LINE, width=1.4, dash="dash"),
                        hovertemplate="capacity %{y:,.0f}<extra></extra>", **at)
        oo = [v if v > 0.5 else None for v in d["open_orders"]]
        fig.add_scatter(x=X, y=oo, name="open orders, month end", mode="markers", legendgroup="o", legendrank=12,
                        showlegend=first, marker=dict(symbol="diamond", size=9, color=OPEN_MARK,
                                                      line=dict(color="white", width=1.5)),
                        hovertemplate="open orders %{y:,.0f}<extra></extra>", **at)
    fig.update_yaxes(rangemode="tozero")
    fig.update_yaxes(title_text="bikes per month", col=1)
    fig.update_layout(barmode="stack")
    return style(fig, 540)


def _date_title(V, V0, ln) -> str:
    k0 = V0["case"].key
    a, b = plan_reading(V0)["lines"][ln]["held_from"], plan_reading(V)["lines"][ln]["held_from"]
    w = None if a is None or b is None else round((b - a).days / 7)
    return f"<b>{LINE_WORDS[ln]}</b> · at target {fdate(b)}" + (f" ({w:+d} wk vs {k0})" if w else f", same as {k0}")


def _stacked_rows(n: int, panel: int, gap: int, cols: int = 1, **kw):
    """make_subplots with fixed panel and gap heights in pixels, so many lines do not squash the panels."""
    rows = -(-n // cols)
    inner = rows * panel + (rows - 1) * gap
    return rows, inner, dict(rows=rows, cols=cols, vertical_spacing=gap / inner if rows > 1 else 0.1, **kw)


def side_by_side_figure(V, V0, lines: list, level: str) -> go.Figure:
    """For each line that moved, per period: the reference's builds (faded) beside the scenario's (solid), both
    stacked by bike; the difference in bikes labelled where it is material."""
    k, k0 = V["case"].key, V0["case"].key
    x = [lab for lab, _ in compare_periods(level)]
    rows, inner, kw = _stacked_rows(len(lines), 210, 78)
    fig = make_subplots(subplot_titles=[_date_title(V, V0, ln) for ln in lines], **kw)
    shown = set()
    for i, ln in enumerate(lines, start=1):
        for grp, Vx, alpha in ((k0, V0, 0.35), (k, V, 1.0)):
            base = None
            for s_, y in built_by_period(Vx, ln, level).items():
                size = SKU.at[s_, "size"]
                fig.add_bar(x=x, y=y, base=base, offsetgroup=grp, name=f"size {size}", marker_color=SIZE[size],
                            opacity=alpha, marker_line=dict(color="white", width=1), legendgroup=size,
                            legendrank=SIZE_RANK[size], showlegend=grp == k and size not in shown,
                            hovertemplate=f"{grp} · {s_}: %{{y:,.0f}}<extra></extra>", row=i, col=1)
                base = y if base is None else [b_ + y_ for b_, y_ in zip(base, y)]
                if grp == k:
                    shown.add(size)
        lab = period_labels(V, V0, ln, level)
        fig.add_scatter(x=[p for p, _, _ in lab], y=[t for _, _, t in lab], mode="text", showlegend=False,
                        text=[f"{d:+,.0f}".replace("-", "−") for _, d, _ in lab], textposition="top center", hoverinfo="skip",
                        textfont=dict(size=11, color=CAPACITY_LINE), cliponaxis=False, row=i, col=1)
    fig.update_layout(barmode="group", bargap=0.28, bargroupgap=0.06)
    fig.update_xaxes(tickangle=0, tickfont=dict(size=10), tickvals=x if level == "Quarter" else x[::3])
    style(fig, inner + 92)
    fig.update_yaxes(rangemode="tozero")
    fig.update_yaxes(title_text="bikes built", col=1)
    return fig


def ahead_figure(V, V0, lines: list) -> go.Figure:
    """For each line that moved: cumulative bikes built, scenario minus reference, week by week, per bike (blues) and
    for the line (ink), all panels on one scale; the weeks a change applies shaded."""
    k, k0 = V["case"].key, V0["case"].key
    cols = min(2, len(lines))
    rows, inner, kw = _stacked_rows(len(lines), 220, 64, cols=cols)
    fig = make_subplots(subplot_titles=[f"<b>{LINE_WORDS[ln]}</b>" for ln in lines], shared_yaxes="all",
                        horizontal_spacing=0.05, **kw)
    x = WEEK_X
    shown = set()
    for i, ln in enumerate(lines):
        at = dict(row=i // cols + 1, col=i % cols + 1)
        d = ahead_behind(V, V0, ln)
        for s_, y in d.items():
            if s_ == "line":
                continue
            size = SKU.at[s_, "size"]
            fig.add_scatter(x=x, y=y, name=f"size {size}", line=dict(color=SIZE[size], width=1.6), line_shape="hv",
                            legendgroup=size, legendrank=SIZE_RANK[size], showlegend=size not in shown,
                            hovertemplate=f"{s_}: %{{y:+,.0f}}<extra></extra>", **at)
            shown.add(size)
        fig.add_scatter(x=x, y=d["line"], name="line total", line=dict(color=CAPACITY_LINE, width=2.4),
                        line_shape="hv", legendgroup="t", legendrank=20, showlegend=i == 0,
                        hovertemplate="line: %{y:+,.0f}<extra></extra>", **at)
    style(fig, inner + 92)
    fig.update_yaxes(zeroline=True, zerolinecolor="#808495", zerolinewidth=1)
    fig.update_yaxes(title_text=f"bikes, {k} − {k0}", col=1)
    bands = [(i, ab) for i, ln in enumerate(lines) for ab in change_weeks(V, V0, ln)]
    for i, (a, b) in bands:
        fig.add_vrect(x0=x[a - 1], x1=x[b - 1] + pd.Timedelta(days=7), fillcolor=GRID, opacity=1, layer="below",
                      line_width=0, exclude_empty_subplots=False, row=i // cols + 1, col=i % cols + 1)
    if bands:                                         # the band's legend entry; it draws nothing
        fig.add_bar(x=[None], y=[None], name="weeks changed", marker_color=GRID, legendrank=30, hoverinfo="skip",
                    row=1, col=1)
    return fig
