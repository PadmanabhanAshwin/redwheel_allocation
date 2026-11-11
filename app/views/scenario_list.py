"""Scenarios: every case, the rules it runs under, and its result."""
import pandas as pd
import streamlit as st

from redwheel import scenarios as sc
from ui import fmt_date, load_cases, right_align

st.title("Scenarios")
st.markdown("Each scenario is the same network and solver under a different set of rules.")
cases = load_cases()
cards = {k: sc.scorecard(R) for k, R in cases.items()}
chk = {k: sc.checks(R) for k, R in cases.items()}

summary = {}
for k, R in cases.items():
    c, rule = cards[k], sc.rules(R["case"]).set_index("Rule")["Setting"]
    summary[R["case"].name] = {
        "Routing rule": rule["Routing rule"], "Weeks of supply counted on": rule["Weeks of supply counted on"],
        "Build time": rule["Build time"], "Reno → PDC transfer": rule["Reno → PDC transfer"],
        "The plan decides": rule["The plan decides"],
        "Bikes built": f"{c['Bikes built']:,}",
        "All targets held from": fmt_date(c["All targets held from"]),
        "On-time fill rate": f"{c['On-time fill rate']:.1%}",
        "Checks passed": f"{int(chk[k]['pass'].sum())} of {len(chk[k])}"}
st.dataframe(pd.DataFrame(summary).rename_axis(""), width="stretch")

st.subheader("Rules and checks")
key = st.radio("Scenario", list(cases), format_func=lambda k: cases[k]["case"].name, horizontal=True)
R = cases[key]
st.markdown("**Rules**")
st.dataframe(sc.rules(R["case"]), hide_index=True, width="stretch")
st.caption("Planning prior: a choice Redwheel can change. Lead time: physical. The rest: the brief, the model, or a "
           "stated assumption.")
st.markdown("**Checks on this run**")
st.dataframe(chk[key].assign(Result=chk[key]["pass"].map({True: "pass", False: "FAIL"})).drop(columns="pass")
             .rename(columns={"check": "Check", "value": "Value"}), hide_index=True, width="stretch")
