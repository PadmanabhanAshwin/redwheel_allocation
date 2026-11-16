"""Scenario Summary: every scenario, one at a time, in the same template. The panel on the left lists the built-in set
in the deck's order (A, R, R+, then the live set on R+), then the runs made on Try a change, each with one line on what
it is. Each scenario is read against the one it is built on."""
import streamlit as st

from planner2_demo import state, views
from planner2_demo.components import delete_control

ss = state.init()
st.title("Scenario Summary")
keys = list(ss.cases)
if ss.get("scen_pick") not in keys:                  # first visit, or the run on screen was removed
    ss["scen_pick"] = state.BASE
pick, page = st.columns([1.15, 3.3], gap="large")
with pick:
    bold = {x: f"**{x}**" for x in keys}
    k = st.radio("Scenario", keys, key="scen_pick", format_func=bold.get,
                 captions=[state.describe(x) for x in keys], label_visibility="collapsed")
    delete_control(k, key="scen")
with page:
    slot = st.empty()                                # planning spinner
    V, err = state.safe_view(k, slot)
    parent = ss.cases[k].parent
    V0, err0 = state.safe_view(parent, slot) if parent in ss.cases else (None, None)
    if V is None:
        st.error(f"{k} cannot be planned: {err}", icon=":material/error:")
    else:
        views.template(k, V, V0, title=state.short(k), description=state.sentence(k))
