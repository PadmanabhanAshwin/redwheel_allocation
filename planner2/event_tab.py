"""The Events tab of the Scenario page: what an event changed in the data, what the plan did about it, and the line it
hit, week by week, against the scenario it is compared with.

Everything is read from the scenario's own computed plan (its object, its change report and its results); nothing is
recomputed here. The event weeks are shaded on both charts."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from planner2 import charts, events as ev, state
from planner2.charts import LINE_WORDS
from redwheel.config import LINES
from ui import BAD_BG, CAPACITY, FORECAST, H, HISTORY, INK, SIZE_COLOR, SKUS_BY_LINE, WEEKS, fmt_date, right_align, style

MARGIN = 8                                   # weeks shown either side of the event and of the plans' difference
MIN_BIKES = 1                                # the plans differ in a week if the line's builds differ by a bike ...
MIN_WEEKS_OF_SUPPLY = 0.1                    # ... or its lowest weeks of supply by this much (less cannot be seen)
WEEK_MS = 6 * 24 * 3600 * 1000               # bar width on a date axis: six days


def _builds(V, ln) -> np.ndarray:
    """Bikes built on a line in weeks 1..H."""
    return V["built"].loc[SKUS_BY_LINE[ln]].sum().to_numpy(float)


def _lowest(V, ln):
    """(weeks of supply, target) for weeks 1..H of the position on the line furthest below its target that week: the
    line is below target exactly when this is."""
    R = V["R"]
    idx = R["wos"].index[R["line"].reindex(R["wos"].index).values == ln]
    w, tg = R["wos"].loc[idx, 1:H].to_numpy(float), R["target_wos"].loc[idx, 1:H].to_numpy(float)
    k = (w - tg).argmin(axis=0)
    cols = np.arange(w.shape[1])
    return w[k, cols], tg[k, cols]


def shades(V, ln) -> list:
    """(first week, last week) of each event on this line that changes weekly numbers, within the plan."""
    obj = V["R"]["obj"]
    return [(c.from_t, min(c.to_t, H)) for c in V["case"].changes
            if c.field == "arrival" and c.from_t <= H and ln in ev.lines_of(c, obj)]


def window(V, V0, ln, spans) -> tuple:
    """Weeks to show: from MARGIN weeks before the first week that matters to MARGIN weeks after the last, where a
    week matters if an event is on it or the plan differs there from the compared scenario's."""
    weeks = {t for a, b in spans for t in range(a, b + 1)}
    if V0 is not None:
        differs = (np.abs(_builds(V, ln) - _builds(V0, ln)) >= MIN_BIKES) | \
                  (np.abs(_lowest(V, ln)[0] - _lowest(V0, ln)[0]) >= MIN_WEEKS_OF_SUPPLY)
        weeks |= {int(t) + 1 for t in np.flatnonzero(differs)}
    if not weeks:
        return 1, H
    lo, hi = max(1, min(weeks) - MARGIN), min(H, max(weeks) + MARGIN)
    return (lo, hi) if hi - lo >= 12 else (max(1, hi - 12), hi)


def _shade(fig, spans, lo, hi):
    for a, b in spans:
        a, b = max(a, lo), min(b, hi)
        if a <= b:
            fig.add_vrect(x0=pd.Timestamp(WEEKS[a]), x1=pd.Timestamp(WEEKS[b]) + pd.Timedelta(days=7),
                          fillcolor=BAD_BG, opacity=1, layer="below", line_width=0)


def _weeks_vs(held, held0) -> str:
    """How much later (+) or earlier (-) a line holds its targets than in the compared scenario."""
    if held == held0:
        return "same"
    if held is None or held0 is None:
        return "never held" if held is None else "was never held"
    return f"{round((held - held0).days / 7):+d} wk"


def effect_table(V, V0) -> pd.DataFrame:
    """Per line: bikes built and the date it holds its targets from, with the change against the compared scenario."""
    rd = charts.plan_reading(V)["lines"]
    rd0 = charts.plan_reading(V0)["lines"] if V0 is not None else None
    vs = V0["case"].key if V0 is not None else ""
    rows = []
    for ln in LINES:
        built, held = int(_builds(V, ln).sum()), rd[ln]["held_from"]
        row = {"Line": LINE_WORDS[ln], "Bikes built": f"{built:,}"}
        if V0 is not None:
            d = built - int(_builds(V0, ln).sum())
            row[f"Built vs {vs}"] = f"{d:+,}" if d else "same"
        row["Holds targets from"] = fmt_date(held) if held is not None else "never"
        if V0 is not None:
            row[f"Date vs {vs}"] = _weeks_vs(held, rd0[ln]["held_from"])
        rows.append(row)
    return pd.DataFrame(rows).set_index("Line")


def builds_figure(V, V0, ln, lo, hi, spans) -> go.Figure:
    x, s = WEEKS.loc[lo:hi], slice(lo - 1, hi)
    cap, built = charts.capacity(V, ln), _builds(V, ln)
    fig = go.Figure()
    _shade(fig, spans, lo, hi)
    fig.add_bar(x=x, y=built[s], width=WEEK_MS, name="built", marker_color=SIZE_COLOR["L"], marker_line_width=0,
                hovertemplate="built: %{y:,.0f}<extra></extra>")
    if V0 is not None:
        fig.add_scatter(x=x, y=_builds(V0, ln)[s], name=f"built · {V0['case'].key}", line_shape="hv",
                        line=dict(color=HISTORY, width=1.8), hovertemplate="built: %{y:,.0f}<extra></extra>")
    fig.add_scatter(x=x, y=cap[s], name="capacity", line_shape="hv", line=dict(color=CAPACITY, width=2),
                    hovertemplate="capacity: %{y:,.0f}<extra></extra>")
    if V0 is not None and not np.array_equal(charts.capacity(V0, ln), cap):
        fig.add_scatter(x=x, y=charts.capacity(V0, ln)[s], name=f"capacity · {V0['case'].key}", line_shape="hv",
                        line=dict(color=HISTORY, width=1.4, dash="dot"), hovertemplate="capacity: %{y:,.0f}<extra></extra>")
    top = max([cap[s].max(), built[s].max()] + ([_builds(V0, ln)[s].max()] if V0 is not None else []))
    fig.update_yaxes(range=[0, top * 1.12])
    return style(fig, 330, ytitle="bicycles per week")


def supply_figure(V, V0, ln, lo, hi, spans) -> go.Figure:
    x, s = WEEKS.loc[lo:hi], slice(lo - 1, hi)
    low, tgt = _lowest(V, ln)
    fig = go.Figure()
    _shade(fig, spans, lo, hi)
    fig.add_scatter(x=x, y=low[s], name="lowest weeks of supply", line_shape="hv", line=dict(color=INK, width=2.2),
                    hovertemplate="lowest: %{y:,.1f} wk<extra></extra>")
    fig.add_scatter(x=x, y=tgt[s], name="target", line_shape="hv", line=dict(color=FORECAST, width=1.6, dash="dash"),
                    hovertemplate="target: %{y:,.1f} wk<extra></extra>")
    if V0 is not None:
        low0, tgt0 = _lowest(V0, ln)
        fig.add_scatter(x=x, y=low0[s], name=f"lowest · {V0['case'].key}", line_shape="hv",
                        line=dict(color=HISTORY, width=1.8), hovertemplate="lowest: %{y:,.1f} wk<extra></extra>")
        if not np.array_equal(tgt0, tgt):
            fig.add_scatter(x=x, y=tgt0[s], name=f"target · {V0['case'].key}", line_shape="hv",
                            line=dict(color=FORECAST, width=1.2, dash="dot"), hovertemplate="target: %{y:,.1f} wk<extra></extra>")
    return style(fig, 330, ytitle="weeks of supply")


def render(V: dict, V0: dict | None, key: str, case) -> None:
    if not case.changes:
        st.info("This scenario has no events: it plans from the data as given.", icon=":material/info:")
        if st.button("Add an event", icon=":material/bolt:", key="ev_tab_add",
                     help="Start a what-if from this scenario, with the Events card"):
            state.new_draft(key)
            st.switch_page("whatif.py")
        return

    obj, rep = V["R"]["obj"], V["R"]["change_report"]
    st.markdown("#### What changed in the data")
    st.dataframe(ev.table(case.changes, rep), hide_index=True, width="stretch",
                 column_config={"Event": st.column_config.TextColumn(width="large"),
                                "Change": st.column_config.TextColumn(width="small"),
                                "Numbers changed": st.column_config.NumberColumn(width="medium"),
                                "From": st.column_config.TextColumn(width="small"),
                                "To": st.column_config.TextColumn(width="small"),
                                "Why": st.column_config.TextColumn(width="large")})
    chk = V["checks"]
    st.caption("From and To add up the numbers each event changed (weekly bikes of capacity or orders, or bikes in "
               "stock); everything else in the data is as given. Before planning, every event is checked: the resources "
               "exist, the weeks are inside the data, no number goes below zero and each changes at least one number. "
               f"Plan checks: {int(chk['pass'].sum())} of {len(chk)} pass.")

    st.markdown("#### What the plan did")
    st.dataframe(right_align(effect_table(V, V0)), width="stretch")
    st.caption("Per line: bikes built over the plan and the first week from which every SKU on the line holds its "
               "target to the end" + (f", against {V0['case'].name}." if V0 is not None else "."))

    touched = [ln for c in case.changes for ln in ev.lines_of(c, obj)]
    c1, c2, _ = st.columns([2, 3, 3], vertical_alignment="bottom")
    ln = c1.selectbox("Line", list(LINES), index=list(LINES).index(touched[0]) if touched else 0,
                      key=f"evline_{key}", format_func=LINE_WORDS.get)
    zoom = c2.radio("Show", ["Around the events", "Whole plan"], horizontal=True, key=f"evwin_{key}")
    spans = shades(V, ln)
    lo, hi = window(V, V0, ln, spans) if zoom == "Around the events" else (1, H)
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown(f"**{LINE_WORDS[ln]}: weekly builds against capacity**")
        st.plotly_chart(builds_figure(V, V0, ln, lo, hi, spans), key=f"evb_{key}_{ln}")
    with right:
        st.markdown(f"**{LINE_WORDS[ln]}: weeks of supply against target**")
        st.plotly_chart(supply_figure(V, V0, ln, lo, hi, spans), key=f"evs_{key}_{ln}")
    st.caption(f"Weeks of {fmt_date(WEEKS[lo])} to {fmt_date(WEEKS[hi])}. Shaded: weeks an event changes numbers on this "
               "line. Left: bikes built each week (gold) against the line's capacity (black). Right: the lowest weeks "
               "of supply among the line's SKUs and stock sites against their target; below the dashed line = below "
               "target." + (f" Grey: {V0['case'].name}." if V0 is not None else ""))
