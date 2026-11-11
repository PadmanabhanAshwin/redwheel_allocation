"""Scenarios: every case, the rules it runs under, and its result."""
import pandas as pd
import streamlit as st

from redwheel import scenarios as sc
from ui import fmt_date, load_cases

st.title("Scenarios")
st.markdown("Each scenario is the same network and solver under a different set of rules. Scenario A is the base "
            "case; each later scenario changes some of its rules.")
cases = load_cases()
base = sc.rules(next(iter(cases.values()))["case"]).set_index("Rule")["Setting"]
cards = {k: sc.scorecard(R) for k, R in cases.items()}
chk = {k: sc.checks(R) for k, R in cases.items()}

summary = {}
for k, R in cases.items():
    c, rule = cards[k], sc.rules(R["case"]).set_index("Rule")["Setting"]
    changed = [n for n in base.index if rule[n] != base[n]]
    summary[R["case"].name] = {
        "Changes from scenario A": "; ".join(changed) if changed else "—",
        "Routing rule": rule["Routing rule"], "Weeks of supply counted on": rule["Weeks of supply counted on"],
        "Build time": rule["Build time"], "Reno → PDC transfer": rule["Reno → PDC transfer"],
        "The plan decides": rule["The plan decides"],
        "Bikes built": f"{c['Bikes built']:,}",
        "All targets held from": fmt_date(c["All targets held from"]),
        "On-time fill rate": f"{c['On-time fill rate']:.1%}",
        "Checks passed": f"{int(chk[k]['pass'].sum())} of {len(chk[k])}"}
st.dataframe(pd.DataFrame(summary).rename_axis(""), width="stretch")

st.caption("Each scenario's own section has its summary and plan pages. Checks: computed on each run; the detail is on the Model Validation page.")
