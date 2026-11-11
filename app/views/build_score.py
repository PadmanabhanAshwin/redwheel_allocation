"""Page 3 — build score: weeks of supply against target at each quarter end, for one scenario's plan."""
import pandas as pd
import streamlit as st

from ui import (FQ_END, FQ_ORDER, FQ_SPAN, H, LINE_NAME, ORDER, SKU, compare, fmt_date, pool_label, scenario_header,
                status_table)


def render(key: str):
    V = scenario_header(key, "Build Score")
    R = V["R"]
    LP, RULE = "LP plan", "Lowest-cover-first rule"
    method = LP
    if V["case"].is_base:                    # the planner's rule was run on scenario A only
        method = {"LP plan": LP, "Planner's rule (lowest cover first)": RULE}[
            st.radio("Plan", ["LP plan", "Planner's rule (lowest cover first)"], horizontal=True)]

    if method == LP:
        wos, ok_all = R["wos"], R["at_target"]
        below, held = V["card"]["Position-weeks below target"], V["card"]["All targets held from"]
    else:                                    # scenario A: one position per SKU, both sites pooled
        pool = next(iter(V["pools"]))
        to_pos = lambda df: df.set_axis(pd.MultiIndex.from_product([df.index, [pool]], names=["item", "pool"]))
        wos, ok_all = to_pos(compare["wos"][RULE]), to_pos(compare["at_target"][RULE])
        below, held = compare["summary"].at["SKU-weeks below target", RULE], compare["summary"].at["All targets held from", RULE]
    rows = [(s, p) for s in ORDER for p in sorted(V["pools"], key=lambda p: p == "CMH")]          # Reno before PDC
    cells = len(rows) * H
    unit = "Position-weeks" if V["multi"] else "SKU-weeks"

    c = st.columns(3)
    c[0].metric(f"{unit} at target", f"{(cells - below) / cells:.0%}", help=f"{cells - below:,} of {cells:,}"
                + (". A position is one SKU at one stock site." if V["multi"] else ""))
    c[1].metric("All targets held from", fmt_date(held) if held is not None else "never")
    if method == LP:
        proof = V["checks"].iloc[-1]                          # below target only when the line ran full
        c[2].metric("Shortfalls forced by capacity", f"{below:,} of {below:,}" if proof["pass"] else "not all",
                    help="Below target only while the line has run full every week, allowing for lead time")
    else:
        c[2].metric("SKU-weeks below target vs LP", f"+{below - V['card']['Position-weeks below target']}")

    # ---------------- weeks of supply at each quarter end ----------------
    st.subheader("Weeks of supply at each quarter end")
    tw = R["target_wos"]
    wq = pd.DataFrame({
        "SKU": [s for s, _ in rows],
        "Line · size": [f"{LINE_NAME[SKU.at[s, 'line_id']]} · {SKU.at[s, 'size']}" for s, _ in rows],
        "Stock at": [pool_label(p) for _, p in rows],
        "Target (weeks)": [f"{int(tw.at[k, 1])}" + (" → 10" if SKU.at[k[0], "target_group"] == "road" else "")
                           for k in rows],
        "Start": [R["wos"].at[k, 0] for k in rows],
    })
    ok = {"Start": [bool(R["wos"].at[k, 0] >= tw.at[k, 1]) for k in rows]}
    for q in FQ_ORDER:
        wq[q] = [wos.at[k, FQ_END[q]] for k in rows]
        ok[q] = [bool(ok_all.at[k, FQ_END[q]]) for k in rows]
    for col in ["Start"] + FQ_ORDER:
        wq[col] = [f"{v:,.1f}" + ("" if g else " ▼") for v, g in zip(wq[col], ok[col])]
    status_table(wq, good=ok, right=["Start"] + FQ_ORDER, height=(len(wq) + 1) * 35 + 3)
    st.caption("Weeks of supply: how many weeks of the coming forecast the net inventory covers"
               + (" (each site's stock against the demand routed to it)" if V["multi"] else "") + ". Last week of each fiscal quarter (FY = Sep–Aug): "
               + " · ".join(f"{q} {FQ_SPAN[q]}" for q in FQ_ORDER) + ". ▼ = below target.")
