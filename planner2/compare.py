"""Compare: the featured scenarios side by side, then the differences between any two."""
import streamlit as st

from planner2 import reading as rd, state, views
from planner2.components import ask, table

ss = state.init()
SHORT = state.short_names()
keys = list(ss.cases)
st.title("Compare")
slot = st.empty()
planned = {k: state.safe_view(k, slot) for k in state.FEATURED}
ok = {k: V for k, (V, _) in planned.items() if V is not None}

st.subheader("Summary")
table(rd.summary(ok), index=True)
st.table(rd.assumptions_table(ok))

st.subheader("Differences")
k, k0 = ss.pair if all(x in ss.cases for x in ss.pair) else (state.FEATURED[1], state.FEATURED[0])


def pick():
    ss.pair = (ss["_k"], ss["_k0"])


c = st.columns([2, 2, 1], vertical_alignment="bottom")
ss["_k"], ss["_k0"] = k, k0
c[0].selectbox("Scenario", keys, key="_k", format_func=SHORT.get, on_change=pick)
c[1].selectbox("Against", keys, key="_k0", format_func=SHORT.get, on_change=pick)
V, e = state.safe_view(k, slot)
V0, e0 = state.safe_view(k0, slot)
if V is None or V0 is None:
    st.error(f"Cannot be planned: {e or e0}", icon=":material/error:")
    st.stop()
with c[2]:
    ask([(k0, ss.cases[k0], V0), (k, ss.cases[k], V)], [f"Why does {k} differ from {k0}?"], key=f"ask_{k0}_{k}")
if k == k0:
    st.caption("Pick two different scenarios.")
else:
    views.differences(V, V0, key=f"{k0}_{k}")
