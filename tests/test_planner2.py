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
    built_in = {**sc.CASES, **sc.EVENTS}                       # A, B and the two events on A
    for k in built_in:
        at.selectbox(key="_current").set_value(k).run()
        ok(at)
        assert at.title[0].value == built_in[k].name
        assert [t.label for t in at.tabs] == ["Summary", "Builds", "Inventory", "SKU detail", "Events", "Settings"]
    at.selectbox(key="_current").set_value("B").run()
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


# ---------------- scenarios that carry changes ----------------

def test_a_scenario_with_changes_runs_with_them_and_a_what_if_keeps_them(folder):
    """Same settings as A, MTB carbon line down three weeks. The planner must run it with the change (not reuse A's
    cached result); a what-if started from it changes settings and keeps the change, preview included."""
    from dataclasses import replace
    store.save(replace(sc.CASE_E1, key="C", name="Scenario C · line down"), folder)
    at = start("scenario.py")
    assert metric(at, "All targets held from") == "6 Sep 2027"                      # A
    at.selectbox(key="_current").set_value("C").run()
    ok(at)
    assert metric(at, "All targets held from") == "4 Oct 2027"
    at.button(key="sc_whatif").click().run()
    at.switch_page("whatif.py").run()
    ok(at)
    widget(at.number_input, "Build · Road · base").set_value(1).run()
    assert metric(at, "Targets held from") == "4 Oct 2027"                          # preview: line still down
    button(at, "Create and run scenario").click().run()
    ok(at)
    saved = store.load_all(folder)
    assert saved["D"].changes == sc.CASE_E1.changes and saved["D"].build_weeks["road-base"] == 1


def test_the_plan_run_is_what_is_cached(folder):
    """The cache must sit on the run (keyed on settings and changes), never on a helper keyed by scenario letter: a
    letter can mean another scenario later (delete C, create a new C), and a stale result would then be shown."""
    start()                                                       # imports the planner's modules
    import planner2.state as p2s
    import planner.state as p1s
    assert hasattr(p2s._run, "clear") and not hasattr(p2s.changes_json, "clear")
    assert hasattr(p1s._run, "clear")


# ---------------- what the pages show for a scenario with changes ----------------

@pytest.fixture(scope="module")
def views():
    """Views of A, E1 (line down) and a stock correction, as the planner draws them."""
    import sys
    sys.path[:0] = [str(ROOT), str(ROOT / "app")]
    from dataclasses import replace
    from redwheel.changes import Change
    import ui
    S = replace(sc.CASE_A, key="S", changes=(
        Change("opening", {"kind": "inventory", "item": "RW-9324", "location": "RENO"}, "add", -200),))
    return {k: ui.view_of(sc.run_case(c)) for k, c in (("A", sc.CASE_A), ("E1", sc.CASE_E1), ("S", S))}


def test_capacity_shown_is_the_scenarios_own(views):
    """The line is down in three of March 2027's five weeks: 750 of capacity, not 1,875, and all of it used."""
    import ui
    from planner2 import charts
    grid = {k: ui.plan_grid(views[k], ui.SKUS_BY_LINE["mtb-carbon"], "Month")[0] for k in ("A", "E1")}
    assert grid["A"].at["Capacity (used)", "Mar 2027"] == "1,875 (100%)"
    assert grid["E1"].at["Capacity (used)", "Mar 2027"] == "750 (100%)"
    assert list(charts.capacity(views["E1"], "mtb-carbon")[24:29]) == [375, 0, 0, 0, 375]
    _, use, _ = charts.next_weeks(views["E1"], 30)
    assert use.at["MTB carbon", "1 Mar"] == "0 / 0"


def test_the_plan_reading_says_when_a_line_had_no_capacity(views):
    from planner2 import charts
    line = lambda k: next(t for t in charts.reading_text(views[k]) if t.startswith("**MTB carbon"))
    assert line("A").startswith("**MTB carbon** uses all its capacity from the start to w/c 30 Aug 2027;")
    assert line("E1").startswith("**MTB carbon** uses all its capacity from the start to w/c 27 Sep 2027 "
                                 "(it has none in 3 of those weeks); its SKUs hold target from 4 Oct 2027.")


def test_sku_facts_show_the_scenarios_stock(views):
    from planner2 import charts
    stock = lambda k: charts.sku_facts(views[k], "RW-9324").set_index("")["Value"]["In stock at the snapshot"]
    assert stock("A") == "1,900  (Reno 1,250, PDC 650)" and stock("S") == "1,700  (Reno 1,050, PDC 650)"


def test_a_scenario_is_flagged_as_a_duplicate_only_if_its_changes_match_too(folder):
    from dataclasses import replace
    from redwheel.changes import Change
    other = Change("arrival", {"kind": "capacity", "location": "RENO/road-base"}, "set", 0, 10, 11)   # in no other scenario
    store.save(replace(sc.CASE_A, key="C", name="Scenario C · road line down", changes=(other,)), folder)  # A's settings + a change
    store.save(replace(sc.CASE_A, key="D", name="Scenario D · copy of A", parent="A"), folder)             # a true copy of A
    store.save(replace(sc.CASE_E1, key="F", name="Scenario F · copy of E1"), folder)                       # a true copy of E1
    at = start()
    ok(at)
    duplicate_badges = [m.value for m in at.markdown if "Same settings as" in m.value]   # a badge is markdown here
    assert duplicate_badges == [":orange-badge[:material/content_copy: Same settings as A]",         # D, not C
                                ":orange-badge[:material/content_copy: Same settings as E1]"]        # F
