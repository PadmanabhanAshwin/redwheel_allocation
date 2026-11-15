"""Events: scenarios whose world differs from the base, solved by the object itself.

A scenario is settings plus changes to the object's numbers. Each event below is scenario A's settings with one
change, and is checked three ways: the change touched exactly the numbers it says; the plan responds where it must
and nowhere else (every other line's builds identical to A, week by week); and every plan check still passes.
The expected numbers were worked out before the code was written (docs/WORKING_NOTES.md, D15)."""
from dataclasses import replace

import pandas as pd
import pytest

from redwheel import changes as ch, scenarios as sc, store
from redwheel.changes import Change

LINE = {"RW-1378": "road-carbon", "RW-2984": "road-carbon", "RW-3980": "road-carbon", "RW-7298": "road-base",
        "RW-9835": "road-base", "RW-9324": "mtb-base", "RW-9901": "mtb-base", "RW-4418": "mtb-carbon",
        "RW-6416": "mtb-carbon", "RW-9304": "mtb-carbon"}


@pytest.fixture(scope="module")
def A():
    return sc.run_case(sc.CASE_A)


def by_sku(R):
    b = R["builds"].copy()
    b.index = b.index.str.split("|").str[1]
    return b


def held(R):
    return {ln: str(d.date()) for ln, d in sc.held_by_line(R).max(axis=1).items()}


def lines_that_moved(R, A):
    b, b0 = by_sku(R), by_sku(A)
    return sorted({LINE[s] for s in b.index if (b.loc[s].values != b0.loc[s].values).any()})


def all_checks_pass(R):
    c = sc.checks(R)
    assert c["pass"].all(), c[~c["pass"]].to_string()


def test_scenarios_without_changes_run_as_before(A):
    assert sc.CASE_A.changes == () and sc.CASE_B.changes == ()
    assert len(A["change_report"]) == 0
    assert int(A["builds"].values.sum()) == 94_429 and held(A)["mtb-carbon"] == "2027-09-06"


def test_event_1_line_down(A):
    """MTB carbon line down for the weeks of 1, 8 and 15 Mar 2027 (plan weeks 26-28)."""
    R = sc.run_case(sc.CASE_E1)
    rep = R["change_report"].iloc[0]
    assert (rep["resources"], rep["cells"], rep["before"], rep["after"]) == (1, 3, 1125, 0)
    b = by_sku(R)
    mtb_carbon = [s for s, ln in LINE.items() if ln == "mtb-carbon"]
    assert b.loc[mtb_carbon, [26, 27, 28]].values.sum() == 0                        # nothing built while it is down
    assert int(b.values.sum()) == 94_429                                              # same bikes, built at other times
    assert lines_that_moved(R, A) == ["mtb-carbon"]
    assert held(R) == {**held(A), "mtb-carbon": "2027-10-04"}                         # was 6 Sep 2027
    all_checks_pass(R)
    # Nothing can be built ahead: in A the line is full every week to 30 Aug 2027 (weeks 1-52). The 1,125 bikes
    # lost are made up exactly in weeks 53-57 (6 Sep - 4 Oct 2027), out of capacity A leaves spare.
    line_A, line_E = by_sku(A).loc[mtb_carbon].sum(), b.loc[mtb_carbon].sum()
    cap = A["obj"].arrivals.loc["capacity||RENO/mtb-carbon"]
    assert (line_A.loc[1:52] == cap.loc[1:52]).all()
    diff = (line_E - line_A).astype(int)
    assert diff[diff != 0].to_dict() == {26: -375, 27: -375, 28: -375, 53: 77, 54: 292, 55: 290, 56: 289, 57: 177}
    assert diff.loc[53:57].sum() == 1_125


def test_event_1_remixes_the_skus_around_the_stoppage_but_not_the_line_total(A):
    """The line's total builds differ from A's only in weeks 26-28 and 53-57 (the stoppage and the catch-up). The mix of
    its three SKUs shifts around the stoppage: bikes move between SKUs, none are added. The other lines are identical,
    SKU by SKU. (The README says exactly this; an earlier note said every other week was built as in A, which holds for
    the line's total, not for each SKU.)"""
    R = sc.run_case(sc.CASE_E1)
    d = (by_sku(R) - by_sku(A)).astype(int)
    mtb = ["RW-4418", "RW-6416", "RW-9304"]
    assert (d.drop(index=mtb) == 0).all().all()
    total = d.loc[mtb].sum()
    assert list(total[total != 0].index) == [26, 27, 28, 53, 54, 55, 56, 57]
    assert d.loc[mtb, 25].to_dict() == {"RW-4418": -9, "RW-6416": -6, "RW-9304": 15}            # the re-mix before the stoppage
    assert d.loc[mtb, 29].to_dict() == {"RW-4418": -4, "RW-6416": -2, "RW-9304": 6}
    quiet = [t for t in d.columns if t not in (25, 26, 27, 28, 29, *range(53, 58))]
    assert d.loc[mtb, quiet].abs().max().max() <= 1                                              # elsewhere: one-bike swaps


def test_event_2_demand_up(A):
    """Dealer forecast for RW-4418 up 30% for the weeks of 4 Jan to 29 Mar 2027 (plan weeks 18-30)."""
    R = sc.run_case(sc.CASE_E2)
    rep = R["change_report"].iloc[0]
    assert (rep["resources"], rep["cells"], rep["before"], rep["after"]) == (1, 13, 636, 827)
    b, b0 = by_sku(R), by_sku(A)
    extra = (b.sum(axis=1) - b0.sum(axis=1)).astype(int)
    assert extra[extra != 0].to_dict() == {"RW-4418": 191}                            # exactly the added demand
    assert lines_that_moved(R, A) == ["mtb-carbon"]
    assert held(R) == {**held(A), "mtb-carbon": "2027-09-13"}
    all_checks_pass(R)


def test_a_stock_correction(A):
    """200 fewer RW-9324 at Reno than counted: 200 more built, all RW-9324; it has stock to spare, so no date moves."""
    R = sc.run_case(replace(sc.CASE_A, key="S", changes=(
        Change("opening", {"kind": "inventory", "item": "RW-9324", "location": "RENO"}, "add", -200, reason="count"),)))
    rep = R["change_report"].iloc[0]
    assert (rep["cells"], rep["before"], rep["after"]) == (1, 1250, 1050)
    b, b0 = by_sku(R), by_sku(A)
    extra = (b.sum(axis=1) - b0.sum(axis=1)).astype(int)
    assert extra[extra != 0].to_dict() == {"RW-9324": 200}
    assert lines_that_moved(R, A) == ["mtb-base"] and held(R) == held(A)
    all_checks_pass(R)


def test_a_scenario_with_changes_that_break_a_rule_is_refused():
    bad = replace(sc.CASE_A, key="X", changes=(Change("arrival", {"kind": "capacity"}, "set", 0, 120, 125),))
    with pytest.raises(ValueError, match="can change only on order resources"):
        sc.run_case(bad)


# ---------------- saving ----------------

def test_changes_are_saved_and_loaded_with_the_scenario(tmp_path, A):
    store.save(sc.CASE_E1, tmp_path)
    back = store.load_all(tmp_path)["E1"]
    assert back.changes == sc.CASE_E1.changes
    R = sc.run_case(back)
    assert held(R)["mtb-carbon"] == "2027-10-04"


def test_a_file_saved_before_changes_existed_loads_with_none(tmp_path):
    store.save(sc.Case("C", "Scenario C · old", sc.CASE_B.priors, "", "B"), tmp_path)
    import json
    path = tmp_path / "C.json"
    d = json.loads(path.read_text())
    del d["changes"]
    path.write_text(json.dumps(d))
    assert store.load_all(tmp_path)["C"].changes == ()


def test_a_saved_change_that_is_not_a_change_is_refused_on_load(tmp_path):
    import json
    store.save(sc.CASE_E1, tmp_path)
    path = tmp_path / "E1.json"
    d = json.loads(path.read_text())
    d["changes"][0]["colour"] = "red"
    path.write_text(json.dumps(d))
    with pytest.raises(ValueError, match="not a change"):
        store.load_all(tmp_path)
    assert ch.from_records(ch.to_records(sc.CASE_E2.changes)) == sc.CASE_E2.changes
