"""The two layouts the pages share.

    template(k, V, V0, title)    one scenario, as its deck slide: what it changes from the scenario it is built on, the
                                 four measures and their change, its settings, builds by line and month, the build plan
    differences(V, V0, key)      one plan against another: what was changed, the four measures and their change, the
                                 phases of every line and bike, the build plan table of differences"""
from __future__ import annotations

import html

import streamlit as st

from planner2_demo import charts, phases, pivot, reading as rd


def strip(items: list, cls: str = ""):
    """[(label, value)] as one row of small labelled values."""
    cells = "".join(f"<div><span>{html.escape(a)}</span>{html.escape(b)}</div>" for a, b in items)
    st.markdown(f"<div class='rw-strip {cls}'>{cells}</div>", unsafe_allow_html=True)


def scorecard(items: list):
    """[(label, value, change, tone)] as one row: each value, and its change against the reference."""
    cells = "".join(f"<div><span>{html.escape(a)}</span>{html.escape(b)}"
                    + (f" <em class='{t}'>{html.escape(d)}</em>" if d else "") + "</div>" for a, b, d, t in items)
    st.markdown(f"<div class='rw-strip rw-score'>{cells}</div>", unsafe_allow_html=True)


def change_lines(V, V0) -> list:
    """What V sets differently from V0, one line each; returns them."""
    lines = rd.change_lines(V0["case"], V["case"], V)
    for change, what, a, b in lines:
        st.markdown(f"<div class='rw-change'><b>{html.escape(change)}</b>"
                    + (f" · {html.escape(what)}" if what else "")
                    + f": {html.escape(a)} → <b>{html.escape(b)}</b></div>", unsafe_allow_html=True)
    return lines


def template(k: str, V: dict, V0: dict | None = None, title: str = ""):
    """One scenario. V0: the scenario it is built on (its changes and the measures' change are read against it)."""
    st.subheader(title + (f", against {V0['case'].key}" if V0 is not None else ""))
    if V0 is not None:
        change_lines(V, V0)
    scorecard(rd.kpis(V, V0))
    strip(rd.assumptions(V), "rw-set")
    st.plotly_chart(charts.plan_figure(V, V0), key=f"plan_{k}", config={"displayModeBar": False})
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
    """One plan against another: what was changed, the four measures, the phases, the build plan table."""
    k0 = V0["case"].key
    lines = change_lines(V, V0)
    scorecard(rd.kpis(V, V0))
    if rd.same_plan(V, V0):
        st.success(f"Same build plan as {k0}." if lines else f"Same settings and build plan as {k0}.",
                   icon=":material/check_circle:")
        return
    phases.render(rd.phase_data(V, V0))
    st.markdown("**Build plan**")
    pivot.render(rd.pivot_compare(V, V0), height=640)
