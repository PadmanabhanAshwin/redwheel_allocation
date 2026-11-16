"""Ask: Claude, answering from the facts of the plans on screen only."""
from __future__ import annotations

import streamlit as st

from planner2_demo import facts
from redwheel import llm


def _fill(key, text):
    st.session_state[key] = text


def ask(items: list, examples: list, key: str):
    """A small Ask popover: a question about the plans in `items` ([(key, case, view)], the first is the reference)."""
    ss = st.session_state
    with st.popover("Ask", icon=":material/forum:", width="stretch"):
        q = st.text_input("Question", key=f"{key}_q", label_visibility="collapsed", placeholder="Question")
        with st.container(horizontal=True):
            for i, ex in enumerate(examples):
                st.button(ex, key=f"{key}_ex{i}", on_click=_fill, args=(f"{key}_q", ex), width="content")
        if st.button("Ask", type="primary", key=f"{key}_go"):
            if not q.strip():
                ss[f"{key}_a"] = ("warn", "Type a question first, or pick one.")
            else:
                try:
                    with st.spinner("Reading the plans …"):
                        ss[f"{key}_a"] = ("ok", llm.explain(q.strip(), facts.facts(items))["answer"])
                except Exception as e:                       # shown, never raised
                    ss[f"{key}_a"] = ("warn", f"The question did not go through ({type(e).__name__}: {e}).")
        a = ss.get(f"{key}_a")
        if a:
            (st.markdown if a[0] == "ok" else st.warning)(a[1])
