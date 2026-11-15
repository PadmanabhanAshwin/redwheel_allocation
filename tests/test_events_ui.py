"""Events in the planner (planner2): the words and forms that make them, the Events tab, the What-if card, and
everywhere else a scenario's events must show (Home, Compare, the Settings tab, the facts Ask reads).

Expected numbers come from the validated event runs (tests/test_events.py, docs/WORKING_NOTES.md D15-D17): E1 holds
its targets from 4 Oct 2027 (+4 weeks on A), with 290 weeks below target (+12) and 94,429 bikes built; E2 from 13 Sep
2027 (+1 week) with 191 more RW-4418 built."""
import datetime as dt
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from redwheel import changes as ch, llm, scenarios as sc, store
from redwheel.changes import Change
from test_planner2 import button, folder, metric, ok, start, widget      # noqa: F401  (folder is a fixture)

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "app")]
E1, E2 = sc.CASE_E1.changes[0], sc.CASE_E2.changes[0]
D = dt.date


@pytest.fixture(scope="module")
def ev():
    from planner2 import events
    return events


@pytest.fixture(scope="module")
def ui():
    import ui as u
    return u


@pytest.fixture(scope="module")
def views(ui):
    return {k: ui.view_of(sc.run_case(c)) for k, c in (("A", sc.CASE_A), ("E1", sc.CASE_E1), ("E2", sc.CASE_E2))}


def badges(at):
    return [m.value for m in at.markdown if "-badge[" in m.value]


def tables(at):
    return [df.value for df in at.dataframe]


def event_lines(at):
    """The events the review panel lists as added or removed (it lists them, not tabulates them: the panel is narrow)."""
    return [m.value for m in at.markdown if m.value.startswith("- **Event ")]


def plain(df):
    """A table's cells without the figure spaces that right-align them."""
    return df.apply(lambda col: col.str.replace("\u2007", "", regex=False))


def ev_title(c):
    from planner2 import events
    return events.title(c)


# ---------------- plan weeks and dates ----------------

def test_a_date_picks_the_plan_week_that_contains_it(ev):
    assert ev.week_start(1) == D(2026, 9, 7) and ev.week_start(26) == D(2027, 3, 1) and ev.week_start(121) == D(2028, 12, 25)
    for t in (1, 18, 26, 57, 121, 156):
        start_ = ev.week_start(t)
        assert [ev.week_of(start_ + dt.timedelta(days=i)) for i in range(7)] == [t] * 7      # Monday to Sunday
        assert ev.week_of(start_ - dt.timedelta(days=1)) == t - 1


# ---------------- the forms make the events we validated ----------------

def test_the_forms_make_the_built_in_events(ev, ui):
    assert ev.line_down("mtb-carbon", D(2027, 3, 1), 3) == replace(E1, reason="")
    mine = ev.demand_change("RW-4418", "DEALERS", 30, D(2027, 1, 4), 13)          # E2 says `channel`, the form `location`
    a, ra = ch.apply(ui.obj, [mine])
    b, rb = ch.apply(ui.obj, [E2])
    assert a.arrivals.equals(b.arrivals) and a.outlook.equals(b.outlook)           # the same numbers, edited the same way
    assert ra[["resources", "cells", "before", "after"]].equals(rb[["resources", "cells", "before", "after"]])
    c = ev.stock_correction("RW-9324", "RENO", -200)
    assert c == Change("opening", {"kind": "inventory", "item": "RW-9324", "location": "RENO"}, "add", -200, None, None, "")


def test_a_line_slowed_is_a_scale_and_a_line_down_is_a_set(ev):
    assert (ev.line_down("road-base", D(2026, 12, 28), 3, 50).op, ev.line_down("road-base", D(2026, 12, 28), 3, 50).value) == ("scale", 0.5)
    assert (ev.line_down("road-base", D(2026, 12, 28), 3).op, ev.line_down("road-base", D(2026, 12, 28), 3).value) == ("set", 0)
    assert ev.demand_change("all", None, -20, D(2027, 6, 7), 1).select == {"kind": "order"}
    assert ev.demand_change("mtb-carbon", "WEB", 10, D(2027, 6, 7), 4).select == {"kind": "order", "line_id": "mtb-carbon", "location": "WEB"}


# ---------------- in words ----------------

def test_events_read_in_plain_words(ev):
    assert ev.title(E1) == "MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027 · set to 0"
    assert ev.title(E2) == "Dealer orders for RW-4418 · weeks of 4 Jan to 29 Mar 2027 · +30%"          # the `channel` spelling
    assert ev.title(ev.demand_change("RW-4418", "DEALERS", 30, D(2027, 1, 4), 13)) == ev.title(E2)     # the `location` spelling
    assert ev.title(ev.stock_correction("RW-9324", "RENO", -200)) == "Stock of RW-9324 at Reno · at the snapshot · -200"
    assert ev.title(ev.line_down("road-base", D(2026, 12, 28), 3, 50)) == \
        "Road base line capacity · weeks of 28 Dec 2026 to 11 Jan 2027 · -50%"                         # across a year end
    assert ev.title(ev.demand_change("all", None, -20, D(2027, 6, 7), 1)) == "All orders · week of 7 Jun 2027 · -20%"
    assert ev.title(ev.demand_change("mtb-carbon", "WEB", 10, D(2027, 6, 7), 4)) == \
        "Web orders for MTB carbon SKUs · weeks of 7 Jun to 28 Jun 2027 · +10%"
    assert [ev.effect(Change("arrival", {"kind": "order"}, "scale", v, 1, 1)) for v in (1.3, 0.5, 1.125, 2)] == \
        ["+30%", "-50%", "+12.5%", "+100%"]
    assert ev.name_hint(E1) == "MTB carbon line down from 1 Mar 2027"
    assert ev.name_hint(E2) == "Dealer orders for RW-4418 +30%"


def test_events_know_which_lines_they_touch(ev, ui):
    assert ev.lines_of(E1, ui.obj) == ["mtb-carbon"] and ev.lines_of(E2, ui.obj) == ["mtb-carbon"]
    assert ev.lines_of(ev.stock_correction("RW-9324", "CMH", 10), ui.obj) == ["mtb-base"]
    assert ev.lines_of(ev.demand_change("all", None, 5, D(2027, 1, 4), 2), ui.obj) == list(ui.LINES)
    assert ev.lines_of(ev.demand_change("road-base", None, 5, D(2027, 1, 4), 2), ui.obj) == ["road-base"]


def test_a_problem_is_said_in_one_plain_sentence(ev, ui):
    assert ev.problem(ui.obj, [E1]) is None
    nothing = "it would change nothing (the numbers it selects already have that value)"
    assert ev.problem(ui.obj, [ev.line_down("mtb-carbon", D(2027, 3, 1), 3, 100)]) == nothing
    assert ev.problem(ui.obj, [ev.line_down("mtb-carbon", D(2028, 12, 18), 3)]) == \
        "weeks after the plan (122–156) can change only on order resources"
    assert ev.problem(ui.obj, [ev.stock_correction("RW-9324", "RENO", -5000)]).startswith("1 number(s) would go below zero")
    # the list is checked as a whole, in order: setting a line to zero twice changes nothing the second time
    assert ev.problem(ui.obj, [E1, E1]) == nothing


def test_the_events_table_has_the_numbers_changed(ev, ui):
    changes = [E1, E2, ev.stock_correction("RW-9324", "RENO", -200)]
    t = ev.table(changes, ch.apply(ui.obj, changes)[1])
    assert t["Change"].tolist() == ["set to 0", "+30%", "-200"] and t["Numbers changed"].tolist() == [3, 13, 1]
    assert t["From"].tolist() == ["1,125 bikes", "636 bikes", "1,250 bikes"]
    assert t["To"].tolist() == ["0 bikes", "827 bikes", "1,050 bikes"]
    assert t["Why"].tolist()[:2] == [E1.reason, E2.reason]


# ---------------- what differs between two lists of events ----------------

def test_differences_between_lists_of_events(ev):
    c = ev.stock_correction("RW-9324", "RENO", -200)
    assert ev.same([E1], [replace(E1, reason="another reason")])              # the reason is not an edit
    assert ev.same([E2], [ev.demand_change("RW-4418", "DEALERS", 30, D(2027, 1, 4), 13)])   # the same resources, spelled differently
    assert ev.same([], [])
    d = ev.differences([E1, E2], [E2, c])
    assert d["Setting"].tolist() == ["Event · MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027",
                                     "Event · Stock of RW-9324 at Reno · at the snapshot"]
    assert d[["From", "To"]].values.tolist() == [["set to 0", "removed"], ["none", "-200"]]
    assert not ev.same([E1, c], [c, E1])                                       # a later change sees an earlier one: order counts
    assert not ev.same([E1], [ev.line_down("mtb-carbon", D(2027, 3, 8), 3)])
    assert ev.moves([E1, E2], [E2, c]) == [("removed", E1), ("added", c)]
    assert ev.moves([E1], [E1]) == [] and ev.moves([], [E1, E2]) == [("added", E1), ("added", E2)]


# ---------------- the Events tab: the charts ----------------

def test_the_window_covers_every_week_the_plans_differ(views):
    from planner2 import event_tab as et
    VA, VE = views["A"], views["E1"]
    spans = et.shades(VE, "mtb-carbon")
    assert spans == [(26, 28)] and et.shades(VE, "road-base") == []              # the event is on one line only
    lo, hi = et.window(VE, VA, "mtb-carbon", spans)
    assert lo == 26 - et.MARGIN and hi >= 57 + et.MARGIN                          # the line's builds still differ in week 57
    # independent check: outside the window the plans do not differ (the line's builds, its lowest weeks of supply)
    cols = [k for k in VE["R"]["wos"].index if k[0] in ("RW-4418", "RW-6416", "RW-9304")]
    low = lambda V: V["R"]["wos"].loc[cols, 1:121].min().to_numpy()
    built = lambda V: V["built"].loc[["RW-4418", "RW-6416", "RW-9304"]].sum().to_numpy()
    differs = np.flatnonzero((np.abs(built(VE) - built(VA)) >= 1) | (np.abs(low(VE) - low(VA)) >= 0.1)) + 1
    assert differs.min() >= lo + et.MARGIN and differs.max() <= hi - et.MARGIN
    assert et.window(VE, None, "mtb-carbon", spans) == (lo, 28 + et.MARGIN)       # with nothing to compare: the event weeks only


def test_the_charts_show_the_line_down_and_the_event_weeks(views):
    from planner2 import event_tab as et
    VA, VE = views["A"], views["E1"]
    lo, hi = 18, 65
    fig = et.builds_figure(VE, VA, "mtb-carbon", lo, hi, [(26, 28)])
    tr = {t.name: t for t in fig.data}
    at = lambda name, week: float(tr[name].y[week - lo])
    assert [at("capacity", w) for w in (25, 26, 27, 28, 29)] == [375, 0, 0, 0, 375]
    assert [at("built", w) for w in (25, 26, 27, 28, 29)] == [375, 0, 0, 0, 375]
    assert [at("capacity · A", w) for w in (26, 27, 28)] == [375, 375, 375]        # the compared scenario's capacity is drawn too
    assert [at("built · A", w) for w in (26, 27, 28)] == [375, 375, 375]
    assert at("built", 54) > at("built · A", 54)                                   # the lost bikes are made up from week 53
    cap = VE["R"]["obj"].arrivals.loc["capacity||RENO/mtb-carbon"]                 # where builds and capacity differ (A leaves
    for w in (60, 64):                                                             # spare capacity after the catch-up) they are
        assert at("capacity", w) == cap.loc[w] > at("built", w) > 0                #   two different lines
    assert len(fig.layout.shapes) == 1
    assert (pd.Timestamp(fig.layout.shapes[0].x0), pd.Timestamp(fig.layout.shapes[0].x1)) == \
        (pd.Timestamp("2027-03-01"), pd.Timestamp("2027-03-22"))                    # three weeks, Monday to the next Monday
    # the same line in A has no capacity series of its own to draw: capacity did not change
    figA = et.builds_figure(VA, VE, "road-base", 1, 121, [])
    assert not figA.layout.shapes and "capacity · E1" not in {t.name for t in figA.data}


def test_the_weeks_of_supply_chart_follows_the_lowest_sku(views):
    from planner2 import event_tab as et
    VA, VE = views["A"], views["E1"]
    lo = 18
    fig = et.supply_figure(VE, VA, "mtb-carbon", lo, 65, [(26, 28)])
    tr = {t.name: t for t in fig.data}
    R = VE["R"]
    mtb = [k for k in R["wos"].index if k[0] in ("RW-4418", "RW-6416", "RW-9304")]
    for week in (25, 28, 40, 56):
        assert float(tr["lowest weeks of supply"].y[week - lo]) == pytest.approx(min(R["wos"].at[k, week] for k in mtb))
        assert float(tr["target"].y[week - lo]) == 15.0
    assert float(tr["lowest · A"].y[28 - lo]) == pytest.approx(min(VA["R"]["wos"].at[k, 28] for k in mtb))
    assert tr["lowest weeks of supply"].y[28 - lo] < 3 < tr["lowest · A"].y[28 - lo]      # the dip: about 2 weeks against 5.6


# ---------------- the pages ----------------

def test_home_lists_the_events_with_a_badge_and_their_dates(folder):
    at = start()
    ok(at)
    assert badges(at).count(":violet-badge[:material/bolt: 1 event]") == 2             # E1 and E2, not A or B
    cards = [m.value for m in at.markdown if "rw-nums" in m.value]
    assert "4 Oct 2027" in cards[2] and "13 Sep 2027" in cards[3]                       # E1, E2 (after A and B)
    assert not any("Same settings as" in b for b in badges(at))                         # E1, E2 are A's settings plus an event


def test_the_events_tab_of_an_event_scenario(folder):
    at = start("scenario.py")
    at.selectbox(key="_current").set_value("E1").run()
    ok(at)
    assert ":orange-badge[:material/bolt: Events: 1]" in badges(at)
    t = next(t for t in tables(at) if "Numbers changed" in t.columns)
    assert t.iloc[0].to_dict() == {"Event": "MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027", "Change": "set to 0",
                                   "Numbers changed": 3, "From": "1,125 bikes", "To": "0 bikes", "Why": E1.reason}
    eff = plain(next(t for t in tables(at) if "Holds targets from" in t.columns))
    assert eff.loc["MTB carbon", ["Built vs A", "Date vs A"]].tolist() == ["same", "+4 wk"]
    assert (eff.drop(index="MTB carbon")[["Built vs A", "Date vs A"]] == "same").all().all()      # the other lines do not move
    assert metric(at, "All targets held from") == "4 Oct 2027"


def test_the_events_tab_of_the_demand_event(folder):
    at = start("scenario.py")
    at.selectbox(key="_current").set_value("E2").run()
    ok(at)
    t = next(t for t in tables(at) if "Numbers changed" in t.columns)
    assert t.iloc[0][["Event", "Change", "Numbers changed", "From", "To"]].tolist() == \
        ["Dealer orders for RW-4418 · weeks of 4 Jan to 29 Mar 2027", "+30%", 13, "636 bikes", "827 bikes"]
    eff = plain(next(t for t in tables(at) if "Holds targets from" in t.columns))
    assert eff.loc["MTB carbon", ["Built vs A", "Date vs A"]].tolist() == ["+191", "+1 wk"]


def test_a_scenario_without_events_says_so_and_offers_one(folder):
    at = start("scenario.py")
    ok(at)
    assert ":gray-badge[Events: none]" in badges(at)
    assert any("no events" in i.value for i in at.info)
    button(at, "Add an event").click().run()
    ok(at)
    # the button switched pages inside the run: the What-if page is what rendered, with a draft from A. (The test must
    # not go on to `at.switch_page`: its tree still holds the SKU box from the page it left, whose state the switch purged.)
    assert at.title[0].value == "What-if" and at.session_state.draft["base"] == "A"
    assert any("Add an event" in s.label for s in at.selectbox if s.key == "ev_type")


def test_the_settings_tab_lists_events_that_differ(folder):
    at = start("scenario.py")
    at.selectbox(key="_current").set_value("E1").run()
    ok(at)
    diff = next(t for t in tables(at) if list(t.columns) == ["Setting", "From", "To", "Why"])       # Why: E1 has a reason
    assert diff.values.tolist() == [["Event · MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027", "none", "set to 0",
                                     E1.reason]]


def test_compare_lists_events_among_the_settings_that_differ(folder):
    at = start("compare.py")
    ok(at)
    side = next(t for t in tables(at) if t.index.name == "Setting")
    assert side.loc["Events"].tolist() == ["none", "none", ev_title(E1), ev_title(E2)]          # A, B, E1, E2


def test_the_facts_for_ask_list_events_and_what_differs(views, ev):
    from planner2 import facts
    text = facts.facts([("A", sc.CASE_A, views["A"]), ("E1", sc.CASE_E1, views["E1"])])
    assert "Events: none (the data is as given)." in text
    assert ("Events (edits to the data this scenario plans from): MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027 "
            "· set to 0: 3 numbers changed, total 1,125 -> 0 bikes (reason: " + E1.reason + ").") in text
    assert "EVENTS IN E1 THAT DIFFER FROM A: MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027: none -> set to 0." in text
    assert "SETTINGS IN E1 THAT DIFFER FROM A: none." in text                              # same settings: only the event differs
    assert "except where a scenario lists events" in text                                  # the facts no longer say "only the settings differ"
    assert "(no capacity at all in 3 of those weeks)" in text


def test_ask_sends_the_events_to_the_model(folder, monkeypatch):
    seen = []
    monkeypatch.setattr(llm, "explain", lambda q, facts, client=None: seen.append(facts) or {"answer": "Because."})
    at = start("scenario.py")
    at.selectbox(key="_current").set_value("E1").run()
    at.text_area(key="q_E1").input("Why is MTB carbon later?").run()
    at.button(key="ask_E1").click().run()
    ok(at)
    assert "Events (edits to the data this scenario plans from)" in seen[-1] and "set to 0" in seen[-1]


# ---------------- the What-if card ----------------

def pick_type(at, label):
    at.selectbox(key="ev_type").set_value(label).run()
    return ok(at)


def captions(at):
    return [c.value for c in at.caption]


def test_the_default_event_form_makes_event_1_and_runs_it(folder):
    at = start("whatif.py")
    assert button(at, "Create and run scenario").disabled                                 # nothing to run yet
    button(at, "Add event").click().run()
    ok(at)
    assert event_lines(at) == ["- **Event added:** MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027 · set to 0"]
    assert not any("Setting" in t.columns for t in tables(at))                            # no settings changed: no settings table
    assert any("Passes every check" in s.value for s in at.success)
    assert (metric(at, "Targets held from"), metric(at, "Weeks below target")) == ("4 Oct 2027", "290")   # the preview
    assert store.load_all(folder) == {}                                                   # nothing saved yet
    assert widget(at.text_input, "Name").value == "MTB carbon line down from 1 Mar 2027"
    button(at, "Create and run scenario").click().run()
    ok(at)
    assert at.title[0].value == "Scenario C · MTB carbon line down from 1 Mar 2027"
    assert metric(at, "All targets held from") == "4 Oct 2027"
    assert ":orange-badge[:material/bolt: Events: 1]" in badges(at)
    saved = store.load_all(folder)["C"]
    assert saved.changes == (replace(E1, reason=""),) and saved.parent == "A"
    # the plan is exactly event 1's
    R, R1 = sc.run_case(saved), sc.run_case(sc.CASE_E1)
    assert R["builds"].equals(R1["builds"]) and (R["X"] == R1["X"]).all().all()


def test_an_event_that_breaks_a_rule_cannot_be_added(folder):
    at = start("whatif.py")
    widget(at.number_input, "Capacity left (%)").set_value(100).run()
    assert button(at, "Add event").disabled
    assert any("Can't add this: it would change nothing (the numbers it selects already have that value)." in c for c in captions(at))
    widget(at.number_input, "Capacity left (%)").set_value(0).run()
    assert not button(at, "Add event").disabled
    at.date_input(key="ev_line_from").set_value(D(2028, 12, 18)).run()                   # weeks 120-122: past the plan
    assert button(at, "Add event").disabled
    assert any("weeks after the plan (122–156) can change only on order resources" in c for c in captions(at))
    ok(at)


def test_the_demand_form_defaults_to_event_2(folder):
    at = start("whatif.py")
    pick_type(at, "Demand up or down")
    button(at, "Add event").click().run()
    ok(at)
    assert event_lines(at) == ["- **Event added:** Dealer orders for RW-4418 · weeks of 4 Jan to 29 Mar 2027 · +30%"]
    assert metric(at, "Targets held from") == "13 Sep 2027"
    button(at, "Create and run scenario").click().run()
    saved = store.load_all(folder)["C"]
    R, R2 = sc.run_case(saved), sc.run_case(sc.CASE_E2)
    assert R["builds"].equals(R2["builds"])


def test_the_stock_form_shows_what_the_books_say(folder):
    at = start("whatif.py")
    pick_type(at, "Stock count correction")
    assert any("On the books at the snapshot: 1,250 bikes; after the correction: 1,050." in c for c in captions(at))
    widget(at.number_input, "Correction (bikes)").set_value(-5000).run()
    assert button(at, "Add event").disabled and any("Can't add this: 1 number(s) would go below zero" in c for c in captions(at))
    widget(at.number_input, "Correction (bikes)").set_value(-200).run()
    button(at, "Add event").click().run()
    ok(at)
    assert metric(at, "Targets held from") == "6 Sep 2027"                                # a stock correction that moves no date


def test_events_can_be_removed_before_running(folder):
    at = start("whatif.py")
    button(at, "Add event").click().run()
    assert not button(at, "Create and run scenario").disabled
    at.button(key="ev_rm_0").click().run()
    ok(at)
    assert button(at, "Create and run scenario").disabled
    assert any("No events" in c for c in captions(at))


def test_two_events_are_checked_together_and_run_in_order(folder):
    at = start("whatif.py")
    button(at, "Add event").click().run()                                                 # line down, weeks 26-28
    assert button(at, "Add event").disabled                                               # the same again changes nothing
    pick_type(at, "Demand up or down")
    button(at, "Add event").click().run()
    ok(at)
    assert event_lines(at) == [f"- **Event added:** {ev_title(E1)}", f"- **Event added:** {ev_title(E2)}"]
    button(at, "Create and run scenario").click().run()
    ok(at)
    saved = store.load_all(folder)["C"]
    assert [ev_title(c) for c in saved.changes] == [ev_title(E1), ev_title(E2)]
    chk = sc.checks(sc.run_case(saved))
    assert chk["pass"].all()


def test_a_what_if_from_an_event_scenario_starts_with_its_events(folder):
    at = start("scenario.py")
    at.selectbox(key="_current").set_value("E1").run()
    at.button(key="sc_whatif").click().run()
    at.switch_page("whatif.py").run()
    ok(at)
    assert any("MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027 · **set to 0**" in m.value for m in at.markdown)   # the card lists it
    assert button(at, "Create and run scenario").disabled                                 # same as E1: nothing differs yet
    at.button(key="ev_rm_0").click().run()
    assert event_lines(at) == ["- **Event removed:** MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027 · set to 0"]
    assert metric(at, "Targets held from") == "6 Sep 2027"                                # without the event: A's date
    button(at, "Create and run scenario").click().run()
    ok(at)
    assert store.load_all(folder)["C"].changes == ()


def test_editing_your_scenario_can_add_an_event(folder):
    store.save(replace(sc.CASE_A, key="C", name="Scenario C · mine", parent="A", summary="mine"), folder)
    at = start("scenario.py")
    at.selectbox(key="_current").set_value("C").run()
    at.button(key="sc_edit").click().run()
    at.switch_page("whatif.py").run()
    ok(at)
    button(at, "Add event").click().run()
    button(at, "Save and re-plan").click().run()
    ok(at)
    saved = store.load_all(folder)["C"]
    assert saved.name == "Scenario C · mine" and saved.summary == "mine"                  # name and description kept
    assert saved.changes == (replace(E1, reason=""),)
    assert metric(at, "All targets held from") == "4 Oct 2027"


def test_the_reason_is_saved_with_the_event(folder):
    at = start("whatif.py")
    at.text_input(key="ev_note").input("planned maintenance").run()
    button(at, "Add event").click().run()
    ok(at)
    assert at.text_input(key="ev_note").value == ""                                       # cleared for the next event
    button(at, "Create and run scenario").click().run()
    assert store.load_all(folder)["C"].changes[0].reason == "planned maintenance"


def test_a_user_scenario_equal_to_an_event_is_flagged_as_the_same_settings(folder):
    from planner2 import events
    store.save(replace(sc.CASE_A, key="C", name="Scenario C · dealers up", parent="A", changes=(
        events.demand_change("RW-4418", "DEALERS", 30, D(2027, 1, 4), 13, "typed in the form"),)), folder)
    at = start()
    ok(at)
    assert ":orange-badge[:material/content_copy: Same settings as E2]" in badges(at)    # same edits as E2, spelled differently


def test_the_assumptions_no_longer_say_only_settings_differ(folder):
    at = start()
    text = " ".join(m.value for m in at.markdown)
    assert "are the same in every scenario; only" not in text and "except where a scenario has events" in text


# ---------------- what the Events table says, checked against the objects themselves ----------------

def test_random_events_change_exactly_the_numbers_the_events_table_says(ev, ui):
    """Fifteen random events from the form builders. For each, the new object is compared with the old one cell by cell
    (not through `changes.selected`): the resources are named from the id convention, and the new values come from exact
    integer arithmetic (halves up), not floats. The Events table's numbers changed, before and after must agree."""
    import random
    from redwheel import rtn
    rng = random.Random(7)
    obj, lines, skus = ui.obj, list(ui.LINES), list(ui.ORDER)
    line_of = ui.SKU["line_id"].to_dict()
    A0 = rtn.arrivals_all(obj)
    done, seen = 0, {"line": 0, "demand": 0, "stock": 0}
    while done < 15:
        kind = ["line", "demand", "stock"][done % 3]                                       # five of each; random details
        if kind == "line":
            ln, n, pct = rng.choice(lines), rng.randint(1, 6), rng.choice([0, 0, 25, 50, 90])
            c = ev.line_down(ln, ev.week_start(rng.randint(1, 120)), n, pct)
            rows, mult = [f"capacity||RENO/{ln}"], pct                                     # new = old * pct / 100
        elif kind == "demand":
            scope, chan = rng.choice(["all"] + lines + skus), rng.choice([None, "WEB", "DEALERS", "COMMERCIAL"])
            pct = rng.choice([-50, -10, 15, 30, 100])
            c = ev.demand_change(scope, chan, pct, ev.week_start(rng.randint(1, 150)), rng.randint(1, 8))
            chosen = skus if scope == "all" else [s for s in skus if line_of[s] == scope] if scope in lines else [scope]
            rows, mult = [f"order|{s}|{k}" for s in chosen for k in ([chan] if chan else ["WEB", "DEALERS", "COMMERCIAL"])], 100 + pct
        else:
            sku, site, bikes = rng.choice(skus), rng.choice(["RENO", "CMH"]), rng.choice([-50, 30, 400])
            c = ev.stock_correction(sku, site, bikes)
            rid = f"inventory|{sku}|{site}"
            if obj.opening[rid] + bikes < 0:
                continue
            new, rep = ch.apply(obj, [c])
            assert rep.iloc[0][["resources", "cells", "before", "after"]].tolist() == [1, 1, obj.opening[rid], obj.opening[rid] + bikes]
            assert (new.opening.drop(rid) == obj.opening.drop(rid)).all() and new.opening[rid] == obj.opening[rid] + bikes
            done += 1
            seen["stock"] += 1
            continue
        if ev.problem(obj, [c]):                                                           # e.g. nothing to change
            continue
        new, rep = ch.apply(obj, [c])
        A1, weeks = rtn.arrivals_all(new), list(range(c.from_t, c.to_t + 1))
        old = A0.loc[rows, weeks].astype(int)
        expected = (old * mult * 2 + 100) // 200                                           # round half up, exactly
        assert (A1.loc[rows, weeks] == expected).all().all()
        assert (A1.drop(index=rows) == A0.drop(index=rows)).all().all()                    # no other resource moved
        rest = [t for t in A0.columns if t not in weeks]
        assert (A1.loc[rows, rest] == A0.loc[rows, rest]).all().all()                      # no other week moved
        row = ev.table([c], rep).iloc[0]
        assert (row["Numbers changed"], row["From"], row["To"]) == (
            int((old != expected).to_numpy().sum()), f"{int(old.to_numpy().sum()):,} bikes", f"{int(expected.to_numpy().sum()):,} bikes")
        done += 1
        seen[kind] += 1
    assert seen == {"line": 5, "demand": 5, "stock": 5}
