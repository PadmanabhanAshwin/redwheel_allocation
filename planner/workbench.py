"""Scenario workbench: pick a scenario, see its plan, change its priors, re-plan."""
import pandas as pd
import streamlit as st

import charts
import state
from priors_editor import editor
from redwheel import llm, priors, scenarios as sc
from ui import GRANULARITY, LINES, LINE_NAME, ORDER, SKU, SKUS_BY_LINE, grid_view, network_figure, obj, plan_grid, \
    sku_label


def label(cases, k):
    return cases[k].name


# ---------------- sidebar: the scenarios ----------------

def sidebar(ss):
    cases = ss.cases
    with st.sidebar:
        st.markdown("### Scenarios")
        ss["_active"] = ss.active
        st.radio("Scenario", list(cases), key="_active", format_func=lambda k: label(cases, k),
                 label_visibility="collapsed", on_change=lambda: ss.update(active=ss["_active"]))
        st.caption("A and B are built in and locked; copy one to change it.")
        if st.button("Copy this scenario", icon=":material/content_copy:", width="stretch",
                     help="Make an editable copy of the selected scenario"):
            state.duplicate(ss.active)
            st.rerun()
        if not state.locked(ss.active) and st.button("Delete this scenario", icon=":material/delete:",
                                                     width="stretch"):
            state.delete(ss.active)
            st.rerun()
        st.divider()
        ss["_compare_to"] = ss.compare_to
        st.selectbox("Compare against", list(cases), key="_compare_to", format_func=lambda k: cases[k].name,
                     on_change=lambda: ss.update(compare_to=ss["_compare_to"]))
        st.caption("Changes against this scenario show under each headline number, and on the Priors tab.")


# ---------------- tabs ----------------

def plan_tab(V, key):
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
               + (" at every stock site" if V["multi"] else "") + ".")
    st.subheader("Builds against capacity and forecast, and the open orders left")
    charts.build_chart(V, key)
    charts.build_downloads(V, key)


def ask_panel(ss, key, case):
    """Ask for a change in words. The LLM's proposal is checked against the network, then loaded into the editors
    below as unapplied changes; nothing is applied from here."""
    with st.container(border=True):
        st.markdown("**Ask for a change** · describe it in words. Claude proposes table changes, checked against the "
                    "network, and loads them below for you to review and apply.")
        req = st.text_area("Request", key=f"ask_{key}", height=80, label_visibility="collapsed",
                           placeholder="e.g. MTB carbon now takes two weeks to build.")
        if st.button("Propose changes", icon=":material/auto_awesome:", key=f"ask_btn_{key}"):
            if not req.strip():
                ss.ask_note[key] = ("info", "Type a request first.")
            else:
                state.clear_proposal(key)
                try:
                    with st.spinner("Asking Claude …"):
                        p = llm.propose(req.strip(), case.priors, obj)
                except Exception as e:                        # no login, no network, a refusal: say so, keep the page
                    ss.ask_note[key] = ("error", f"The request did not go through ({type(e).__name__}: {e}).")
                else:
                    if p.ok:
                        ss.loaded[key] = {"table": p.table, "reasons": {
                            (c["prior"], c["applies_to"], c["from_date"], c["new"]): c["reason"] for c in p.changes}}
                        ss.version += 1                       # re-seed the editors from the proposal
                        msg = f"Proposed {len(p.changes)} change{'s' if len(p.changes) != 1 else ''}, loaded below " \
                              "as unapplied changes. Review, then apply or discard."
                        if p.unsupported:
                            msg += "\n\nNot covered by these settings:\n" + "\n".join(f"- {u}" for u in p.unsupported)
                        ss.ask_note[key] = ("success", msg)
                    elif p.changes:                           # changes that still fail the checks after one retry
                        ss.ask_note[key] = ("warning", "The proposal failed the checks and was not loaded:\n"
                                            + "\n".join(f"- {e}" for e in p.errors))
                    elif p.question:
                        ss.ask_note[key] = ("info", f"**Question:** {p.question}")
                    else:
                        ss.ask_note[key] = ("info", "No changes proposed. Not covered by these settings:\n"
                                            + "\n".join(f"- {u}" for u in p.unsupported))
            st.rerun()
        note = ss.ask_note.get(key)
        if note:
            getattr(st, note[0])(note[1])


def discard(key):
    """Runs before the page is drawn, so the page shows the cleared state directly."""
    state.clear_proposal(key)
    st.session_state.version += 1


def priors_tab(ss, key, V0):
    case = ss.cases[key]
    locked = state.locked(key)
    if locked:
        st.info(f"{case.name} is built in and cannot be changed. **Copy this scenario** (sidebar) to make a "
                "version you can edit.", icon=":material/lock:")
    else:
        c1, c2 = st.columns([1, 2])
        name = c1.text_input("Name", case.name, key=f"name_{key}_{ss.version}")
        summary = c2.text_input("Description", case.summary, key=f"summ_{key}_{ss.version}")
        if (name, summary) != (case.name, case.summary):
            state.rename(key, name, summary)
        ask_panel(ss, key, case)

    loaded = ss.loaded.get(key)
    draft = editor(loaded["table"] if loaded else case.priors, locked, f"{key}_{ss.version}")
    errs = priors.validate(draft, obj)
    pending = priors.diff(case.priors, draft)

    st.markdown("**Changes**")
    if not pending:
        st.caption("No unapplied changes." if not locked else "Locked.")
    else:
        why = loaded["reasons"] if loaded else {}
        st.markdown("\n".join(f"- {priors.describe_change(c)}" + (
            f" · *{why[(c['prior'], c['applies_to'], c['from_date'], c['new'])]}*"
            if (c["prior"], c["applies_to"], c["from_date"], c["new"]) in why else "") for c in pending))
        if errs:
            st.error("This table cannot run:\n\n" + "\n".join(f"- {e}" for e in errs), icon=":material/block:")
        b1, b2, _ = st.columns([1, 1, 3])
        if b1.button("Apply and re-plan", type="primary", disabled=bool(errs), icon=":material/play_arrow:",
                     width="stretch"):
            before = state.view(key)["card"]["All targets held from"]
            state.apply(key, draft)
            after = state.view(key)["card"]["All targets held from"]
            w = charts.weeks_between(before, after) if before is not None and after is not None else None
            ss.toast = f"Re-planned with {len(pending)} change{'s' if len(pending) != 1 else ''}. All targets held " \
                       f"from {charts.fmt_date(after) if after is not None else 'never'}" + \
                       (f" ({w:+d} wk)." if w else ".")
            st.rerun()
        b2.button("Discard changes", width="stretch", on_click=discard, args=(key,))

    vs = ss.compare_to
    if vs != key:
        since = priors.diff(ss.cases[vs].priors, case.priors)
        with st.expander(f"How this scenario differs from {ss.cases[vs].name} ({len(since)} settings)",
                         expanded=False):
            st.markdown("\n".join(f"- {priors.describe_change(c)}" for c in since) or "The same settings.")
    with st.expander("The priors table this run reads"):
        st.dataframe(priors.describe(case.priors), hide_index=True, width="stretch",
                     height=(len(case.priors) + 1) * 35 + 3)
        st.caption("Every setting the plan uses. A run checks it against the network first and refuses settings the "
                   "network cannot carry out.")


def targets_tab(V, key):
    st.subheader("Weeks of supply at each quarter end")
    charts.wos_table(V)
    st.subheader("One SKU, week by week")
    s = st.selectbox("SKU", ORDER, key=f"cover_sku_{key}", format_func=sku_label)
    charts.sku_cover_chart(V, s, key)


def balance_tab(V, key):
    st.subheader("Balance for every SKU, snapshot to end of horizon")
    charts.balance_table(V)
    st.subheader("One SKU in detail")
    s = st.selectbox("SKU", ORDER, key=f"wf_sku_{key}", format_func=sku_label)
    charts.waterfall(V, s, key)


def network_tab(V, key):
    import views.network as net                                   # the settings table from the first UI
    R = V["R"]
    mine = net.settings(R)
    st.dataframe(pd.DataFrame({"Setting": mine.index, "This scenario": mine.values}), hide_index=True,
                 width="stretch")
    s = st.selectbox("SKU", ORDER, key=f"net_sku_{key}", format_func=sku_label)
    st.plotly_chart(network_figure(s, R["obj"], routes=R["case"].ship_routes), key=f"net_{key}")
    st.caption("Circles: resources (opening level). Squares: tasks. Black edge adds, grey edge takes; +N wk = delay. "
               "Faded: ship routes this scenario does not use.")


# ---------------- page ----------------

ss = state.init()
if ss.get("toast"):
    st.toast(ss.pop("toast"), icon=":material/check:")
sidebar(ss)
key = ss.active
case = ss.cases[key]
V = state.view(key)
V0 = state.view(ss.compare_to) if ss.compare_to != key else None

st.caption("SCENARIO WORKBENCH" + ("" if state.locked(key) else f" · based on {case.parent}"))
st.title(case.name)
st.markdown(case.summary)
rl = V["rules"]
st.caption(f"Routing: {rl['Routing rule']} · Build time: {rl['Build time']} · Reno → PDC: "
           f"{rl['Reno → PDC transfer']} · The plan decides: {rl['The plan decides']}.")
charts.kpis(V, V0)
chk = V["checks"]
with st.expander(f"Plan checks: {int(chk['pass'].sum())} of {len(chk)} pass", expanded=not chk["pass"].all(),
                 icon=":material/check_circle:" if chk["pass"].all() else ":material/error:"):
    st.dataframe(chk.assign(Result=chk["pass"].map({True: "pass", False: "FAIL"})).drop(columns="pass")
                 .rename(columns={"check": "Check", "value": "Value"}), hide_index=True, width="stretch")

tabs = st.tabs(["Plan", "Priors", "Targets", "Balance", "Network"])
with tabs[0]:
    plan_tab(V, key)
with tabs[1]:
    priors_tab(ss, key, V0)
with tabs[2]:
    targets_tab(V, key)
with tabs[3]:
    balance_tab(V, key)
with tabs[4]:
    network_tab(V, key)
