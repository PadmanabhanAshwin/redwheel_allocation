"""Scenarios: each featured scenario in the same template, one at a time (a hidden tab would draw at no width)."""
import streamlit as st

from planner2_demo import state, views

ss = state.init()
SHORT = state.short_names()
st.title("Scenarios")
k = st.radio("Scenario", list(state.FEATURED), format_func=SHORT.get, horizontal=True, key="scen_pick",
             label_visibility="collapsed")
slot = st.empty()                                    # planning spinner
V, err = state.safe_view(k, slot)
if V is None:
    st.error(f"{k} cannot be planned: {err}", icon=":material/error:")
else:
    views.template(k, V)
