"""A scenario's network: the shared network with this scenario's delays and the routes its routing rule allows."""
import pandas as pd
import streamlit as st

from redwheel import scenarios as sc
from ui import HIGHLIGHT_BG, ORDER, load_cases, network_figure, scenario_header, sku_label

BASE = next(iter(sc.CASES))
KIND_NAME = {"make": "Build: line capacity → Reno stock", "move": "Transfer: Reno → PDC (via in transit)"}


def wk(n):
    return "same week" if n == 0 else f"{n} week" + ("s" if n > 1 else "")


def settings(R) -> pd.Series:
    """Read from the scenario's network and routing rule: each task kind's delay, and each route used or not."""
    a = R["obj"].arrows
    kind = a["task_id"].str.split("|").str[0]
    out = {KIND_NAME[k]: wk(int(a.loc[(kind == k) & (a["amount"] > 0), "delay"].max())) for k in KIND_NAME}
    allowed = set(R["case"].ship_routes)
    for site in sc.SITES:
        for cust in sc.CUSTOMERS:
            out[f"Ship: {sc.SHORT[site]} → {sc.CUSTOMER_NAME[cust]} orders"] = \
                "used" if (site, cust) in allowed else "not used"
    return pd.Series(out)


def render(key: str):
    V = scenario_header(key, "Network")
    R = V["R"]
    cases = load_cases()
    vs = key != BASE
    st.markdown("Every scenario runs on the same network (resources, tasks, edges). A scenario sets the delays on its "
                "edges and, through its routing rule, which ship routes may be used.")

    st.subheader("How this scenario sets the network")
    mine, base = settings(R), settings(cases[BASE])
    t = pd.DataFrame({"Setting": mine.index, "This scenario": mine.values})
    if vs:
        t["Scenario A"] = base.values
    changed = (mine != base).values
    st.dataframe(t.style.apply(lambda col: [f"background-color: {HIGHLIGHT_BG}; font-weight: 600" if c else ""
                                            for c in changed], axis=0),
                 hide_index=True, width="stretch")
    if vs:
        k = ["task_id", "resource_id", "amount"]
        a, b = cases[BASE]["obj"].arrows, R["obj"].arrows
        same = set(map(tuple, a[k].values)) == set(map(tuple, b[k].values))
        d = a.merge(b, on=k, suffixes=("_a", "_b"))
        kinds = d.loc[d["delay_a"] != d["delay_b"], "task_id"].str.split("|").str[0].value_counts()
        note = "Highlighted: changed from scenario A."
        if same:
            note += (f" Same {len(R['obj'].resources)} resources, {len(R['obj'].tasks)} tasks and {len(b)} edges as "
                     "scenario A" + "".join(f"; {n} {kind} edges have a different delay" for kind, n in kinds.items())
                     + ". Routes not used stay in the network; the routing rule leaves them out of the plan.")
        st.caption(note)

    st.subheader("Network for one SKU")
    s = st.selectbox("SKU", ORDER, key=f"net_sku_{key}", format_func=sku_label)
    st.plotly_chart(network_figure(s, R["obj"], routes=R["case"].ship_routes), key=f"net_{key}")
    st.caption("Circles: resources (opening level). Squares: tasks. Black edge adds, grey edge takes; +N wk = delay. "
               "Faded: ship routes this scenario's routing rule does not use. Dealer stock is not Redwheel's, so it has "
               "no edges.")
