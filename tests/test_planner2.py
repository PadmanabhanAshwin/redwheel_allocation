"""The scenario-first planner (planner2/): every page, every flow a planner takes, with fake models standing in for
the API. Saved scenarios go to a scratch folder."""
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from redwheel import llm, priors, scenarios as sc, store
from test_llm import A_TO_B, FakeClient, answer

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "planner2" / "app.py")
REAL_PROPOSE = llm.propose


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "FOLDER", tmp_path)
    return tmp_path


def start(page=None):
    at = AppTest.from_file(APP, default_timeout=240).run()
    if page:
        at.switch_page(page).run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def ok(at):
    assert not at.exception, [e.message for e in at.exception]
    return at


def widget(items, label):
    return next(w for w in items if w.label == label)


def button(at, label):
    return next(b for b in at.button if b.label == label)


def metric(at, label):
    return next(m.value for m in at.metric if m.label == label)


# ---------------- pages ----------------

@pytest.mark.parametrize("page, title", [
    (None, "Redwheel build planner"), ("scenario.py", "Scenario A · base case"), ("whatif.py", "What-if"),
    ("compare.py", "Compare scenarios"), ("ref_context.py", "Supply–Demand Context"),
    ("ref_demand.py", "Demand Sources"), ("ref_model.py", "Object Encoding"), ("ref_validation.py", "Model Validation")])
def test_every_page_renders(folder, page, title):
    at = start(page)
    assert at.title[0].value == title


def test_home_shows_every_scenario_and_opens_one(folder):
    store.save(sc.Case("C", "Scenario C · test", sc.CASE_B.priors, "a test", "B"), folder)
    at = start()
    assert {"Scenario A · base case", "Scenario B · web via PDC, others direct", "Scenario C · test"} <= \
        {md.value.strip("*") for md in at.markdown}
    at.button(key="home_open_B").click().run()
    ok(at)
    assert at.title[0].value == "Scenario B · web via PDC, others direct"


def test_every_tab_of_every_built_in_scenario(folder):
    at = start("scenario.py")
    for k in sc.CASES:
        at.selectbox(key="_current").set_value(k).run()
        ok(at)
        assert at.title[0].value == sc.CASES[k].name
        assert [t.label for t in at.tabs] == ["Summary", "Builds", "Inventory", "SKU detail", "Settings"]
    at.selectbox(key="_compare_to").set_value("A").run()
    ok(at)
    assert metric(at, "All targets held from") == "27 Sep 2027"


# ---------------- the settings editor ----------------

def _editor(table_json, planner_root, app_dir):
    import sys
    sys.path[:0] = [planner_root, app_dir]
    import pandas as pd
    import streamlit as st
    from planner2.components import settings_editor
    import io
    st.session_state["out"] = settings_editor(pd.read_json(io.StringIO(table_json), dtype=False), key="t")


def editor_round_trip(t):
    at = AppTest.from_function(_editor, args=(t.to_json(), str(ROOT), str(ROOT / "app")), default_timeout=120).run()
    assert not at.exception, [e.message for e in at.exception]
    return at.session_state["out"]


@pytest.mark.parametrize("key", list(sc.CASES))
def test_untouched_editor_gives_back_the_same_settings(key):
    assert priors.diff(sc.CASES[key].priors, editor_round_trip(sc.CASES[key].priors)) == []


def test_untouched_editor_keeps_unusual_targets():
    t = priors.apply_changes(sc.CASE_A.priors, [
        {"prior": "target_weeks", "applies_to": "mtb_carbon", "from_date": "2027-09-06", "new": "18"},
        {"prior": "target_weeks", "applies_to": "mtb_carbon", "from_date": "2028-03-06", "new": "16"},
        {"prior": "target_weeks", "applies_to": "mtb_base", "from_date": "2026-01-05", "new": "11"}])
    assert priors.diff(t, editor_round_trip(t)) == []


# ---------------- what-if: by hand ----------------

def set_b_by_hand(at):
    widget(at.radio, "Web orders").set_value("PDC").run()
    widget(at.radio, "Dealer orders").set_value("Reno").run()
    widget(at.radio, "Commercial orders").set_value("Reno").run()
    widget(at.toggle, "Plan transfers from Reno to the PDC").set_value(True).run()
    for ln in ("Road · base", "Road · carbon", "MTB · base", "MTB · carbon"):
        widget(at.number_input, f"Build · {ln}").set_value(1).run()
    return ok(at)


def test_what_if_by_hand_creates_b_and_opens_it(folder):
    at = set_b_by_hand(start("whatif.py"))
    assert any("Passes every check" in s.value for s in at.success)
    assert metric(at, "Targets held from") == "27 Sep 2027"           # the preview, before anything is saved
    assert store.load_all(folder) == {}
    review = next(df.value for df in at.dataframe if "Setting" in df.value.columns)
    assert dict(zip(review["Setting"], review["To"])) == {
        "Web orders ship from": "PDC", "Dealer orders ship from": "Reno", "Commercial orders ship from": "Reno",
        "Build time · Road · base": "1 week", "Build time · Road · carbon": "1 week", "Build time · MTB · base": "1 week",
        "Build time · MTB · carbon": "1 week", "Plan decides transfers to the PDC": "yes"}
    at.text_input(key=next(t.key for t in at.text_input if t.label == "Name")).input("Hand-built B").run()
    button(at, "Create and run scenario").click().run()
    ok(at)
    assert at.title[0].value == "Scenario C · Hand-built B"
    assert priors.diff(store.load_all(folder)["C"].priors, sc.CASE_B.priors) == []
    assert metric(at, "All targets held from") == "27 Sep 2027"


def test_rules_the_network_cannot_carry_out_block_the_run(folder):
    at = start("whatif.py")
    widget(at.toggle, "Plan transfers from Reno to the PDC").set_value(True).run()    # Reno and PDC share orders
    ok(at)
    assert any("same orders" in e.value for e in at.error)
    assert button(at, "Create and run scenario").disabled
    assert store.load_all(folder) == {}


def test_target_steps_can_be_added_and_removed(folder):
    at = start("whatif.py")
    next(b for b in at.button if b.key and b.key.startswith("tadd_mtb_carbon")).click().run()
    ok(at)
    review = next(df.value for df in at.dataframe if "Setting" in df.value.columns)
    assert review["Setting"].str.startswith("Target · MTB carbon from").any()
    next(b for b in at.button if b.key and b.key.startswith("trm_mtb_carbon")).click().run()
    ok(at)
    assert not any("Setting" in df.value.columns and len(df.value) for df in at.dataframe)


# ---------------- what-if: in words ----------------

def fake(monkeypatch, *answers):
    client = FakeClient(*answers)
    monkeypatch.setattr(llm, "propose", lambda req, table, obj, client_=None: REAL_PROPOSE(req, table, obj, client))


def test_what_if_in_words_loads_settings_then_runs(folder, monkeypatch):
    fake(monkeypatch, answer(A_TO_B))
    at = start("whatif.py")
    at.text_area(key="wi_req").input("Web via the PDC, others direct, one-week builds").run()
    button(at, "Propose settings").click().run()
    ok(at)
    assert any("Claude set 8 settings" in s.value for s in at.success)
    assert widget(at.radio, "Web orders").value == "PDC"                     # the controls show the proposal
    review = next(df.value for df in at.dataframe if "Setting" in df.value.columns)
    assert "Why" in review.columns and (review["Why"] == "test").all()
    button(at, "Create and run scenario").click().run()
    ok(at)
    assert priors.diff(store.load_all(folder)["C"].priors, sc.CASE_B.priors) == []
    assert store.load_all(folder)["C"].summary == "Web via the PDC, others direct, one-week builds"


def test_example_chips_fill_the_request(folder):
    at = start("whatif.py")
    at.button(key="wi_ex_1").click().run()
    ok(at)
    assert at.text_area(key="wi_req").value == "MTB carbon now takes two weeks to build."


def test_unclear_or_unsupported_requests_change_nothing(folder, monkeypatch):
    fake(monkeypatch, answer(unsupported=["conditional shipping"]), answer(question="Which line?"))
    at = start("whatif.py")
    at.text_area(key="wi_req").input("ship from Reno when the PDC is short").run()
    button(at, "Propose settings").click().run()
    assert any("conditional shipping" in i.value for i in at.info)
    at.text_area(key="wi_req").input("make it faster").run()
    button(at, "Propose settings").click().run()
    assert any("Which line?" in i.value for i in at.info)
    assert button(at, "Create and run scenario").disabled

    def broken(*a, **k):
        raise ConnectionError("no network")
    monkeypatch.setattr(llm, "propose", broken)
    button(at, "Propose settings").click().run()
    assert any("no network" in e.value for e in at.error)


# ---------------- your scenarios: edit, delete ----------------

def test_edit_saves_over_your_scenario(folder):
    store.save(sc.Case("C", "Scenario C · mine", sc.CASE_B.priors, "mine", "B"), folder)
    at = start("scenario.py")
    at.selectbox(key="_current").set_value("C").run()
    at.button(key="sc_edit").click().run()
    ok(at)
    assert at.title[0].value == "Change your scenario"
    at.switch_page("whatif.py").run()          # the app switched pages; the test harness must be told to stay there
    widget(at.number_input, "Build · MTB · carbon").set_value(2).run()
    button(at, "Save and re-plan").click().run()
    ok(at)
    saved = store.load_all(folder)
    assert list(saved) == ["C"] and saved["C"].build_weeks["mtb-carbon"] == 2
    assert at.title[0].value == "Scenario C · mine"


def test_delete_your_scenario(folder):
    store.save(sc.Case("C", "Scenario C · mine", sc.CASE_B.priors, "mine", "B"), folder)
    at = start("scenario.py")
    at.selectbox(key="_current").set_value("C").run()
    at.button(key="sc_delete").click().run()
    ok(at)
    assert store.load_all(folder) == {} and at.title[0].value == "Scenario B · web via PDC, others direct"


# ---------------- asking about results ----------------

def test_ask_about_a_plan_and_about_differences(folder, monkeypatch):
    seen = []
    monkeypatch.setattr(llm, "explain", lambda q, facts, client=None: seen.append((q, facts)) or {"answer": "Because."})
    at = start("scenario.py")
    at.text_area(key="q_A").input("Why September?").run()
    at.button(key="ask_A").click().run()
    ok(at)
    assert any(md.value == "Because." for md in at.markdown)
    assert "SCENARIO A" in seen[-1][1] and "MTB carbon" in seen[-1][1]
    at.switch_page("compare.py").run()
    at.text_area(key="cmp_q").input("Why is B later?").run()
    at.button(key="cmp_ask").click().run()
    ok(at)
    assert "SETTINGS IN B THAT DIFFER FROM A" in seen[-1][1]


def test_compare_lists_what_differs(folder):
    at = start("compare.py")
    tables = [df.value for df in at.dataframe]
    settings = next(t for t in tables if t.index.name == "Setting")
    assert "Web orders ship from" in settings.index and set(settings.loc["Web orders ship from"]) == {"Either site", "PDC"}
    results = next(t for t in tables if t.index.name == "Measure")
    assert "(+3 wk)" in results.loc["All targets held from"].iloc[1]


def test_a_saved_scenario_that_cannot_be_planned_does_not_break_the_app(folder):
    bad = priors.apply_changes(sc.CASE_A.priors, [{"prior": "decides", "applies_to": "make", "new": "no"}])
    store.save(sc.Case("C", "Scenario C · broken", bad, "edited by hand", "A"), folder)
    at = start()
    assert any("can't be planned" in e.value for e in at.error)
    assert any(md.value.strip("*") == "Scenario A · base case" for md in at.markdown)
    at.switch_page("scenario.py").run()
    at.selectbox(key="_current").set_value("C").run()
    assert not at.exception and any("can't be planned" in e.value or "decides" in e.value for e in at.error)
    at.switch_page("compare.py").run()
    assert not at.exception


def test_example_questions_fill_the_ask_boxes(folder):
    at = start("scenario.py")
    at.button(key="qex_A_0").click().run()
    ok(at)
    assert at.text_area(key="q_A").value == "What limits this plan?"
    at.switch_page("compare.py").run()
    at.button(key="cmpex_1").click().run()
    ok(at)
    assert at.text_area(key="cmp_q").value == "Which settings explain most of the difference?"
