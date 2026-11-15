"""Plan: what do we build, and does it hit target?

One scenario's plan, read top to bottom: the answer in a sentence (when every target is held, and what sets that
date); four headline numbers; the planning grid (each line's capacity used, month by month, with its SKUs' weeks of
supply under it); then the tables: Build Plans (what to start building, by week or month), Summarized Plan (the
balance, period by period) and Plan by SKU (start, plan, end, target)."""
import pandas as pd
import streamlit as st

from planner2 import events as ev
from planner2 import state
from planner2.charts import LINE_WORDS
from planner3 import charts, reading as rd, theme as T
from ui import GRANULARITY, LINES, ORDER, SKU, SKUS_BY_LINE, sku_label

ss = state.init()
SHORT = state.short_names()
keys = list(ss.cases)
if "p3_linked" not in ss:                  # a link like ?scenario=E1 opens that scenario, once per session
    ss.p3_linked = True
    if st.query_params.get("scenario") in ss.cases:
        ss.current = st.query_params["scenario"]
if ss.current not in ss.cases:
    ss.current = state.BASE
key = ss.current
case = ss.cases[key]
st.query_params["scenario"] = key           # the address bar always names the scenario on screen


def pick():
    ss.current = ss["p3_plan_key"]


# ---------------- header: the question, the scenario and its rules; the scenario picker on the right ----------------
head, side = st.columns([3, 1], gap="large", vertical_alignment="bottom")
with side:
    ss["p3_plan_key"] = key
    st.selectbox("Scenario", keys, key="p3_plan_key", format_func=SHORT.get, on_change=pick)
    checks_slot = st.container()          # the plan checks, filled once the plan is computed
slot = st.empty()                       # planning spinner; always drawn so nothing above the tabs comes and goes
V, err = state.safe_view(key, slot)
with head:
    rules = ""
    if V is not None:
        rl = V["rules"]
        rules = (f"Routing: {rl['Routing rule']} · Build time: {rl['Build time']} · Reno → PDC: "
                 f"{rl['Reno → PDC transfer']} · The plan decides: {rl['The plan decides']}")
    T.header(case.name, "What do we build, and does it hit target?", case.summary, rules)
if V is None:
    st.error(f"This scenario can't be planned: {err}", icon=":material/error:")
    st.stop()

# ---------------- the answer, and the numbers that confirm it ----------------
st.markdown(f"<div class='p3-verdict'>{rd.verdict(V)}</div>", unsafe_allow_html=True)
st.markdown("".join(f"<span class='p3-chip'>Event · {T.esc(ev.title(c))}</span>" for c in case.changes)
            or "<span></span>", unsafe_allow_html=True)      # always drawn: keeps the tabs below in place
T.kpis(rd.kpi_cards(V))
chk = V["checks"]
with checks_slot, st.popover(f"The {len(chk)} plan checks", icon=":material/fact_check:", width="stretch"):
    ct = pd.DataFrame({"": chk["pass"].map({True: "✓", False: "✗ FAIL"}), "Check": chk["check"], "Value": chk["value"]})
    T.table(ct, left=3, key="p3-checks",
            cells=pd.DataFrame({"": chk["pass"].map({True: "", False: "bad"}), "Check": "wrap", "Value": "wraps"}))
    st.caption("Computed on every plan, every time it is run.")

# ---------------- the planning grid ----------------
st.subheader("Capacity and stock, month by month")
g = rd.grid(V)
T.key([(T.INK, "line full"), ("#D5DAE0", "line with spare capacity: % of it used"),
       ("#F4A47E", "SKU below target: weeks of supply (darker = further below)"), ("#F3F4F6", "SKU at target"),
       ("#C9D4E0", "SKU above target"), *([("white", "event months", T.ACCENT)] if case.changes else [])])
st.plotly_chart(charts.grid_figure(g), key=f"p3_grid_{key}", config={"displayModeBar": False})
below_ok = bool(chk[chk["check"].str.startswith(rd.BELOW_CHECK)]["pass"].all())
T.note(f"Targets: {rd.targets_text(V)}. Weeks of supply: how many weeks of the coming forecast a SKU's stock, less "
       "its open orders, covers at the month's end. " +
       (("Every week a SKU is below target its line is full" + (" or the SKU at its run limit" if rd.has_run_limits(V)
                                                                 else "")
         + (", allowing for build and transfer time" if rd.lead_weeks(V) else "") + ": the shortfall is capacity, "
         "not the plan.") if below_ok else "<b>A SKU is below target in a week its line had spare capacity:</b> see "
                                           "the plan checks.")
       + (" In this scenario each SKU has a row per stock site." if V["multi"] else "") + " Hover for the numbers.")

# ---------------- the tables ----------------
tabs = st.tabs(["Build Plans", "Summarized Plan", "Plan by SKU"])

with tabs[0]:
    kinds = {"weeks": "Next 12 weeks", "months": "Every month to Dec 2028"}
    kind = st.radio("Show", list(kinds), horizontal=True, key=f"p3_bk_{key}", format_func=kinds.get,
                    label_visibility="collapsed")
    bt, cells, rows = rd.build_table(V, kind)
    T.table(bt, left=2, rows=rows, cells=cells, key="p3-builds")
    T.note("Bikes to start building, per SKU, in each " + ("week (week commencing)" if kind == "weeks" else
           "month (a week counts in the month of its Monday)") + ". Each line's first row is its capacity; its "
           "total is shaded where it uses all of it. – = none.")
    with st.container(horizontal=True):
        st.download_button("Weekly build plan (CSV)", rd.build_csv(V), file_name=f"build_plan_{key}.csv",
                           mime="text/csv", key=f"p3_dl_{key}", icon=":material/download:")
        tc = rd.transfer_csv(V)
        if tc is not None:
            st.download_button("Weekly transfers to the PDC (CSV)", tc, file_name=f"transfers_{key}.csv",
                               mime="text/csv", key=f"p3_dlm_{key}", icon=":material/download:")

with tabs[1]:
    scopes = {"All SKUs": "All SKUs", **{f"line:{ln}": f"{LINE_WORDS[ln]} line" for ln in LINES},
              **{s: sku_label(s) for s in ORDER}}
    c1, c2 = st.columns([2, 3], vertical_alignment="bottom")
    scope = c1.selectbox("Scope", list(scopes), key=f"p3_scope_{key}", format_func=scopes.get)
    gran = c2.radio("Period", GRANULARITY, index=1, horizontal=True, key=f"p3_gran_{key}")
    skus = (list(SKU.index) if scope == "All SKUs" else SKUS_BY_LINE[scope[5:]] if scope.startswith("line:")
            else [scope])
    table, cells, rows = rd.summarized_plan(V, skus, gran)
    T.table(table, rows=rows, cells=cells, key="p3-summary")
    T.note("Demand and supply: totals in the period. Stock: at the period's end; net inventory = on hand"
           + (" + in transit" if "In transit to the PDC" in set(table["Measure"]) else "") + " − open orders. "
           "Each period, net inventory" + (" + work in progress" if rd.WIP in set(table["Measure"]) else "")
           + " at its start + builds − forecast demand = the same at its end. Quarters and years are fiscal "
           "(September to August). Shaded: below target, or more on open orders than in stock.")

with tabs[2]:
    st_, cells, rows = rd.sku_table(V)
    T.table(st_, left=2, rows=rows, cells=cells, key="p3-skus", groups=rd.SKU_GROUPS)
    T.note("Bikes. Net inventory = stock − open orders; at the end it is the start + built − forecast"
           + (" − bikes still in build" if any(V["case"].build_weeks.values()) else "") + ". Weeks of supply at "
           "the start" + (" (lowest stock site)" if V["multi"] else "") + "; shaded when below target. Weeks below: "
           + ("SKU-site" if V["multi"] else "SKU") + " weeks below target over the plan.")
