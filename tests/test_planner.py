"""The planner (second UI): change lists, saved scenarios, the priors editor, and the workbench flow."""
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from redwheel import priors, scenarios as sc, store

PLANNER = Path(__file__).resolve().parents[1] / "planner"


# ---------------- change lists: what a person or an LLM proposes ----------------

def test_a_to_b_is_eight_changes_and_applying_them_gives_b():
    d = priors.diff(sc.CASE_A.priors, sc.CASE_B.priors)
    assert len(d) == 8
    assert priors.apply_changes(sc.CASE_A.priors, d).equals(priors.normalise(sc.CASE_B.priors))
    assert priors.diff(sc.CASE_B.priors, sc.CASE_B.priors) == []


def test_change_list_can_add_and_remove_rows():
    t = priors.apply_changes(sc.CASE_A.priors, [
        {"prior": "target_weeks", "applies_to": "mtb_carbon", "from_date": "2027-09-06", "new": "18"},
        {"prior": "target_weeks", "applies_to": "road", "from_date": "2028-01-03", "new": None}])
    p = t[t["prior"] == "target_weeks"]
    assert ("mtb_carbon", "2027-09-06", "18") in set(zip(p["applies_to"], p["from_date"], p["value"]))
    assert "2028-01-03" not in set(p["from_date"])
    assert [priors.describe_change(c) for c in priors.diff(sc.CASE_A.priors, t)] == [
        "target_weeks · road from 2028-01-03: removed (was 10)", "target_weeks · mtb_carbon from 2027-09-06: added (18)"]


def test_same_settings_written_differently_are_the_same_table():
    t = sc.CASE_B.priors.copy()
    t["value"] = t["value"].map(lambda v: float(v) if v.isdigit() else v)        # 1.0 instead of "1"
    assert priors.diff(sc.CASE_B.priors, t.iloc[::-1]) == []


# ---------------- saved scenarios ----------------

def test_save_and_load_round_trip(tmp_path):
    c = sc.Case("C", "Scenario C · test", priors.apply_changes(sc.CASE_B.priors, [
        {"prior": "build_weeks", "applies_to": "mtb-carbon", "new": "2"}]), "a test", "B")
    store.save(c, tmp_path)
    back = store.load_all(tmp_path)["C"]
    assert (back.name, back.summary, back.parent) == (c.name, c.summary, c.parent)
    assert priors.diff(c.priors, back.priors) == []
    assert back.build_weeks["mtb-carbon"] == 2
    store.delete("C", tmp_path)
    assert store.load_all(tmp_path) == {}


# ---------------- the editor gives back what it was given ----------------

def _editor_round_trip(key, planner_dir, app_dir):
    import sys
    sys.path[:0] = [planner_dir, app_dir]
    import streamlit as st
    from priors_editor import editor
    from redwheel import scenarios as sc
    st.session_state["out"] = editor(sc.CASES[key].priors, locked=False, key="t")


@pytest.mark.parametrize("key", ["A", "B"])
def test_untouched_editor_returns_the_same_table(key):
    at = AppTest.from_function(_editor_round_trip, args=(key, str(PLANNER), str(PLANNER.parent / "app")),
                               default_timeout=120).run()
    assert not at.exception, [e.message for e in at.exception]
    assert priors.diff(sc.CASES[key].priors, at.session_state["out"]) == []


# ---------------- the workbench ----------------

@pytest.fixture
def planner(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "FOLDER", tmp_path)                 # saved scenarios go to a scratch folder
    return AppTest.from_file(str(PLANNER / "app.py"), default_timeout=180).run()


def test_workbench_opens_on_scenario_a(planner):
    assert not planner.exception, [e.message for e in planner.exception]
    assert planner.title[0].value == "Scenario A · base case"
    assert [t.label for t in planner.tabs] == ["Plan", "Priors", "Targets", "Balance", "Network"]


def test_every_scenario_renders(planner):
    for key in sc.CASES:
        planner.sidebar.radio[0].set_value(key).run()
        assert not planner.exception, (key, [e.message for e in planner.exception])
        assert planner.title[0].value == sc.CASES[key].name


def test_duplicate_then_delete(planner, tmp_path):
    planner.sidebar.radio[0].set_value("B").run()
    next(b for b in planner.sidebar.button if b.label == "Copy this scenario").click().run()
    assert not planner.exception
    assert planner.title[0].value == "Scenario C · copy of B"
    assert (tmp_path / "C.json").exists()
    assert priors.diff(sc.CASE_B.priors, store.load_all(tmp_path)["C"].priors) == []
    next(b for b in planner.sidebar.button if b.label == "Delete this scenario").click().run()
    assert not planner.exception and planner.title[0].value == "Scenario B · web via PDC, others direct"
    assert not (tmp_path / "C.json").exists()


def test_compare_page(planner):
    planner.switch_page("compare.py").run()
    assert not planner.exception, [e.message for e in planner.exception]
    assert planner.title[0].value == "Compare Scenarios"


# ---------------- the Ask box (a fake model stands in for the API) ----------------

from redwheel import llm                                            # noqa: E402
from test_llm import A_TO_B, FakeClient, answer                     # noqa: E402

REAL_PROPOSE = llm.propose


def fake_model(monkeypatch, *answers):
    client = FakeClient(*answers)
    monkeypatch.setattr(llm, "propose", lambda req, table, obj, client_=None: REAL_PROPOSE(req, table, obj, client))


def copy_of(planner, key):
    planner.sidebar.radio[0].set_value(key).run()
    next(b for b in planner.sidebar.button if b.label == "Copy this scenario").click().run()
    return planner.title[0].value


def ask(planner, key, text):
    planner.text_area(key=f"ask_{key}").input(text)
    planner.button(key=f"ask_btn_{key}").click().run()
    assert not planner.exception, [e.message for e in planner.exception]


def test_ask_loads_a_proposal_for_review_and_apply_replans(planner, tmp_path, monkeypatch):
    fake_model(monkeypatch, answer(A_TO_B))
    assert copy_of(planner, "A") == "Scenario C · copy of A"
    ask(planner, "C", "describe scenario B")
    assert any("Proposed 8 changes" in s.value for s in planner.success)
    changes = next(md.value for md in planner.markdown if md.value.startswith("- route"))
    assert changes.count("\n") == 7 and "*test*" in changes                      # 8 changes, each with its reason
    assert store.load_all(tmp_path)["C"].priors.equals(sc.CASE_A.priors)        # nothing applied yet
    next(b for b in planner.button if b.label == "Apply and re-plan").click().run()
    assert not planner.exception
    assert priors.diff(store.load_all(tmp_path)["C"].priors, sc.CASE_B.priors) == []
    held = next(mt for mt in planner.metric if mt.label == "All targets held from")
    assert held.value == "27 Sep 2027"                                           # scenario B's result


def test_discard_clears_a_loaded_proposal(planner, monkeypatch):
    fake_model(monkeypatch, answer(A_TO_B))
    copy_of(planner, "A")
    ask(planner, "C", "describe scenario B")
    next(b for b in planner.button if b.label == "Discard changes").click().run()
    assert not any(b.label == "Apply and re-plan" for b in planner.button)
    assert not any("Proposed" in s.value for s in planner.success)


def test_unsupported_unclear_or_failed_requests_load_nothing(planner, monkeypatch):
    fake_model(monkeypatch, answer(unsupported=["conditional shipping"]), answer(question="Better how?"))
    copy_of(planner, "B")
    ask(planner, "C", "ship from Reno when the PDC is short")
    assert any("conditional shipping" in i.value for i in planner.info)
    ask(planner, "C", "make it better")
    assert any("Better how?" in i.value for i in planner.info)
    assert not any(b.label == "Apply and re-plan" for b in planner.button)

    def broken(*a, **k):
        raise ConnectionError("no network")
    monkeypatch.setattr(llm, "propose", broken)
    ask(planner, "C", "anything")
    assert any("no network" in e.value for e in planner.error)


def test_locked_scenarios_have_no_ask_box(planner):
    for key in sc.CASES:
        planner.sidebar.radio[0].set_value(key).run()
        assert not [t for t in planner.text_area if t.key == f"ask_{key}"]
