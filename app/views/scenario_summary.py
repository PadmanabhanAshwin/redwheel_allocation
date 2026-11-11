"""A scenario's summary: what it is, its rules, its results, and the plan period by period."""
import streamlit as st

from redwheel import priors, scenarios as sc
from ui import (GRANULARITY, HIGHLIGHT_BG, LINES, LINE_NAME, ORDER, SKU, SKUS_BY_LINE, fmt_date, grid_view, plan_grid,
                scenario_header, scenario_view, sku_label)

BASE = next(iter(sc.CASES))


def weeks_between(a, b):
    return round((b - a).days / 7)


def render(key: str):
    V = scenario_header(key, "Summary")
    st.markdown(V["case"].summary)
    base = scenario_view(BASE)
    card, card0 = V["card"], base["card"]
    vs = key != BASE

    # ---------------- results ----------------
    st.subheader("Results")
    moves = "move" in V["case"].decides
    c = st.columns(5 if moves else 4)
    held, cleared = card["All targets held from"], card["Open orders cleared from"]
    dw = lambda a, b: f"{weeks_between(a, b):+d} weeks vs A" if vs and weeks_between(a, b) else None
    c[0].metric("All targets held from", fmt_date(held), dw(card0["All targets held from"], held), delta_color="inverse",
                help="First week from which every SKU is at its weeks-of-supply target to the end of the horizon")
    c[1].metric("Open orders cleared from", fmt_date(cleared), dw(card0["Open orders cleared from"], cleared),
                delta_color="inverse", help="First week from which no order is waiting")
    fill = card["On-time fill rate"]
    c[2].metric("On-time fill rate", f"{fill:.1%}",
                f"{(fill - card0['On-time fill rate']) * 100:+.1f} pts vs A" if vs and abs(fill - card0['On-time fill rate']) > 5e-4
                else None,
                help="Forecast demand shipped in the week it arrives")
    c[3].metric("Bikes built", f"{card['Bikes built']:,}",
                f"{card['Bikes built'] - card0['Bikes built']:+,} vs A" if vs and card['Bikes built'] != card0['Bikes built']
                else None, delta_color="off")
    if moves:
        c[4].metric("Bikes transferred to the PDC", f"{card['Bikes transferred to the PDC']:,}",
                    help=f"About {card['Average bikes in transit']:,.0f} bikes in transit in an average week")

    # ---------------- rules ----------------
    st.subheader("Rules")
    rules = sc.rules(V["case"])
    changed = (rules["Setting"] != sc.rules(sc.CASES[BASE]).set_index("Rule").loc[rules["Rule"], "Setting"].values)
    st.dataframe(rules.style.apply(lambda col: [f"background-color: {HIGHLIGHT_BG}; font-weight: 600" if d else ""
                                                for d in changed], axis=0),
                 hide_index=True, width="stretch")
    st.caption("Planning prior: a choice Redwheel can change. Lead time: physical. The rest: the brief, the model, or a "
               "stated assumption." + (" Highlighted: changed from scenario A." if vs else ""))
    with st.expander("Planning priors table: every setting this run reads"):
        t = priors.describe(V["case"].priors)
        base_t = sc.CASES[BASE].priors
        diff = (t["value"].astype(str).values != base_t["value"].astype(str).values) if vs else [False] * len(t)
        st.dataframe(t.rename(columns={"prior": "Prior", "applies_to": "Applies to", "value": "Value",
                                       "from_date": "From", "meaning": "Meaning", "kind": "Kind"})
                     .style.apply(lambda col: [f"background-color: {HIGHLIGHT_BG}; font-weight: 600" if d else ""
                                               for d in diff], axis=0),
                     hide_index=True, width="stretch", height=(len(t) + 1) * 35 + 3)
        st.caption("The rules above are written from this table. A run checks the table against the network first and "
                   "refuses settings the network cannot carry out." + (" Highlighted: changed from scenario A." if vs
                                                                       else ""))

    # ---------------- the plan, period by period ----------------
    st.subheader("Summarized Plan")
    scopes = ["All SKUs"] + [f"line:{ln}" for ln in LINES] + ORDER
    left, right = st.columns([2, 3])
    scope = left.selectbox("Scope", scopes, key=f"scope_{key}", format_func=lambda x: x if x == "All SKUs" else (
        f"{LINE_NAME[x[5:]]} line" if x.startswith("line:") else sku_label(x)))
    gran = right.radio("Granularity", GRANULARITY, index=1, horizontal=True, key=f"gran_{key}")
    skus = list(SKU.index) if scope == "All SKUs" else (SKUS_BY_LINE[scope[5:]] if scope.startswith("line:") else [scope])
    table, flags = plan_grid(V, skus, gran)
    grid_view(table, flags)
    transit = "In transit to the PDC" in table.index
    st.caption("Demand and builds: period totals. On hand, " + ("in transit, " if transit else "") + "open orders, net "
               "inventory: at period end (net = on hand " + ("+ in transit " if transit else "") + "− open orders). "
               "% SKUs @ nominal inv.: share of SKUs at their weeks-of-supply target"
               + (" at every stock site" if V["multi"] else "") + "."
               + (" Builds count in the week the line runs; the bike reaches Reno stock after the build time."
                  if any(V["case"].build_weeks.values()) else ""))
