"""The two layouts the pages share.

    template(k, V)               one scenario: assumptions, measures, build plan by line, build plan table
    differences(V, V0, key)      one scenario against another: headline measures and their change, what was changed,
                                 both plans' builds by quarter or month, cumulative builds ahead or behind,
                                 the build plan table of differences"""
from __future__ import annotations

import html

import streamlit as st

from planner2 import charts, pivot, reading as rd
from ui import LINES


def strip(items: list):
    """[(label, value)] as one row of small labelled values."""
    cells = "".join(f"<div><span>{html.escape(a)}</span>{html.escape(b)}</div>" for a, b in items)
    st.markdown(f"<div class='rw-strip'>{cells}</div>", unsafe_allow_html=True)


def template(k: str, V: dict):
    strip(rd.assumptions(V))
    st.plotly_chart(charts.plan_figure(V), key=f"plan_{k}", config={"displayModeBar": False})
    st.markdown("**Build plan**")
    pivot.render(rd.pivot_data(V))
    with st.container(horizontal=True):
        st.download_button("Weekly build plan (CSV)", rd.build_csv(V), file_name=f"build_plan_{k}.csv",
                           mime="text/csv", key=f"dl_{k}", icon=":material/download:")
        tc = rd.transfer_csv(V)
        if tc is not None:
            st.download_button("Weekly transfers to the PDC (CSV)", tc, file_name=f"transfers_{k}.csv",
                               mime="text/csv", key=f"dlm_{k}", icon=":material/download:")


def headline(items: list):
    """[(label, value, change, tone)] as one row: the value, and its change against the reference."""
    cells = "".join(f"<div><span>{html.escape(a)}</span>{html.escape(b)}"
                    + (f" <em class='{t}'>{html.escape(d)}</em>" if d else "") + "</div>" for a, b, d, t in items)
    st.markdown(f"<div class='rw-strip'>{cells}</div>", unsafe_allow_html=True)


def differences(V, V0, key: str):
    """One plan against another: the headline measures, what was changed, the difference by line and month, and the
    build plan table of differences."""
    case, case0 = V["case"], V0["case"]
    k, k0 = case.key, case0.key
    headline(rd.headline(V, V0))
    wc = rd.what_changed(case0, case, V)
    for r in rd.grouped_changes(wc):
        n = f" <span class='n'>· {r['Numbers']} numbers</span>" if r["Numbers"] else ""
        st.markdown(f"<div class='rw-change'><b>{html.escape(r['Change'])}</b> · {html.escape(r['What'])}: "
                    f"{html.escape(r['From'])} → <b>{html.escape(r['To'])}</b>{n}</div>", unsafe_allow_html=True)
    if wc.empty:
        st.caption(f"{k} and {k0} have the same settings, data and priority.")
    if rd.same_plan(V, V0):
        st.success(f"The same build plan as {k0}, bike by bike and week by week.", icon=":material/check_circle:")
        return
    moved = rd.lines_changed(V, V0)
    same = [rd.LINE_WORDS[ln] for ln in LINES if ln not in moved]
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    c1.markdown(f"**Builds: {k0} (faded) and {k}**" + (f" · same as {k0}: {', '.join(same)}" if same else ""))
    level = c2.radio("Period", ["Quarter", "Month"], horizontal=True, key=f"lvl_{key}", label_visibility="collapsed")
    st.plotly_chart(charts.side_by_side_figure(V, V0, moved, level), key=f"side_{key}_{level}",
                    config={"displayModeBar": False})
    st.markdown(f"**Ahead of or behind {k0}**")
    st.plotly_chart(charts.ahead_figure(V, V0, moved), key=f"ahead_{key}", config={"displayModeBar": False})
    st.markdown("**Build plan**")
    pivot.render(rd.pivot_compare(V, V0), height=560)
