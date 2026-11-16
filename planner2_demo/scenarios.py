"""Scenarios: every scenario, one at a time, in the same template: the built-in set in the deck's order (A, R, R+, then
the live set on R+), then the runs made on Try a change. Each is read against the scenario it is built on."""
import streamlit as st

from planner2_demo import state, views

ss = state.init()
st.title("Scenarios")
keys = list(ss.cases)
if ss.get("scen_pick") not in keys:                  # first visit, or the run on screen was removed
    ss["scen_pick"] = state.BASE
k = st.radio("Scenario", keys, horizontal=True, key="scen_pick", label_visibility="collapsed")
slot = st.empty()                                    # planning spinner
V, err = state.safe_view(k, slot)
parent = ss.cases[k].parent
V0, err0 = state.safe_view(parent, slot) if parent in ss.cases else (None, None)
if V is None:
    st.error(f"{k} cannot be planned: {err}", icon=":material/error:")
else:
    views.template(k, V, V0, title=state.short(k))
