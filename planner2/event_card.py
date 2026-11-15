"""The Events card of the What-if page: the events the draft will run with, and a form to add one.

Three forms (a line down or slowed, demand up or down, a stock count correction) each build one `Change` through
`planner2.events`. The card shows the event the form describes before it is added, checks it together with the
events already in the draft (`changes.check`), and adds it to the draft only if it passes. It plans nothing."""
from __future__ import annotations

from dataclasses import replace

import streamlit as st

from planner2 import events as ev
from planner2.charts import LINE_WORDS
from planner2.components import CUSTOMERS, SITES
from redwheel import rtn
from redwheel.config import LINES
from ui import ORDER, sku_label

TYPES = ["Line down or slowed", "Demand up or down", "Stock count correction"]
LINE_LABEL = {ln: f"{LINE_WORDS[ln]} line" for ln in LINES}
SCOPE_LABEL = {"all": "All SKUs", **{ln: f"{LINE_WORDS[ln]} line (all its SKUs)" for ln in LINES},
               **{s: sku_label(s) for s in ORDER}}
CHANNEL_LABEL = {"all": "All channels", **{k: v.replace(" orders", "") for k, v in CUSTOMERS.items()}}
SITE_LABEL = dict(SITES)


def _add(d: dict, c) -> None:
    """Add an event to the draft. A blank name and description get one from the event, as a request to Claude would."""
    ss = st.session_state
    d["changes"] = tuple(d["changes"]) + (c,)
    if not d["name"]:
        d["name"] = ev.name_hint(c)
    if not d["summary"]:
        d["summary"] = ev.title(c) + "."
    d["seed"] = ss.get("wi_last", d["seed"])            # keep settings typed directly: the name boxes re-seed with them
    ss.wv += 1
    ss["ev_note"] = ""


def _remove(d: dict, i: int) -> None:
    d["changes"] = tuple(c for j, c in enumerate(d["changes"]) if j != i)


def events_card(d: dict, obj) -> None:
    A = rtn.arrivals_all(obj)
    last_plan_week, last_forecast_week = int(len(obj.weeks)), int(A.columns.max())
    first_day, last_plan_day, last_forecast_day = ev.week_start(1), ev.week_start(last_plan_week), ev.week_start(last_forecast_week)
    with st.container(border=True):
        st.markdown("**Events**")
        st.caption("Something happens to the data this scenario plans from: a line goes down, demand moves, a stock "
                   "count is off. An event changes a few numbers for this scenario only; the plan is then worked out "
                   "as for any scenario.")
        if d["changes"]:
            for i, c in enumerate(d["changes"]):
                r = st.columns([14, 1], vertical_alignment="center")
                r[0].markdown(f"{ev.subject(c)} · {ev.when(c)} · **{ev.effect(c)}**")
                r[1].button("", key=f"ev_rm_{i}", icon=":material/close:", help="Remove this event", on_click=_remove,
                            args=(d, i))
        else:
            st.caption("No events: the plan uses the data as given.")

        kind = st.selectbox("Add an event", TYPES, key="ev_type")
        info = ""
        if kind == TYPES[0]:
            cols = st.columns([2.2, 2, 1.2, 1.6])
            line = cols[0].selectbox("Line", list(LINES), index=list(LINES).index("mtb-carbon"), key="ev_line",
                                     format_func=LINE_LABEL.get)
            day = cols[1].date_input("From", value=ev.week_start(26), min_value=first_day, max_value=last_plan_day,
                                     key="ev_line_from", format="YYYY-MM-DD", help="The week containing this date is the first.")
            n = cols[2].number_input("Weeks", min_value=1, max_value=104, value=3, step=1, key="ev_line_weeks")
            pct = cols[3].number_input("Capacity left (%)", min_value=0, max_value=100, value=0, step=10,
                                       key="ev_line_pct", help="0 = the line is down; 50 = it runs at half speed.")
            c = ev.line_down(line, day, n, pct)
        elif kind == TYPES[1]:
            cols = st.columns([4.2, 1.7, 2, 1.1, 1.3])
            scope = cols[0].selectbox("SKUs", list(SCOPE_LABEL), index=list(SCOPE_LABEL).index("RW-4418"),
                                      key="ev_dem_scope", format_func=SCOPE_LABEL.get)
            chan = cols[1].selectbox("Channel", list(CHANNEL_LABEL), index=list(CHANNEL_LABEL).index("DEALERS"),
                                     key="ev_dem_chan", format_func=CHANNEL_LABEL.get)
            day = cols[2].date_input("From", value=ev.week_start(18), min_value=first_day, max_value=last_forecast_day,
                                     key="ev_dem_from", format="YYYY-MM-DD", help="The week containing this date is the first.")
            n = cols[3].number_input("Weeks", min_value=1, max_value=156, value=13, step=1, key="ev_dem_weeks")
            pct = cols[4].number_input("Change (%)", min_value=-100, max_value=500, value=30, step=5, key="ev_dem_pct",
                                       help="Orders arriving each week, up (+) or down (-). Rounded to whole bikes.")
            c = ev.demand_change(scope, None if chan == "all" else chan, pct, day, n)
            if c.to_t is not None and c.to_t > last_plan_week:
                info = f" Weeks after {ev.week_start(last_plan_week):%-d %b %Y} are forecast only: they move targets, not builds."
        else:
            cols = st.columns([3, 1.5, 1.5])
            sku = cols[0].selectbox("SKU", list(ORDER), index=list(ORDER).index("RW-9324"), key="ev_stk_sku",
                                    format_func=sku_label)
            site = cols[1].selectbox("Site", list(SITE_LABEL), key="ev_stk_site", format_func=SITE_LABEL.get)
            bikes = cols[2].number_input("Correction (bikes)", min_value=-20000, max_value=20000, value=-200, step=10,
                                         key="ev_stk_bikes", help="Negative: fewer bikes than the books say.")
            c = ev.stock_correction(sku, site, bikes)
            now = float(obj.opening[f"inventory|{sku}|{site}"])
            info = f" On the books at the snapshot: {now:,.0f} bikes; after the correction: {now + bikes:,.0f}."
        note = st.text_input("Why (optional)", key="ev_note", placeholder="e.g. planned maintenance")
        c = replace(c, reason=note.strip())

        issue = ev.problem(obj, [*d["changes"], c])
        if issue:
            st.caption(f":red[Can't add this: {issue}.]")
        else:
            st.caption(f"{ev.subject(c)} · {ev.when(c)} · {ev.effect(c)}.{info}")
        st.button("Add event", key="ev_add", icon=":material/add:", disabled=bool(issue), on_click=_add, args=(d, c))
