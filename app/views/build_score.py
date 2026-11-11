"""Page 3 — build score: weeks of supply against target, for the LP plan or the planner's rule."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui import (FQ_END, FQ_ORDER, FQ_SPAN, H, INK, LINE_NAME, ORDER, SKU, WEEKS, checks, compare, fmt_date, r,
                status_table, style)

st.title("Build Score")
METHODS = {"LP plan": "LP plan", "Planner's rule (lowest cover first)": "Lowest-cover-first rule"}
method = METHODS[st.radio("Plan", list(METHODS), horizontal=True)]
summ = compare["summary"][method]
wos, ok_all = compare["wos"][method], compare["at_target"][method]
cells = len(ORDER) * H

c = st.columns(3)
c[0].metric("SKU-weeks at target", f"{(cells - summ['SKU-weeks below target']) / cells:.0%}",
            help=f"{cells - summ['SKU-weeks below target']:,} of {cells:,}")
c[1].metric("All targets held from", fmt_date(summ["All targets held from"]))
if method == "LP plan":
    proof = checks[checks["check"].str.startswith("below target only")].iloc[0]
    c[2].metric("Shortfalls forced by capacity", f"{summ['SKU-weeks below target']} of {summ['SKU-weeks below target']}"
                if proof["pass"] else "not all", help="Below target only while the line has run full every week")
else:
    c[2].metric("SKU-weeks below target vs LP",
                f"+{summ['SKU-weeks below target'] - compare['summary'].at['SKU-weeks below target', 'LP plan']}")

# ---------------- heatmap: where and when each SKU is below or above target ----------------
st.subheader("Weeks of supply against target")
gap = (wos.loc[ORDER, 1:H] - r["target_wos"].loc[ORDER]).clip(-10, 10)
labels = [f"{s} · {LINE_NAME[SKU.at[s, 'line_id']]} {SKU.at[s, 'size']}" for s in ORDER]
fig = go.Figure(go.Heatmap(
    z=gap.values, x=WEEKS.values, y=labels, zmin=-10, zmax=10,
    colorscale=[[0, "#b4372f"], [0.5, "#ecebe7"], [1, "#2a78d6"]],
    colorbar=dict(title="weeks vs target", tickvals=[-10, -5, 0, 5, 10],
                  ticktext=["≤ −10", "−5", "at target", "+5", "≥ +10"]),
    customdata=wos.loc[ORDER, 1:H].values,
    hovertemplate="%{y}<br>%{x|%d %b %Y}: %{customdata:.1f} weeks of supply<extra></extra>"))
fig.update_yaxes(autorange="reversed")
st.plotly_chart(style(fig, 380, legend=False), key="heat")
st.caption("Red: below target. Grey: at target. Blue: above target (RW-9324 starts with 1,900 on hand).")

# ---------------- weeks of supply at each quarter end ----------------
st.subheader("Weeks of supply at each quarter end")
wq = pd.DataFrame({
    "Line · size": [f"{LINE_NAME[SKU.at[s, 'line_id']]} · {SKU.at[s, 'size']}" for s in ORDER],
    "Target (weeks)": [f"{int(r['target_wos'].at[s, 1])}" + (" → 10" if SKU.at[s, "target_group"] == "road" else "")
                       for s in ORDER],
    "Start": [r["wos"].at[s, 0] for s in ORDER],
}, index=pd.Index(ORDER, name="SKU"))
ok = {"Start": (r["wos"].loc[ORDER, 0] >= r["target_wos"].loc[ORDER, 1]).values}
for q in FQ_ORDER:
    wq[q] = [wos.at[s, FQ_END[q]] for s in ORDER]
    ok[q] = ok_all.loc[ORDER, FQ_END[q]].values
shown = wq.reset_index()
for col in ["Start"] + FQ_ORDER:
    shown[col] = [f"{v:,.1f}" + ("" if g else " ▼") for v, g in zip(shown[col], ok[col])]
status_table(shown, good=ok, right=["Start"] + FQ_ORDER)
st.caption("Last week of each fiscal quarter (FY = Sep–Aug): " + " · ".join(f"{q} {FQ_SPAN[q]}" for q in FQ_ORDER)
           + ". ▼ = below target.")
