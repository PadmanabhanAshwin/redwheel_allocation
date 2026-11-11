"""Planner state: the scenarios in this session, unapplied edits to their priors, and cached runs.

Scenarios A and B are built in and locked; any other scenario is a copy, saved to outputs/scenarios/ and editable.
A run is cached on the scenario's priors table, so a change re-plans and an unchanged scenario does not."""
import io
from dataclasses import replace

import pandas as pd
import streamlit as st

from redwheel import priors, scenarios as sc, store
import ui

BUILT_IN = sc.CASES


def init():
    ss = st.session_state
    if "cases" not in ss:
        ss.cases = {**BUILT_IN, **{k: c for k, c in store.load_all().items() if k not in BUILT_IN}}
        ss.active, ss.compare_to = "A", "A"
        ss.version = 0                      # bumped to reset the priors editors
        ss.loaded = {}                      # key -> an LLM proposal loaded into the editors, not yet applied
        ss.ask_note = {}                    # key -> (kind, message) from the last request to the LLM
    return ss


def locked(key: str) -> bool:
    return key in BUILT_IN


@st.cache_resource(max_entries=32, show_spinner=False)   # the spinner is drawn by view(), in the sidebar
def _run(key: str, name: str, summary: str, parent: str, table_csv: str) -> dict:
    t = pd.read_csv(io.StringIO(table_csv), dtype=str, keep_default_na=False)
    return ui.view_of(sc.run_case(sc.Case(key, name, t, summary, parent)))


def view(key: str) -> dict:
    """A scenario's results, planned on first use. The spinner goes in the sidebar: an element that comes and goes
    above the workbench tabs would make Streamlit treat them as new and jump back to the first tab."""
    c = st.session_state.cases[key]
    with st.sidebar, st.spinner(f"Planning {c.name} …"):
        return _run(c.key, c.name, c.summary, c.parent, priors.normalise(c.priors).to_csv(index=False))


def next_key() -> str:
    used = set(st.session_state.cases)
    return next(k for k in (chr(c) for c in range(ord("C"), ord("Z") + 1)) if k not in used)


def duplicate(key: str) -> str:
    ss = st.session_state
    src = ss.cases[key]
    k = next_key()
    ss.cases[k] = sc.Case(k, f"Scenario {k} · copy of {key}", priors.normalise(src.priors),
                          f"A copy of scenario {key}; change its priors to explore.", key)
    store.save(ss.cases[k])
    ss.active, ss.compare_to = k, key
    ss.version += 1
    return k


def clear_proposal(key: str) -> None:
    st.session_state.loaded.pop(key, None)
    st.session_state.ask_note.pop(key, None)


def delete(key: str) -> None:
    ss = st.session_state
    if locked(key):
        return
    store.delete(key)
    clear_proposal(key)
    parent = ss.cases.pop(key).parent
    ss.active = parent if parent in ss.cases else "A"
    if ss.compare_to == key:
        ss.compare_to = "A"
    ss.version += 1


def apply(key: str, table: pd.DataFrame) -> None:
    ss = st.session_state
    ss.cases[key] = replace(ss.cases[key], priors=priors.normalise(table))
    store.save(ss.cases[key])
    clear_proposal(key)
    ss.version += 1


def rename(key: str, name: str, summary: str) -> None:
    ss = st.session_state
    ss.cases[key] = replace(ss.cases[key], name=name, summary=summary)
    store.save(ss.cases[key])
