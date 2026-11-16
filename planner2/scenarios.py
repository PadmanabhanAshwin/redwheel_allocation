"""Scenarios: each featured scenario in the same template."""
import streamlit as st

from planner2 import state, views

ss = state.init()
st.title("Scenarios")
slot = st.empty()                                    # planning spinner; always drawn so the tabs keep their place
planned = {k: state.safe_view(k, slot) for k in state.FEATURED}
for tab, k in zip(st.tabs([state.short(k) for k in state.FEATURED]), state.FEATURED):
    with tab:
        V, err = planned[k]
        if V is None:
            st.error(f"{k} cannot be planned: {err}", icon=":material/error:")
        else:
            views.template(k, V)
