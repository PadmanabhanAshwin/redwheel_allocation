"""Page 6 — model validation: checks on this run, and the LP against a planner's rule."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui import FORECAST, H, HISTORY, LINES, LINE_NAME, WEEKS, checks, compare, fmt_date, right_align, style

st.title("Model Validation")

# ---------------- checks ----------------
st.subheader("Checks on this run")
st.dataframe(checks.assign(Result=checks["pass"].map({True: "pass", False: "FAIL"})).drop(columns="pass")
             .rename(columns={"area": "Area", "check": "Check", "value": "Value"}),
             hide_index=True, width="stretch")

# ---------------- LP vs the planner's rule ----------------
st.subheader("Does the optimisation earn its place?")
s = compare["summary"]
lp, rule = "LP plan", "Lowest-cover-first rule"
bl = compare["by_line"]
st.markdown("Compared with a common planner's rule, **lowest cover first**: each week, each line builds for the SKU "
            "furthest below target first, one week at a time, no look-ahead. Same network, inputs and scoring.")
st.markdown(
    f"**Result.** The LP holds every target from **{fmt_date(s.at['All targets held from', lp])}**; the rule from "
    f"**{fmt_date(s.at['All targets held from', rule])}**. The gain is foresight on road: the LP builds ahead of the "
    "January 2028 target step and recovers faster after the July 2027 peak. On MTB, capacity is the limit and both "
    "plans are identical in timing.")

fmt = {"Bikes built": "{:,.0f}", "SKU-weeks below target": "{:,.0f}",
       "Shortfall (weeks of demand, summed)": "{:,.0f}", "On-time fill rate": "{:.1%}",
       "LP objective (lower is better)": "{:,.1f}"}
tbl = pd.DataFrame({c: [fmt[k].format(s.at[k, c]) if k in fmt else
                        ("yes" if s.at[k, c] is True else fmt_date(s.at[k, c]) if s.at[k, c] is not None else "never")
                        if k != "Capacity respected" else ("yes" if s.at[k, c] else "NO")
                        for k in s.index] for c in s.columns}, index=s.index).rename_axis("Measure")
tbl = tbl.loc[["SKU-weeks below target", "Shortfall (weeks of demand, summed)", "All targets held from",
               "On-time fill rate", "Bikes built", "Capacity respected", "LP objective (lower is better)"]]
st.dataframe(right_align(tbl), width="stretch")
st.caption(f"SKU-weeks below target: of {10 * H:,}. Shortfall: weeks of average demand short, summed over SKU-weeks. "
           "LP objective: what the LP minimises (worst shortfall per line-week, then total shortfall, then excess).")

st.markdown("**By line**")
lt = pd.DataFrame({
    "Line": [LINE_NAME[ln] for ln in LINES],
    "Target held from · LP": [fmt_date(WEEKS[int(bl[lp].at[ln, "held"])]) for ln in LINES],
    "Target held from · rule": [fmt_date(WEEKS[int(bl[rule].at[ln, "held"])]) for ln in LINES],
    "SKU-weeks below · LP": [int(bl[lp].at[ln, "below"]) for ln in LINES],
    "SKU-weeks below · rule": [int(bl[rule].at[ln, "below"]) for ln in LINES],
})
st.dataframe(lt, hide_index=True, width="stretch")

st.markdown("**SKUs below target, week by week**")
fig = go.Figure()
fig.add_scatter(x=WEEKS.values, y=compare["below_by_week"][rule].values, name="rule", line_shape="hv",
                line=dict(color=HISTORY, width=2))
fig.add_scatter(x=WEEKS.values, y=compare["below_by_week"][lp].values, name="LP", line_shape="hv",
                line=dict(color=FORECAST, width=2.5))
fig.update_yaxes(range=[0, 10.5], dtick=2)
st.plotly_chart(style(fig, 300, ytitle="SKUs below target (of 10)"), key="cmp")
st.caption("Rule worse in 19 weeks (early Aug 2027, Jan–Apr 2028); LP worse by one SKU in 7 weeks.")

st.markdown("**Checks on this comparison**")
opt_ok = compare["lp_unrounded_objective"] <= s.at["LP objective (lower is better)", rule] + 1e-6
score_ok = abs(compare["lp_unrounded_objective"] - compare["lp_solver_objective"]) < 1e-6
st.dataframe(pd.DataFrame([
    ("Scoring the LP's own plan reproduces the solver's objective", f"{compare['lp_unrounded_objective']:,.4f} vs "
     f"{compare['lp_solver_objective']:,.4f}", score_ok),
    ("No feasible plan beats the LP on its own objective (the rule is a feasible plan)",
     f"LP {compare['lp_unrounded_objective']:,.1f} ≤ rule {s.at['LP objective (lower is better)', rule]:,.1f}", opt_ok),
    ("The rule's plan is feasible: whole bikes, capacity respected", "", bool(s.at["Capacity respected", rule])),
], columns=["Check", "Value", "pass"]).assign(Result=lambda d: d["pass"].map({True: "pass", False: "FAIL"}))
             .drop(columns="pass"), hide_index=True, width="stretch")
st.caption("The rule matches the LP on on-time fill rate and has two fewer SKU-weeks below target on MTB carbon "
           "(it finishes one SKU first; the LP keeps all three level).")
