"""Scenario: one plan in depth, always read against another scenario (by default the one it came from)."""
import plotly.graph_objects as go
import streamlit as st

from planner2 import charts
from planner2 import facts
from planner2 import state
from planner2.components import describe_changes, fdate, header, settings_view, show_changes
from redwheel import llm
from ui import (GRANULARITY, LINES, LINE_NAME, ORDER, SKU, SKUS_BY_LINE, WEEKS, grid_view, network_figure, plan_grid,
                sku_label, style)

ss = state.init()
NAMES = state.names()
SHORT = state.short_names()
if ss.get("toast"):
    st.toast(ss.pop("toast"), icon=":material/check_circle:")
keys = list(ss.cases)
if ss.current not in ss.cases:
    ss.current = state.BASE
if ss.compare_to not in ss.cases:
    ss.compare_to = state.BASE


def pick(field):
    ss[field] = ss[f"_{field}"]


def fill(widget_key, text):
    ss[widget_key] = text


# ---------------- title on the left; which scenario, compared with what, and actions on the right ----------------
key, vs = ss.current, ss.compare_to
case = ss.cases[key]
head_l, head_r = st.columns([3, 2], gap="large")
with head_r:
    p = st.columns(2)
    ss["_current"] = ss.current
    p[0].selectbox("Scenario", keys, key="_current", format_func=SHORT.get, on_change=pick, args=("current",))
    ss["_compare_to"] = ss.compare_to
    p[1].selectbox("Compare with", keys, key="_compare_to", format_func=SHORT.get, on_change=pick,
                   args=("compare_to",), help="Changes under the headline numbers, the marks on Settings and the "
                                               "extra line in the charts are against this scenario.")
    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button("What-if from this", icon=":material/tune:", key="sc_whatif",
                     help="Start a new scenario from this one's settings"):
            state.new_draft(key)
            st.switch_page("whatif.py")
        if not state.locked(key):
            if st.button("", icon=":material/edit:", key="sc_edit", help="Edit this scenario's settings"):
                state.new_draft(key, edit=True)
                st.switch_page("whatif.py")
            with st.popover("", icon=":material/delete:", help="Delete this scenario"):
                st.markdown(f"Delete **{case.name}**? Its saved settings are removed; this cannot be undone.")
                if st.button("Delete", type="primary", key="sc_delete"):
                    state.delete(key)
                    st.rerun()

slot = st.empty()                     # planning spinner: always drawn, so nothing above the tabs comes and goes
V, err = state.safe_view(key, slot)
if V is None:
    with head_l:
        header(case.name, eyebrow="This scenario can't be planned", subtitle=case.summary)
    st.error(f"{err}\n\nOpen it in What-if (Edit) to fix its settings, or delete it.", icon=":material/error:")
    st.stop()
V0 = (state.safe_view(vs, slot)[0] if vs != key else None)
with head_l:
    header(case.name, eyebrow=("Built-in scenario" if state.locked(key) else f"Your scenario · from {case.parent}")
           + (f" · compared with {vs}" if V0 is not None else " · pick a scenario to compare with"),
           subtitle=case.summary)
rl = V["rules"]
with st.container(horizontal=True):
    st.badge(f"Routing: {rl['Routing rule']}", color="gray")
    st.badge(f"Build time: {rl['Build time']}", color="gray")
    st.badge(f"Reno → PDC: {rl['Reno → PDC transfer']}", color="gray")
    st.badge(f"Plan decides: {rl['The plan decides']}", color="gray")
charts.kpis(V, V0)

tabs = st.tabs(["Summary", "Builds", "Inventory", "SKU detail", "Settings"])

# ---------------- summary ----------------
with tabs[0]:
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("#### What shapes this plan")
        st.markdown("\n".join(f"- {line}" for line in charts.reading_text(V)))
        chk = V["checks"]
        with st.expander(f"Plan checks: {int(chk['pass'].sum())} of {len(chk)} pass", expanded=not chk["pass"].all(),
                         icon=":material/check_circle:" if chk["pass"].all() else ":material/error:"):
            st.dataframe(chk.assign(Result=chk["pass"].map({True: "pass", False: "FAIL"})).drop(columns="pass")
                         .rename(columns={"check": "Check", "value": "Value"}), hide_index=True, width="stretch")
    with right, st.container(border=True):
        st.markdown("#### Ask about this plan")
        st.caption("Answers come only from this plan's computed numbers and settings"
                   + (f", and those of {vs}." if V0 is not None else "."))
        q = st.text_area("Question", key=f"q_{key}", height=90, label_visibility="collapsed",
                         placeholder="e.g. Why does MTB carbon take until September 2027 to reach target?")
        examples = ["What limits this plan?", "Which line is the bottleneck, and until when?"]
        if V0 is not None:
            examples.append(f"Why does this plan differ from {vs}?")
        with st.container(horizontal=True):
            for i, ex in enumerate(examples):
                st.button(ex, key=f"qex_{key}_{i}", width="content", on_click=fill, args=(f"q_{key}", ex))
        if st.button("Ask", icon=":material/auto_awesome:", key=f"ask_{key}", type="primary"):
            if q.strip():
                items = [(key, case, V)] + ([(vs, ss.cases[vs], V0)] if V0 is not None else [])
                try:
                    with st.spinner("Thinking …"):
                        out = llm.explain(q.strip(), facts.facts(items))
                    ss[f"ans_{key}"] = ("ok", q.strip(), out["answer"])
                except Exception as e:
                    ss[f"ans_{key}"] = ("error", q.strip(), f"The question did not go through ({type(e).__name__}: {e}).")
            else:
                ss[f"ans_{key}"] = ("error", "", "Type a question first.")
        ans = ss.get(f"ans_{key}")
        if ans:
            if ans[0] == "ok":
                st.markdown(f"<div class='rw-muted'>Q: {ans[1]}</div>", unsafe_allow_html=True)
                st.markdown(ans[2])
            else:
                st.warning(ans[2])

    st.markdown("#### Summarized plan")
    scopes = ["All SKUs"] + [f"line:{ln}" for ln in LINES] + ORDER
    c1, c2 = st.columns([2, 3])
    scope = c1.selectbox("Scope", scopes, key=f"scope_{key}", format_func=lambda x: x if x == "All SKUs" else (
        f"{LINE_NAME[x[5:]]} line" if x.startswith("line:") else sku_label(x)))
    gran = c2.radio("Granularity", GRANULARITY, index=1, horizontal=True, key=f"gran_{key}")
    skus = list(SKU.index) if scope == "All SKUs" else (SKUS_BY_LINE[scope[5:]] if scope.startswith("line:") else [scope])
    table, flags = plan_grid(V, skus, gran)
    grid_view(table, flags)
    transit = "In transit to the PDC" in table.index
    st.caption("Demand and builds: period totals. On hand, " + ("in transit, " if transit else "") + "open orders and "
               "net inventory: at period end (net = on hand " + ("+ in transit " if transit else "") + "− open "
               "orders). % SKUs @ nominal inv.: share of SKUs at their weeks-of-supply target"
               + (" at every stock site" if V["multi"] else "") + ".")

# ---------------- builds ----------------
with tabs[1]:
    st.markdown("#### The next 12 weeks")
    nb, use, full = charts.next_weeks(V)
    st.dataframe(nb, hide_index=True, width="stretch", height=(len(nb) + 1) * 35 + 3,
                 column_config={"Line": st.column_config.TextColumn(pinned=True),
                                "SKU": st.column_config.TextColumn(pinned=True)})
    st.dataframe(use.style.apply(lambda col: ["font-weight: 600" if f else "color: #6b6a66" for f in full[col.name]],
                                 axis=0), width="stretch")
    st.caption("Bikes to build each week (week commencing). Line use: bikes built / line capacity that week; bold = the "
               "line is full.")
    st.markdown("#### The whole plan, by line and month")
    charts.build_chart(V, key)
    st.markdown("#### Monthly build plan by SKU")
    mb = charts.monthly_builds(V)
    st.dataframe(mb.style.format({c: "{:,.0f}" for c in mb.columns if c not in ("Line", "SKU", "Size")}),
                 hide_index=True, width="stretch", height=(len(mb) + 1) * 35 + 3,
                 column_config={"Line": st.column_config.TextColumn(pinned=True),
                                "SKU": st.column_config.TextColumn(pinned=True)})
    st.caption("Bikes to start building each month (a week counts in the month of its Monday). The weekly plan for the "
               "whole horizon is in the download.")
    charts.build_downloads(V, key)

# ---------------- inventory ----------------
with tabs[2]:
    st.markdown("#### Weeks of supply at each quarter end")
    charts.wos_table(V)
    st.markdown("#### Share of SKUs at target over time")
    views = {state.short(key): V} | ({state.short(vs): V0} if V0 is not None else {})
    colors = dict(zip(views, ["#2a78d6", "#a3a29c"]))
    fig = go.Figure()
    for lab, Vx in views.items():
        fig.add_scatter(x=WEEKS.values, y=Vx["R"]["at_target"].mean(axis=0).values, name=lab, line_shape="hv",
                        line=dict(color=colors[lab], width=2.4 if Vx is V else 1.6))
    fig.update_yaxes(tickformat=".0%", range=[0, 1.05])
    st.plotly_chart(style(fig, 300, ytitle="SKU-site positions at target"), key=f"share_{key}")

# ---------------- one SKU ----------------
with tabs[3]:
    s = st.selectbox("SKU", ORDER, key=f"sku_{key}", format_func=sku_label)
    st.markdown("#### Stock against target, week by week")
    charts.sku_cover_chart(V, s, key)
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("#### Balance over the plan")
        charts.waterfall(V, s, key)
    with right:
        st.markdown("#### This SKU in numbers")
        st.dataframe(charts.sku_facts(V, s), hide_index=True, width="stretch")
    with st.expander("Where this SKU can go: its part of the network"):
        st.plotly_chart(network_figure(s, V["R"]["obj"], routes=case.ship_routes), key=f"net_{key}_{s}")
        st.caption("Circles: stock and orders (opening level). Squares: tasks. Faded: ship routes this scenario does "
                   "not use. +N wk: a delay.")

# ---------------- settings ----------------
with tabs[4]:
    st.markdown("#### Settings")
    settings_view(case.priors, ss.cases[vs].priors if V0 is not None else None)
    if V0 is not None:
        st.markdown(f"#### Differences from {ss.cases[vs].name}")
        show_changes(describe_changes(ss.cases[vs].priors, case.priors), empty="The same settings.")
    c = st.columns([1, 1, 3])
    if c[0].button("What-if from this", icon=":material/tune:", key="set_whatif", width="stretch"):
        state.new_draft(key)
        st.switch_page("whatif.py")
    if not state.locked(key) and c[1].button("Edit settings", icon=":material/edit:", key="set_edit", width="stretch"):
        state.new_draft(key, edit=True)
        st.switch_page("whatif.py")
