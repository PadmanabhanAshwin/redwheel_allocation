"""Scenario comparison: rules, scorecard and plans of two scenarios side by side."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from redwheel import scenarios as sc
from ui import CASE_COLOR, LINES, LINE_NAME, WEEKS, cell, fmt_date, line_grid, load_cases, right_align, style

st.title("Scenario Comparison")
cases = load_cases()
keys = list(cases)
A, B = cases[keys[0]], cases[keys[1]]
na, nb = A["case"].name, B["case"].name
H = len(WEEKS)

# ---------------- rules ----------------
st.subheader("Rules")
ra, rb = sc.rules(A["case"]).set_index("Rule"), sc.rules(B["case"]).set_index("Rule")
rules = pd.DataFrame({na: ra["Setting"], nb: rb["Setting"], "Kind": ra["Kind"]}).rename_axis("Rule").reset_index()
differs = (ra["Setting"] != rb["Setting"]).values
st.dataframe(rules.style.apply(lambda col: ["font-weight: 600; background-color: #f6edd4" if d and col.name != "Rule"
                                            and col.name != "Kind" else "" for d in differs], axis=0),
             hide_index=True, width="stretch")
st.caption("Highlighted: rules that differ.")

# ---------------- scorecard ----------------
st.subheader("Scorecard")
ca, cb = sc.scorecard(A), sc.scorecard(B)


def show(k, v):
    if v is None:
        return "never"
    if isinstance(v, pd.Timestamp):
        return fmt_date(v)
    if "rate" in k or "share" in k:
        return f"{v:.1%}"
    return f"{v:,.0f}"


def diff(k):
    a, b = ca[k], cb[k]
    if isinstance(a, pd.Timestamp) and isinstance(b, pd.Timestamp):
        w = round((b - a).days / 7)
        return "same week" if w == 0 else f"{abs(w)} weeks {'later' if w > 0 else 'earlier'}"
    if a is None or b is None:
        return ""
    if "rate" in k or "share" in k:
        return f"{(b - a) * 100:+.1f} pts"
    return f"{b - a:+,.0f}"


score = pd.DataFrame({"Measure": list(ca), na: [show(k, ca[k]) for k in ca], nb: [show(k, cb[k]) for k in cb],
                      "B against A": [diff(k) for k in ca]})
st.dataframe(right_align(score.set_index("Measure")), width="stretch")
st.caption("A position is one SKU in one stock pool: 10 in scenario A (stock pooled), 20 in scenario B (Reno and PDC). "
           "Scenario B's last two weeks are understated: a bike built in the final week lands after the horizon, "
           "so it is not planned.")

# ---------------- targets by line ----------------
st.subheader("Week each line holds its targets from")
ha, hb = sc.held_by_line(A), sc.held_by_line(B)
tl = pd.DataFrame({"Line": [LINE_NAME[ln] for ln in LINES],
                   f"A · pooled": [fmt_date(ha.loc[ln].max()) for ln in LINES],
                   "B · Reno (dealer, commercial)": [fmt_date(hb.at[ln, "RENO"]) for ln in LINES],
                   "B · PDC (web)": [fmt_date(hb.at[ln, "CMH"]) for ln in LINES],
                   "B later by": [f"{round((hb.loc[ln].max() - ha.loc[ln].max()).days / 7)} weeks" for ln in LINES]})
st.dataframe(tl, hide_index=True, width="stretch")

# ---------------- over time ----------------
st.subheader("Positions at target, week by week")
fig = go.Figure()
for R, k in ((A, keys[0]), (B, keys[1])):
    fig.add_scatter(x=WEEKS.values, y=R["at_target"].mean(axis=0).values, name=R["case"].name, line_shape="hv",
                    line=dict(color=CASE_COLOR[k], width=2.5))
fig.update_yaxes(tickformat=".0%", range=[0, 1.05])
st.plotly_chart(style(fig, 300, ytitle="share of positions at target"), key="cmp_target")

st.subheader("Open orders, week by week")
fig = go.Figure()
for R, k in ((A, keys[0]), (B, keys[1])):
    fig.add_scatter(x=WEEKS.values[:40], y=R["flows"]["open_orders"].sum()[list(range(1, 41))].values,
                    name=R["case"].name, line=dict(color=CASE_COLOR[k], width=2.5))
st.plotly_chart(style(fig, 300, ytitle="bicycles on open orders"), key="cmp_open")
st.caption("First 40 weeks; both scenarios carry no open orders after that.")

st.subheader("Builds per month by line")
month = pd.Series(WEEKS.dt.to_period("M").values, index=WEEKS.index)
months = month.unique()
x = [p.to_timestamp() for p in months]
fig = line_grid()
for i, ln in enumerate(LINES):
    for R, k in ((A, keys[0]), (B, keys[1])):
        b = R["builds"][R["builds"].index.str.endswith(f"RENO/{ln}")].sum()
        y = b.groupby(month.values).sum().reindex(months).values
        fig.add_scatter(x=x, y=y, name=R["case"].name, legendgroup=k, showlegend=i == 0, line_shape="hvh",
                        line=dict(color=CASE_COLOR[k], width=2.2 if k == keys[1] else 1.8), **cell(i))
fig.update_yaxes(rangemode="tozero")
st.plotly_chart(style(fig, 520, ytitle=None), key="cmp_builds")
st.caption("Bicycles built per month. Scenario B builds earlier to fill the pipeline, and stops short in the final "
           "month (end of horizon).")
