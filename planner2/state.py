"""Session state for the planner: the scenarios, which one is open, what it is compared with, the what-if draft,
and cached plan runs.

Scenarios A and B, and the two events E1 and E2 on A, are built in and locked. Every other scenario is the user's:
created from the What-if page, saved to outputs/scenarios/ (settings and events only; a plan is recomputed in about a
second) and editable or deletable."""
from __future__ import annotations

import io
import json
from dataclasses import replace

import pandas as pd
import streamlit as st

from redwheel import changes as ch, priors, scenarios as sc, store
import ui

BUILT_IN = {**sc.CASES, **sc.EVENTS}
BASE = "A"


def init():
    ss = st.session_state
    if "cases" not in ss:
        ss.cases = {**BUILT_IN, **{k: c for k, c in store.load_all().items() if k not in BUILT_IN}}
        ss.current = BASE                  # the scenario open on the Scenario page
        ss.compare_to = BASE               # what its headline numbers are compared with
        ss.draft = None                    # the what-if being built (see new_draft)
        ss.wv = 0                          # bumped to re-seed the what-if editors
    return ss


def locked(key: str) -> bool:
    return key in BUILT_IN


def name(key: str) -> str:
    return st.session_state.cases[key].name


def names() -> dict:
    """{key: name} now. Use `names().get` as a widget's format_func: it must not read session state later."""
    return {k: c.name for k, c in st.session_state.cases.items()}


def short_names() -> dict:
    """{key: 'B · web via PDC, others direct'} now, for compact pickers (same rule as names())."""
    return {k: short(k) for k in st.session_state.cases}


def short(key: str) -> str:
    """'Scenario B · web via PDC, others direct' -> 'B · web via PDC, others direct'."""
    n = name(key)
    return n[len("Scenario "):] if n.startswith("Scenario ") else n


# ---------------- plan runs ----------------

def changes_text(changes) -> str:
    """A list of changes as text: part of what a run is cached on."""
    return json.dumps(ch.to_records(changes), sort_keys=True)


def changes_json(key: str) -> str:
    return changes_text(st.session_state.cases[key].changes)


@st.cache_resource(max_entries=48, show_spinner=False)
def _run(key: str, name_: str, summary: str, parent: str, table_csv: str, changes_json_: str = "[]") -> dict:
    """Cached on everything the run reads: the settings table and the changes."""
    t = pd.read_csv(io.StringIO(table_csv), dtype=str, keep_default_na=False)
    changes = ch.from_records(json.loads(changes_json_))
    return ui.view_of(sc.run_case(sc.Case(key, name_, t, summary, parent, changes)))


def view(key: str, slot=None) -> dict:
    """A scenario's computed plan (cached on its settings). While a plan is computed, a spinner shows in `slot`, a
    placeholder the page always draws, so nothing above the page's tabs appears or disappears between runs."""
    c = st.session_state.cases[key]
    args = (c.key, c.name, c.summary, c.parent, priors.normalise(c.priors).to_csv(index=False), changes_json(key))
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


# ---------------- scenarios ----------------

def next_key() -> str:
    used = set(st.session_state.cases)
    return next(k for k in (chr(c) for c in range(ord("C"), ord("Z") + 1)) if k not in used)


def create(base: str, table: pd.DataFrame, name_: str, summary: str, changes=None) -> str:
    """A new scenario from `base`'s settings; its events are `changes` (default: base's)."""
    ss = st.session_state
    k = next_key()
    title = name_.strip() or "what-if"
    full = title if title.startswith(f"Scenario {k}") else f"Scenario {k} · {title}"
    ss.cases[k] = sc.Case(k, full, priors.normalise(table), summary.strip(), base,
                          ss.cases[base].changes if changes is None else tuple(changes))
    store.save(ss.cases[k])
    return k


def update(key: str, table: pd.DataFrame, name_: str, summary: str, changes=None) -> None:
    ss = st.session_state
    ss.cases[key] = replace(ss.cases[key], priors=priors.normalise(table), name=name_.strip() or ss.cases[key].name,
                            summary=summary.strip(),
                            changes=ss.cases[key].changes if changes is None else tuple(changes))
    store.save(ss.cases[key])


def delete(key: str) -> None:
    ss = st.session_state
    if locked(key):
        return
    store.delete(key)
    parent = ss.cases.pop(key).parent
    for k in [k for k, c in ss.cases.items() if c.parent == key]:     # children keep working; re-point their parent
        ss.cases[k] = replace(ss.cases[k], parent=parent if parent in ss.cases else BASE)
        store.save(ss.cases[k])
    if ss.current == key:
        ss.current = parent if parent in ss.cases else BASE
    if ss.compare_to == key or ss.compare_to not in ss.cases:
        ss.compare_to = BASE
    if ss.draft and ss.draft["base"] == key:
        ss.draft = None


def open_scenario(key: str, compare_to: str | None = None) -> None:
    ss = st.session_state
    ss.current = key
    if compare_to is not None:
        ss.compare_to = compare_to
    elif ss.compare_to == key and key != BASE:
        ss.compare_to = ss.cases[key].parent if ss.cases[key].parent in ss.cases else BASE


# ---------------- the what-if draft ----------------

def new_draft(base: str, edit: bool = False, keep_request: bool = False) -> None:
    """Start a what-if from scenario `base`: its settings seed the editors, and changes are shown against it.
    With edit=True (user scenarios only), running the draft updates `base` instead of creating a new scenario."""
    ss = st.session_state
    src = ss.cases[base]
    edit = bool(edit) and not locked(base)
    ss.draft = {"base": base, "edit": edit, "seed": priors.normalise(src.priors), "reasons": {}, "note": None,
                "name": src.name if edit else "", "summary": src.summary if edit else "",
                "changes": tuple(src.changes)}           # the events the draft will run with; start from the base's
    ss.pop("wi_last", None)                # the editors' last table belongs to the old draft
    if not keep_request:
        ss.pop("wi_req", None)
    ss.wv += 1
