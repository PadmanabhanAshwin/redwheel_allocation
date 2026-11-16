"""Session state for the planner: the scenarios, what each view has open, and cached plan runs.

Built in and locked: the featured scenarios (shown on Scenarios and Compare) and the example changes E1–E5 (listed on
Try a change). Every other scenario is a run made on Try a change, saved to outputs/scenarios/ (settings, changes and
priority order; a plan is recomputed in a second or two)."""
from __future__ import annotations

import io
import json

import pandas as pd
import streamlit as st

from redwheel import changes as ch, priors, scenarios as sc, store, walk as wk
import ui

BUILT_IN = {c.key: c for c in (sc.CASE_A, sc.CASE_B, sc.CASE_E1, sc.CASE_E2, sc.CASE_E3, sc.CASE_E4, sc.CASE_E5,
                               sc.CASE_P1)}
FEATURED = ("A", "B", "P1")          # the scenarios the Scenarios and Compare views show; chosen with the solver session
EXAMPLES = ("E1", "E2", "E3", "E4", "E5")    # ready-made changes on A, listed on Try a change beside the user's runs
BASE = "A"


def init():
    ss = st.session_state
    if "cases" not in ss:
        ss.cases = {**BUILT_IN, **{k: c for k, c in store.load_all().items() if k not in BUILT_IN}}
        ss.pair = (FEATURED[1], FEATURED[0])         # Compare: (scenario, against)
        ss.run = EXAMPLES[0]                          # Try a change: the run on screen
    return ss


def locked(key: str) -> bool:
    return key in BUILT_IN


def short(key: str) -> str:
    """'Scenario B · web via PDC, others direct' -> 'B · web via PDC, others direct'."""
    n = st.session_state.cases[key].name
    return n[len("Scenario "):] if n.startswith("Scenario ") else n


def short_names() -> dict:
    """{key: short name} now. Use `.get` of it as a widget's format_func: it must not read session state later."""
    return {k: short(k) for k in st.session_state.cases}


# ---------------- plan runs ----------------

def changes_text(changes) -> str:
    return json.dumps(ch.to_records(changes), sort_keys=True)


def walk_text(walk) -> str:
    return json.dumps(wk.to_record(walk), sort_keys=True)


@st.cache_resource(max_entries=48, show_spinner=False)
def _run(key: str, name_: str, summary: str, parent: str, table_csv: str, changes_json_: str = "[]",
         walk_json_: str = "null") -> dict:
    """Cached on everything the run reads: the settings table, the changes and the priority order."""
    t = pd.read_csv(io.StringIO(table_csv), dtype=str, keep_default_na=False)
    case = sc.Case(key, name_, t, summary, parent, ch.from_records(json.loads(changes_json_)),
                   wk.from_record(json.loads(walk_json_)))
    return ui.view_of(sc.run_case(case))


def view(key: str, slot=None) -> dict:
    """A scenario's computed plan (cached). While it is computed a spinner shows in `slot`, a placeholder the page
    always draws, so nothing above the page's tabs appears or disappears between runs."""
    c = st.session_state.cases[key]
    args = (c.key, c.name, c.summary, c.parent, priors.normalise(c.priors).to_csv(index=False),
            changes_text(c.changes), walk_text(c.walk))
    if slot is None:
        return _run(*args)
    with slot.container():
        with st.spinner(f"Planning {c.name} …"):
            out = _run(*args)
    slot.empty()
    return out


def safe_view(key: str, slot=None):
    """(view, None) or (None, reason) when a scenario cannot be planned (e.g. a saved file edited by hand)."""
    try:
        return view(key, slot), None
    except Exception as e:                           # shown to the planner; the rest of the app keeps working
        return None, f"{type(e).__name__}: {e}"


# ---------------- the user's scenarios ----------------

def next_key() -> str:
    """The next free letter, skipping E and P (the families of the built-in events and priority orders)."""
    used = set(st.session_state.cases)
    return next(k for k in "CDFGHIJKLMNOQRSTUVWXYZ" if k not in used)


def add(case: sc.Case) -> str:
    """Save a new scenario (the case's own key is replaced by the next free one) and return its key."""
    ss = st.session_state
    k = next_key()
    name = case.name if case.name.startswith(f"Scenario {k}") else f"Scenario {k} · {case.name}"
    ss.cases[k] = sc.Case(k, name, priors.normalise(case.priors), case.summary, case.parent, tuple(case.changes),
                          case.walk)
    store.save(ss.cases[k])
    return k


def delete(key: str) -> None:
    ss = st.session_state
    if locked(key):
        return
    store.delete(key)
    ss.cases.pop(key)
    if key in ss.pair:
        ss.pair = (FEATURED[1], FEATURED[0])
    if ss.run == key:
        ss.run = EXAMPLES[0]
