"""The two layouts the pages share.

    template(k, V, V0, title)    one scenario: its summary (the scenario, objective, constraints, outputs), builds by
                                 line and month, the supply map, the build plan
    differences(V, V0, key)      one plan against another: what was changed, the four measures and their change, the
                                 two supply maps one above the other, the build plan table (changed cells shaded)"""
from __future__ import annotations

import html

import streamlit as st

from planner2_demo import charts, pivot, reading as rd


def strip(items: list, cls: str = ""):
    """[(label, value)] as one row of small labelled values."""
    cells = "".join(f"<div><span>{html.escape(a)}</span>{html.escape(b)}</div>" for a, b in items)
    st.markdown(f"<div class='rw-strip {cls}'>{cells}</div>", unsafe_allow_html=True)


def scorecard(items: list):
    """[(label, value, change, tone)] as one row: each value, and its change against the reference."""
    st.markdown(f"<div class='rw-strip rw-score'>{_score_html(items)}</div>", unsafe_allow_html=True)


def _change_html(change, what, a, b) -> str:
    return (f"<b>{html.escape(change)}</b>" + (f" · {html.escape(what)}" if what else "")
            + f": {html.escape(a)} → <b>{html.escape(b)}</b>")


def change_lines(V, V0) -> list:
    """What V sets differently from V0, one line each; returns them."""
    lines = rd.change_lines(V0["case"], V["case"], V)
    for line in lines:
        st.markdown(f"<div class='rw-change'>{_change_html(*line)}</div>", unsafe_allow_html=True)
    return lines


def _score_html(items: list) -> str:
    return "".join(f"<div><span>{html.escape(a)}</span>{html.escape(b)}"
                   + (f" <em class='{t}'>{html.escape(d)}</em>" if d else "") + "</div>" for a, b, d, t in items)


def _tiles(items: list) -> str:
    """[(label, value html)] as a grid of small labelled tiles."""
    return "<div class='rw-tiles'>" + "".join(f"<div><span>{html.escape(a)}</span>{b}</div>" for a, b in items) + "</div>"


def summary(V, V0, description: str):
    """Labelled rows: the scenario (what it is, and what it changes from the one it is built on), the supply chain it
    plans (sourcing, build lead time, capacity, decisions, priority), the targets per line, the objective as its
    ordered steps, and the outputs with their change."""
    case, a = V["case"], dict(rd.assumptions(V))
    scen = f"<div class='lead'>{html.escape(description)}</div>"
    if V0 is not None:
        lines = rd.change_lines(V0["case"], case, V)
        k0 = html.escape(V0["case"].key)
        scen += (f"<div class='rw-delta'><span>Changed from {k0}</span>"
                 + "".join(f"<div>{_change_html(*x)}</div>" for x in lines) + "</div>") if lines else \
            f"<div class='sub'>Same settings as {k0}</div>"
    pooled = len(V["R"]["pools"]) == 1
    supply = [("Stock serves orders from", "Reno + PDC, pooled for every order" if pooled else html.escape(a["Sourcing"])),
              ("Build lead time", html.escape(a["Build lead time"])),
              ("Capacity", "each line's weekly capacity, as given"),
              ("Plan decides", html.escape(a["Decisions"])),
              ("Priority", html.escape(a["Priority"]))]
    if not pooled:
        supply.insert(1, ("Reno to the PDC", html.escape(a["Transfer lead time"])))
    targets = "".join(f"<span class='chip'>{html.escape(t)}</span>" for t in a["Targets (weeks of supply)"].split(" · "))
    steps = "".join(f"<li>{html.escape(s)}</li>" for s in rd.objective_steps(case))
    rows = [("Scenario", scen),
            ("Supply chain", _tiles(supply)),
            ("Targets", f"<div class='rw-chips'>{targets}<span class='note'>weeks of supply</span></div>"),
            ("Objective", f"<div class='sub'>Minimise, in order:</div><ol class='rw-steps'>{steps}</ol>"),
            ("Outputs", f"<div class='rw-strip rw-score'>{_score_html(rd.kpis(V, V0))}</div>")]
    cells = "".join(f"<div class='k'>{k}</div><div class='v'>{v}</div>" for k, v in rows)
    st.markdown(f"<div class='rw-sum'>{cells}</div>", unsafe_allow_html=True)


def template(k: str, V: dict, V0: dict | None = None, title: str = "", description: str = ""):
    """One scenario. V0: the scenario it is built on (its changes and the outputs' change are read against it)."""
    st.subheader(title + (f", against {V0['case'].key}" if V0 is not None else ""))
    summary(V, V0, description)
    st.plotly_chart(charts.plan_figure(V, V0), key=f"plan_{k}", config={"displayModeBar": False})
    st.plotly_chart(charts.supply_map_figure(V, against=V0), key=f"map_{k}", config={"displayModeBar": False})
    st.markdown("**Build plan**")
    pivot.render(rd.pivot_data(V))
    with st.container(horizontal=True):
        st.download_button("Weekly build plan (CSV)", rd.build_csv(V), file_name=f"build_plan_{k}.csv",
                           mime="text/csv", key=f"dl_{k}", icon=":material/download:")
        tc = rd.transfer_csv(V)
        if tc is not None:
            st.download_button("Weekly transfers to the PDC (CSV)", tc, file_name=f"transfers_{k}.csv",
                               mime="text/csv", key=f"dlm_{k}", icon=":material/download:")


def differences(V, V0, key: str):
    """One plan against another: what was changed, the four measures, the two supply maps, the build plan table."""
    k0 = V0["case"].key
    lines = change_lines(V, V0)
    scorecard(rd.kpis(V, V0))
    if rd.same_plan(V, V0):
        st.success(f"Same build plan as {k0}." if lines else f"Same settings and build plan as {k0}.",
                   icon=":material/check_circle:")
        return
    st.plotly_chart(charts.supply_map_figure(V, V0), key=f"map_{key}", config={"displayModeBar": False})
    st.markdown("**Build plan**")
    pivot.render(rd.pivot_compare(V, V0), height=640)
