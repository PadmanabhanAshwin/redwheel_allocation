"""The one list of tunables (redwheel/tunables.py): each form makes exactly the change or settings it says; the
forms rebuild the built-in scenarios (E1, E2, E3 from data tunables, B from rules tunables); checks say why in words;
every data tunable runs through the solver with every plan check passing; differences and reports read right."""
import datetime as dt
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from redwheel import changes as ch, priors, rtn, scenarios as sc, tunables as tu
from redwheel.changes import Change

D = dt.date
E1, E2, E3 = sc.CASE_E1.changes[0], sc.CASE_E2.changes[0], sc.CASE_E3.changes[0]
STOCK = Change("opening", {"kind": "inventory", "item": "RW-9324", "location": "RENO"}, "add", -200, None, None, "")


@pytest.fixture(scope="module")
def A():
    return sc.run_case(sc.CASE_A)


def by_sku(R):
    return R["builds"].set_axis(R["builds"].index.str.split("|").str[1])


# ---------------- the list ----------------

def test_the_list_has_every_tunable_once_with_where_it_sits():
    t = tu.table()
    assert t["key"].tolist() == ["stock", "line_capacity", "demand", "extra_order", "build_limit", "transfer_limit",
                                 "build_time", "transfer_time", "ship_from", "plan_transfers", "target"]
    assert t["Tunable"].is_unique and t["key"].is_unique
    assert dict(zip(t["key"], t["In the model"])) == {
        "stock": "opening", "line_capacity": "arrival", "demand": "arrival", "extra_order": "arrival",
        "build_limit": "run limit", "transfer_limit": "run limit", "build_time": "delay", "transfer_time": "delay",
        "ship_from": "routing", "plan_transfers": "decides", "target": "target"}
    assert set(t.loc[t["Changes"] == "data", "key"]) == {"stock", "line_capacity", "demand", "extra_order",
                                                          "build_limit", "transfer_limit"}
    assert dict(zip(t["key"], t["Example"]))["line_capacity"] == "E1" and dict(zip(t["key"], t["Example"]))["build_limit"] == "E3"


@pytest.mark.parametrize("key", list(tu.TUNABLES))
def test_every_form_has_valid_defaults_and_makes_one_kind_of_edit(key):
    e = tu.make(key)
    t = tu.TUNABLES[key]
    assert set(e.values) == {f.key for f in t.fields}
    assert (e.change is not None) == (t.changes == "data") and bool(e.settings) == (t.changes == "rules")
    if e.change is not None:
        assert tu.tunable_of(e.change) == key                           # the change is recognised as this tunable


# ---------------- the forms make exactly the built-in events ----------------

def test_the_default_forms_are_the_built_in_events():
    assert tu.make("line_capacity").change == replace(E1, reason="")
    assert tu.make("build_limit").change == replace(E3, reason="")
    assert tu.make("stock").change == STOCK
    mine = tu.make("demand").change                               # E2 selects by `channel`, the form by `location`
    obj = tu._base()
    a, ra = ch.apply(obj, [mine])
    b, rb = ch.apply(obj, [E2])
    assert a.arrivals.equals(b.arrivals) and a.outlook.equals(b.outlook)
    assert ra[["resources", "cells", "before", "after"]].equals(rb[["resources", "cells", "before", "after"]])
    assert tu.same_changes([mine], [E2])


def test_the_rules_forms_rebuild_scenario_b_from_a():
    edits = [tu.make("ship_from", channel="WEB", site="PDC"), tu.make("ship_from", channel="DEALERS", site="Reno"),
             tu.make("ship_from", channel="COMMERCIAL", site="Reno"), tu.make("plan_transfers", decide="yes")] + \
            [tu.make("build_time", line=ln, weeks=1) for ln in ("road-base", "road-carbon", "mtb-base", "mtb-carbon")]
    assert tu.check(sc.CASE_A, edits) == []
    B = tu.apply(sc.CASE_A, edits, key="B2")
    assert priors.diff(B.priors, sc.CASE_B.priors) == [] and B.changes == () and B.key == "B2"
    # half of it is not a valid scenario: transfers decided while Reno and the PDC serve the same orders
    assert any("serve the same orders" in p for p in tu.check(sc.CASE_A, edits[3:4]))


def test_a_target_step_and_a_target_from_the_start():
    e = tu.make("target", group="mtb_carbon", weeks=18, **{"from": D(2027, 9, 8)})          # a Wednesday
    assert e.settings == ({"prior": "target_weeks", "applies_to": "mtb_carbon", "from_date": "2027-09-06", "new": "18"},)
    t = priors.normalise(tu.apply(sc.CASE_A, [e]).priors)
    rows = t[(t["prior"] == "target_weeks") & (t["applies_to"] == "mtb_carbon")]
    assert rows[["from_date", "value"]].values.tolist() == [["2026-09-07", "15"], ["2027-09-06", "18"]]
    start = tu.make("target", group="road", weeks=9, **{"from": D(2026, 9, 7)})              # replaces the start row
    t = priors.normalise(tu.apply(sc.CASE_A, [start]).priors)
    assert t[(t["prior"] == "target_weeks") & (t["applies_to"] == "road")][["from_date", "value"]].values.tolist() == \
        [["2026-09-07", "9"], ["2028-01-03", "10"]]


def test_each_data_form_selects_what_it_says():
    obj = tu._base()
    ids = lambda e: ch.selected(obj, e.change.select)[0]
    assert sorted(ids(tu.make("demand", skus="mtb-carbon", channel="all"))) == sorted(
        f"order|{s}|{c}" for s in ("RW-4418", "RW-6416", "RW-9304") for c in ("WEB", "DEALERS", "COMMERCIAL"))
    assert len(ids(tu.make("demand", skus="all", channel="WEB"))) == 10
    assert ids(tu.make("extra_order")) == ["order|RW-4418|COMMERCIAL"]
    assert ids(tu.make("build_limit", skus="mtb-base")) == ["make|RW-9324|RENO/mtb-base", "make|RW-9901|RENO/mtb-base"]
    assert len(ids(tu.make("transfer_limit"))) == 10 and ids(tu.make("transfer_limit", skus="RW-1378")) == ["move|RW-1378|RENO>CMH"]
    assert ids(tu.make("line_capacity", line="road-base")) == ["capacity||RENO/road-base"]
    c = tu.make("line_capacity", percent=120).change
    assert (c.op, c.value) == ("scale", 1.2)                                                 # overtime
    c = tu.make("extra_order", week="2027-03-03").change                                     # a date as text
    assert (c.op, c.value, c.from_t, c.to_t) == ("add", 300, 26, 26)


# ---------------- what a form refuses, and what a check says ----------------

@pytest.mark.parametrize("key, values, message", [
    ("nothing", {}, "unknown tunable"),
    ("line_capacity", {"colour": "red"}, "unknown field(s) ['colour']"),
    ("line_capacity", {"line": "mtb-titanium"}, "Line: 'mtb-titanium' is not one of the choices"),
    ("line_capacity", {"percent": 100}, "Capacity (% of normal): 100 would change nothing"),
    ("line_capacity", {"percent": 250}, "Capacity (% of normal): must be between 0 and 200"),
    ("line_capacity", {"weeks": 2.5}, "Weeks: a whole number is needed"),
    ("line_capacity", {"first": D(2026, 8, 31)}, "From: must be between 7 Sep 2026 and 31 Dec 2028"),
    ("line_capacity", {"first": "soon"}, "From: a date is needed"),
    ("stock", {"bikes": 0}, "Correction (bikes): 0 would change nothing"),
    ("demand", {"percent": 0}, "Change (%): 0 would change nothing"),
    ("target", {"weeks": 0}, "Weeks of supply: must be between 0.5 and 52"),
])
def test_a_form_that_is_filled_wrong_is_refused_with_the_reason(key, values, message):
    with pytest.raises(ValueError) as e:
        tu.make(key, **values)
    assert message in str(e.value)


def test_check_says_why_in_words():
    A = sc.CASE_A
    past = tu.make("line_capacity", first=D(2028, 12, 18))                                    # weeks 120-122
    assert tu.check(A, [past]) == ["MTB carbon line capacity · weeks of 18 Dec 2028 to 1 Jan 2029 · down (none): "
                                   "weeks after the plan (122–156) can change only on order resources"]
    assert tu.check(A, [tu.make("stock", bikes=-5000)]) == [
        "Stock of RW-9324 at Reno · at the snapshot · -5,000 bikes: 1 number(s) would go below zero (lowest -3750)"]
    twice = [tu.make("line_capacity"), tu.make("line_capacity")]
    assert tu.check(A, twice) == ["MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027 · down (none): it would "
                                  "change nothing (the numbers it selects already have that value)"]
    assert tu.check(A, [tu.make("ship_from", channel="WEB", site="Either site")]) == [
        "Ship from · Web orders · Either site: it would change nothing (that is already the setting)"]
    assert tu.check(A, [tu.make("transfer_limit")]) == [
        "Transfers to the PDC (each SKU) · weeks of 9 Nov to 30 Nov 2026 · at most 20 a week: the plan does not decide "
        "these runs in this scenario, so a limit would change nothing (it plans no transfers)"]
    assert tu.check(sc.CASE_B, [tu.make("transfer_limit")]) == []                            # B plans transfers
    assert tu.check(sc.CASE_E1, []) == [] and tu.check(sc.CASE_E3, []) == []


def test_check_agrees_with_what_running_refuses():
    """A limit on runs the plan does not decide: check names it, and run_case refuses it."""
    case = tu.apply(sc.CASE_A, [tu.make("transfer_limit", skus="RW-4418")])
    assert tu.check(case) and "plan does not decide" in tu.check(case)[0]
    with pytest.raises(ValueError, match="would change nothing"):
        sc.run_case(case)


# ---------------- in words ----------------

def test_every_tunable_in_words():
    words = {k: tu.describe(tu.make(k)) for k in tu.TUNABLES}
    assert words == {
        "stock": "Stock of RW-9324 at Reno · at the snapshot · -200 bikes",
        "line_capacity": "MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027 · down (none)",
        "demand": "Dealer orders for RW-4418 · weeks of 4 Jan to 29 Mar 2027 · +30%",
        "extra_order": "Commercial orders for RW-4418 · week of 1 Mar 2027 · +300 bikes",
        "build_limit": "RW-4418 builds · weeks of 25 Oct to 13 Dec 2027 · none",
        "transfer_limit": "Transfers to the PDC (each SKU) · weeks of 9 Nov to 30 Nov 2026 · at most 20 a week",
        "build_time": "Build time · MTB carbon · 2 weeks",
        "transfer_time": "Transfer time · Reno to the PDC · 2 weeks",
        "ship_from": "Ship from · Web orders · PDC",
        "plan_transfers": "Plan transfers · Reno to the PDC · yes",
        "target": "Target · MTB carbon · 18 weeks from 6 Sep 2027"}
    assert tu.describe(E2) == words["demand"]                                                 # the `channel` spelling too
    assert tu.describe(tu.make("line_capacity", percent=50, first=D(2026, 12, 28))) == \
        "MTB carbon line capacity · weeks of 28 Dec 2026 to 11 Jan 2027 · 50% of normal"
    assert tu.describe(tu.make("build_limit", skus="mtb-carbon", most=100)) == \
        "MTB carbon builds (each SKU) · weeks of 25 Oct to 13 Dec 2027 · at most 100 a week"
    assert [tu.name_hint(c) for c in (E1, E3, E2)] == ["MTB carbon line down from 1 Mar 2027",
                                                       "No RW-4418 built from 25 Oct 2027", "Dealer orders for RW-4418 +30%"]
    assert [tu.tunable_of(c) for c in (E1, E2, E3, STOCK, tu.make("extra_order").change)] == \
        ["line_capacity", "demand", "build_limit", "stock", "extra_order"]


def test_what_is_there_now():
    assert tu.now("line_capacity", sc.CASE_A) == "375 a week"
    assert tu.now("line_capacity", sc.CASE_E1) == "0 a week"                                 # E1's own object
    assert tu.now("line_capacity", sc.CASE_A, first=D(2027, 8, 23)) == "375 to 580 a week"
    assert tu.now("demand", sc.CASE_A) == "636 bikes forecast in those weeks"
    assert tu.now("stock", sc.CASE_A) == "1,250 bikes in stock at the snapshot"
    assert tu.now("build_limit", sc.CASE_A) == "no limit" and tu.now("build_limit", sc.CASE_E3) == "limits from 0 to 0 a week"
    assert tu.now("ship_from", sc.CASE_B, channel="WEB") == "PDC" and tu.now("plan_transfers", sc.CASE_A) == "no"
    assert tu.now("target", sc.CASE_A, group="road", **{"from": D(2028, 6, 5)}) == "10 weeks"


# ---------------- what differs between two scenarios ----------------

def test_differences_between_scenarios():
    d = tu.differences(sc.CASE_A, sc.CASE_B)
    assert d[["Tunable", "What", "From", "To"]].values.tolist() == [
        ["Ship from", "Web orders", "Either site", "PDC"], ["Ship from", "Dealer orders", "Either site", "Reno"],
        ["Ship from", "Commercial orders", "Either site", "Reno"],
        ["Build time", "Road base", "same week", "1 week"], ["Build time", "Road carbon", "same week", "1 week"],
        ["Build time", "MTB base", "same week", "1 week"], ["Build time", "MTB carbon", "same week", "1 week"],
        ["Plan transfers", "Reno to the PDC", "no", "yes"]]
    d = tu.differences(sc.CASE_A, sc.CASE_E1)
    assert d.values.tolist() == [["Line capacity", "MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027",
                                  "as in the data", "down (none)", E1.reason]]
    assert tu.differences(sc.CASE_E1, sc.CASE_A)[["From", "To"]].values.tolist() == [["down (none)", "as in the data"]]
    assert tu.differences(sc.CASE_A, sc.CASE_A).empty
    form_e2 = tu.apply(sc.CASE_A, [tu.make("demand")])
    assert tu.differences(form_e2, sc.CASE_E2).empty                                         # same edits, spelled differently
    both = tu.apply(sc.CASE_E1, [tu.make("build_limit")])
    assert tu.differences(sc.CASE_E1, both)["Tunable"].tolist() == ["Build limit"]
    assert tu.differences(sc.CASE_E3, both)["Tunable"].tolist() == ["Line capacity"]


def test_a_runs_changes_in_words_with_the_numbers_changed():
    for case, row in [(sc.CASE_E1, ["Line capacity", "MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027", "down (none)", 3,
                                    "1,125 bikes", "0 bikes"]),
                      (sc.CASE_E2, ["Demand", "Dealer orders for RW-4418 · weeks of 4 Jan to 29 Mar 2027", "+30%", 13,
                                    "636 bikes", "827 bikes"]),
                      (sc.CASE_E3, ["Build limit", "RW-4418 builds · weeks of 25 Oct to 13 Dec 2027", "none", 8,
                                    "no limit", "none"])]:
        obj = tu._base()
        report = ch.apply(obj, list(case.changes))[1]
        r = tu.change_rows(case.changes, report)
        assert r.drop(columns="Why").values.tolist() == [row] and r["Why"].tolist() == [case.changes[0].reason]


# ---------------- every data tunable runs ----------------

def test_the_forms_plan_exactly_like_the_built_in_events(A):
    for key, event in (("line_capacity", sc.CASE_E1), ("demand", sc.CASE_E2), ("build_limit", sc.CASE_E3)):
        R = sc.run_case(tu.apply(sc.CASE_A, [tu.make(key)], key="F"))
        assert R["builds"].equals(sc.run_case(event)["builds"]), key


@pytest.mark.parametrize("key, base", [("stock", "A"), ("extra_order", "A"), ("transfer_limit", "B"),
                                       ("line_capacity", "A"), ("build_limit", "A")])
def test_every_data_tunable_runs_and_passes_every_plan_check(key, base, A):
    values = {"line_capacity": {"percent": 120, "line": "road-base", "first": D(2026, 10, 5), "weeks": 6},   # overtime
              "build_limit": {"skus": "mtb-base", "most": 100, "first": D(2026, 9, 14), "weeks": 6}}.get(key, {})
    case = tu.apply({"A": sc.CASE_A, "B": sc.CASE_B}[base], [tu.make(key, **values)], key="T")
    assert tu.check(case) == []
    R = sc.run_case(case)
    c = sc.checks(R)
    assert c["pass"].all(), c[~c["pass"]].to_string()
    if key == "extra_order":                                    # the extra 300 are built, and nothing else is
        assert int(R["builds"].values.sum()) == int(A["builds"].values.sum()) + 300
        d = (by_sku(R).sum(axis=1) - by_sku(A).sum(axis=1)).astype(int)
        assert d[d != 0].to_dict() == {"RW-4418": 300}
    if key == "transfer_limit":
        assert R["moves"].loc[:, 10:13].values.max() <= 20
    if key == "build_limit":
        assert by_sku(R).loc[["RW-9324", "RW-9901"], 2:7].values.max() <= 100
    if key == "line_capacity":
        cap = R["obj"].arrivals.loc["capacity||RENO/road-base"]
        assert (cap.loc[5:10] == np.floor(A["obj"].arrivals.loc["capacity||RENO/road-base", 5:10] * 1.2 + 0.5)).all()
