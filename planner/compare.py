"""Compare scenarios: headline results, the settings that differ, and the plans side by side over time."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import state
from redwheel import priors
from ui import HIGHLIGHT_BG, LINES, WEEKS, cell, fmt_date, line_grid, right_align, style

PALETTE = ["#262420", "#b8860b", "#2a78d6", "#8f6b16", "#7a7873", "#5b8fd6", "#d9b44a"]   # fixed order, never cycled

ss = state.init()
cases = ss.cases
color = {k: PALETTE[i % len(PALETTE)] for i, k in enumerate(cases)}

st.title("Compare Scenarios")
default = list(dict.fromkeys(["A", "B", ss.active]))
keys = st.multiselect("Scenarios", list(cases), default=[k for k in default if k in cases],
                      format_func=lambda k: cases[k].name, max_selections=len(PALETTE))
if len(keys) < 2:
    st.info("Pick at least two scenarios.")
    st.stop()
views = {k: state.view(k) for k in keys}
base = keys[0]
st.caption(f"Differences are against the first scenario picked: {cases[base].name}.")

# ---------------- headline results ----------------
st.subheader("Results")
M = ["All targets held from", "Open orders cleared from", "On-time fill rate", "Position-weeks below target",
     "Bikes built", "Bikes transferred to the PDC", "Average bikes in transit"]


def show(k, v):
    if v is None:
        return "never"
    if isinstance(v, pd.Timestamp):
        return fmt_date(v)
    return f"{v:.1%}" if "rate" in k else f"{v:,.0f}"


def delta(k, a, b):
    if a is None or b is None or a == b:
        return ""
    if isinstance(a, pd.Timestamp):
        return f" ({round((b - a).days / 7):+d} wk)"
    return f" ({(b - a) * 100:+.1f} pts)" if "rate" in k else f" ({b - a:+,.0f})"


card0 = views[base]["card"]
res = pd.DataFrame({cases[k].name: [show(m, views[k]["card"][m]) + ("" if k == base else
                                                                    delta(m, card0[m], views[k]["card"][m]))
                                    for m in M] for k in keys}, index=pd.Index(M, name="Measure"))
st.dataframe(right_align(res), width="stretch")
st.caption("A position is one SKU at one stock site: weeks below target are summed over positions, so a scenario "
           "that splits stock across two sites has twice as many positions.")

# ---------------- settings ----------------
st.subheader("Settings that differ")
side = pd.concat({cases[k].name: priors.normalise(cases[k].priors).set_index(priors.KEY)["value"] for k in keys},
                 axis=1).fillna("—")
side = side[side.nunique(axis=1) > 1]
if len(side):
    st.dataframe(side.reset_index().rename(columns={"prior": "Prior", "applies_to": "Applies to",
                                                    "from_date": "From"}), hide_index=True, width="stretch")
else:
    st.caption("All picked scenarios have the same settings.")

# ---------------- over time ----------------
H = len(WEEKS)
st.subheader("Share of positions at target, week by week")
fig = go.Figure()
for k in keys:
    fig.add_scatter(x=WEEKS.values, y=views[k]["R"]["at_target"].mean(axis=0).values, name=cases[k].name,
                    line_shape="hv", line=dict(color=color[k], width=2.2))
fig.update_yaxes(tickformat=".0%", range=[0, 1.05])
st.plotly_chart(style(fig, 300, ytitle="positions at target"), key="cmp_at")

st.subheader("Open orders, first 40 weeks")
fig = go.Figure()
for k in keys:
    fig.add_scatter(x=WEEKS.values[:40], y=views[k]["open_orders"].loc[:, 1:40].sum().values, name=cases[k].name,
                    line=dict(color=color[k], width=2.2))
st.plotly_chart(style(fig, 300, ytitle="bicycles on open orders"), key="cmp_open")

st.subheader("Builds per month by line")
month = pd.Series(WEEKS.dt.to_period("M").values, index=WEEKS.index)
months = month.unique()
x = [p.to_timestamp() for p in months]
fig = line_grid()
for i, ln in enumerate(LINES):
    for k in keys:
        b = views[k]["R"]["builds"]
        y = b[b.index.str.endswith(f"RENO/{ln}")].sum().groupby(month.values).sum().reindex(months).values
        fig.add_scatter(x=x, y=y, name=cases[k].name, legendgroup=k, showlegend=i == 0, line_shape="hvh",
                        line=dict(color=color[k], width=2), **cell(i))
fig.update_yaxes(rangemode="tozero")
st.plotly_chart(style(fig, 520), key="cmp_builds")
st.caption("Bicycles built per month (a week counts in the month of its Monday).")
