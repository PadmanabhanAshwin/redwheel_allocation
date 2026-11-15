"""The priority order (redwheel/walk.py), from the facts to the plan.

The facts: when the opening orders are due, on the object, recounted from the raw files. The rule: what an order
with no date means. The walk: its rules, each broken on purpose; how it becomes what the solver takes; the floors.
Then worked by hand on two bikes, and end to end on Redwheel (scenarios A and B) through `run_case`."""
import csv
import datetime as dt
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from redwheel import changes as ch, engine, rtn, scenarios as sc, store, walk as wk
from redwheel.changes import Change
from redwheel.config import RAW_DIR
from redwheel.walk import Step, Walk
from test_engine import two_skus_one_line

MTB = ("RW-9304", "RW-4418", "RW-6416")
START = dt.date(2026, 9, 7)


# ---------------- the facts: when the opening orders are due ----------------

def _raw_open_orders():
    """(channel, sku, qty, order date, date asked for or None) for every order line open at the snapshot (not
    fulfilled, or shipped after it), read from the three raw files with the standard library only."""
    day = lambda s, f: dt.datetime.strptime(s, f).date()
    is_open = lambda done, shipped, f: not done or (bool(shipped.strip()) and day(shipped, f) > START)
    out = []
    for r in csv.DictReader(open(Path(RAW_DIR) / "dtc_web_orders.csv")):
        if is_open(r["is_fulfilled"].strip().lower() == "true", r["ship_date"], "%Y-%m-%d"):
            out.append(("WEB", r["sku"], int(r["qty"]), day(r["order_date"], "%Y-%m-%d"), None))
    for r in csv.DictReader(open(Path(RAW_DIR) / "dealer_orders_export.csv")):
        if is_open(r["Fulfilled (Y/N)"].strip().upper() == "Y", r["Shipped"], "%m/%d/%Y"):
            out.append(("DEALERS", r["SKU"], int(r["Qty"]), day(r["Order Date"], "%m/%d/%Y"),
                        day(r["Requested Ship Date"], "%m/%d/%Y")))
    for r in csv.DictReader(open(Path(RAW_DIR) / "Commercial_PO_Log.csv")):
        if is_open(r["Fulfilled"].strip().lower() == "yes", r["Delivered"], "%d-%b-%Y"):
            out.append(("COMMERCIAL", r["Product"], int(r["Units"]), day(r["PO Date"], "%d-%b-%Y"),
                        day(r["Need By"], "%d-%b-%Y")))
    return out


def test_the_due_table_is_the_order_files_recounted(obj):
    raw = _raw_open_orders()
    d = obj.due
    assert list(d.columns) == rtn.DUE_COLUMNS
    assert d["qty"].sum() == sum(q for *_, q, _, _ in raw) == 5991
    undated = d[d["due"].isna()]
    assert undated["qty"].sum() == sum(q for c, _, q, _, asked in raw if asked is None) == 2139
    assert undated["resource_id"].str.endswith("|WEB").all()                   # every web order, and only those
    assert not d[d["due"].notna()]["resource_id"].str.endswith("|WEB").any()
    week = lambda day: (day - START).days // 7 + 1
    past = sum(q for _, _, q, _, asked in raw if asked is not None and week(asked) <= 0)
    later = sum(q for _, _, q, _, asked in raw if asked is not None and week(asked) >= 1)
    assert (d[d["due"] <= 0]["qty"].sum(), d[d["due"] >= 1]["qty"].sum()) == (past, later) == (2385, 1467)
    for chan, sku in {(c, s) for c, s, *_ in raw}:                              # row by row, per order resource
        mine = [(q, placed, asked) for c, s, q, placed, asked in raw if (c, s) == (chan, sku)]
        got = d[d["resource_id"] == f"order|{sku}|{chan}"]
        assert got["qty"].sum() == sum(q for q, _, _ in mine) == obj.opening[f"order|{sku}|{chan}"]
        by_week = got.groupby("due")["qty"].sum().to_dict()
        want = {}
        for q, _, asked in mine:
            if asked is not None:
                want[week(asked)] = want.get(week(asked), 0) + q
        assert by_week == want
        undated_days = sorted((p - START).days for _, p, asked in mine if asked is None)
        got_days = sorted((got[got["due"].isna()]["placed"] * 7).round().astype(int))
        assert sorted(set(undated_days)) == got_days                           # when each undated order was placed
    assert (d["placed"] <= 0).all() and d["placed"].min() == pytest.approx(-125 / 7)   # oldest: 125 days before


def toy_due(rows, opening=10, H=4):
    """One bike A (and B), one line; A's order resource opens with `opening`, dated as `rows`: (qty, due, placed)."""
    obj = two_skus_one_line(capacity=10, H=H)
    obj.opening["order|A|C"] = opening
    return replace(obj, due=pd.DataFrame([("order|A|C", *r) for r in rows], columns=rtn.DUE_COLUMNS).astype(
        {"qty": float, "due": float, "placed": float}))


def test_not_yet_due_by_hand():
    """Ten open orders: 3 past their date, 2 due in week 3, 4 with no date placed three and a half days before the
    plan, 1 the table does not list. With 7 days the undated four are due in week 1; with 14, in week 2."""
    obj = toy_due([(3, 0, -2.0), (2, 3, -1.0), (4, np.nan, -0.5)])
    rtn.validate(obj)
    assert wk.not_due(obj, 7).loc["order|A|C"].tolist() == [2, 2, 0, 0]
    assert wk.not_due(obj, 14).loc["order|A|C"].tolist() == [6, 2, 0, 0]
    assert wk.not_due(obj, 0).loc["order|A|C"].tolist() == [2, 2, 0, 0]
    assert wk.not_due(obj, 28).loc["order|A|C"].tolist() == [6, 6, 4, 0]       # 24.5 days in: week 4
    assert (wk.not_due(obj, 7).loc["order|B|C"] == 0).all()
    assert (wk.not_due(replace(obj, due=None), 7).values == 0).all()           # no dates known: all due at once


@pytest.mark.parametrize("placed_days, days, week", [(-7, 7, 1), (-1, 7, 1), (0, 7, 2), (-7, 14, 2), (-8, 14, 1),
                                                     (-30, 7, -3), (0, 0, 1), (-3, 3, 1)])
def test_an_order_with_no_date_is_due_in_the_week_that_day_falls_in(placed_days, days, week):
    """Placed `placed_days` from the start of week 1 (a Monday), due `days` later: the plan week of that day."""
    obj = toy_due([(5, np.nan, placed_days / 7)])
    last_not_due = int((wk.not_due(obj, days).loc["order|A|C"] > 0).sum())
    assert last_not_due == max(week - 1, 0)
    assert (START + dt.timedelta(days=placed_days + days) - START).days // 7 + 1 == week    # the same, on a calendar


@pytest.mark.parametrize("rows, message", [
    ([(3, 0, -1.0), (8, 2, -1.0)], "more orders than the opening level"),
    ([(0, 1, -1.0)], "no quantity"),
    ([(3, 1.5, -1.0)], "whole week"),
    ([(3, 1, 0.5)], "placed before the plan starts"),
])
def test_a_due_table_that_does_not_fit_the_object_is_refused(rows, message):
    with pytest.raises(ValueError, match=message):
        rtn.validate(toy_due(rows))
    obj = toy_due([(3, 0, -1.0)])
    with pytest.raises(ValueError, match="not an order"):
        rtn.validate(replace(obj, due=obj.due.assign(resource_id="inventory|A|F")))
    with pytest.raises(ValueError, match="columns"):
        rtn.validate(replace(obj, due=obj.due.rename(columns={"placed": "when"})))


def test_open_orders_cannot_be_cut_below_the_ones_with_known_dates():
    """Rule 9 of changes: the table says when 9 of the 10 are due; cutting to 8 would leave it not knowing which."""
    obj = toy_due([(3, 0, -2.0), (2, 3, -1.0), (4, np.nan, -0.5)])
    cut = Change("opening", {"kind": "order", "item": "A"}, "set", 8, None, None, "cancelled")
    assert "below the orders whose dates the object knows" in ch.check(obj, [cut])[0]
    with pytest.raises(ValueError, match="below the orders whose dates"):
        ch.apply(obj, [cut])
    for ok in (Change("opening", {"kind": "order", "item": "A"}, "set", 9, None, None, ""),
               Change("opening", {"kind": "order", "item": "A"}, "add", 5, None, None, "")):
        new, _ = ch.apply(obj, [ok])                                           # the added ones are due at once
        assert wk.not_due(new, 7).loc["order|A|C"].tolist() == [2, 2, 0, 0] and new.due is obj.due


# ---------------- the rules of a walk ----------------

EVEN = Walk((Step("due"), Step("owed"), Step("target")))


def test_the_usual_walks_break_no_rule(obj):
    assert wk.check(EVEN, obj) == []
    assert wk.check(Walk((Step("target"),)), obj) == []                        # the standing rule, as a walk
    assert wk.check(sc.CASE_P1.walk, obj) == []
    assert wk.check(wk.standard(obj, "line_id", {"mtb-carbon": (MTB, True), "road-base": (("RW-9835",), False)}), obj) == []


@pytest.mark.parametrize("walk, message", [
    (Walk((Step("cover"),)), "floor must be one of"),                                                   # 1
    (Walk((Step("target", share="first"),)), "share must be one of"),                                   # 1
    (Walk((Step("target", {"colour": "red"}),)), "unknown column"),                                     # 2
    (Walk((Step("target", {"line_id": "tandem"}),)), "matches no item"),                                # 2
    (Walk((Step("owed"), Step("target", share="ranked"))), "a ranked step needs an order"),             # 3
    (Walk((Step("owed"), Step("target", {}, "ranked", ("RW-9304", "RW-9304")))), "listed twice"),       # 3
    (Walk((Step("owed"), Step("target", {"line_id": "mtb-carbon"}, "ranked", ("RW-9835",)),
           Step("target", {"line_id": ["road-base", "road-carbon", "mtb-base"]}))), "not in the step's selection"),
    (Walk((Step("target", order=("RW-9304",)),)), "an even step has no order"),                         # 3
    (Walk((Step("target"), Step("target", {"line_id": "mtb-carbon"}))), "already in step 1 on the target floor"),  # 4
    (Walk((Step("owed"), Step("target", {"line_id": "mtb-carbon"}))), "no target step for RW-"),        # 5
    (Walk((Step("target"), Step("owed"))), "must go due, then owed, then target"),                      # 6
    (Walk((Step("owed"), Step("due"), Step("target"))), "must go due, then owed, then target"),         # 6
    (Walk((Step("target", {}, "ranked", MTB),)), "needs an owed step for the same items before it"),    # 7: the trap
    (Walk((Step("owed", {"line_id": "road-base"}), Step("target", {}, "ranked", MTB))), "needs an owed step"),  # 7
    (Walk((Step("target"),), no_date_days=-1), "no_date_days must be a whole number"),                  # 8
    (Walk((Step("target"),), no_date_days=7.5), "no_date_days must be a whole number"),                 # 8
    (Walk((Step("target"),), no_date_days=366), "no_date_days must be a whole number"),                 # 8
])
def test_each_rule_broken_is_named(obj, walk, message):
    problems = wk.check(walk, obj)
    assert problems and any(message in p for p in problems), problems
    with pytest.raises(ValueError, match="the priority order cannot run"):
        wk.solver_input(SimpleNamespace(key="X", walk=walk), obj, {}, pd.DataFrame())


def test_a_walk_with_no_steps_is_no_walk(obj):
    assert not Walk() and Walk((Step("target"),))
    assert wk.solver_input(SimpleNamespace(key="X", walk=Walk()), obj, {}, pd.DataFrame()) == (None, None)
    assert wk.solver_input(SimpleNamespace(key="X", walk=None), obj, {}, pd.DataFrame()) == (None, None)
    assert wk.check(Walk(), obj) == ["a walk needs at least one step"]


# ---------------- what the solver takes ----------------

def test_a_ranked_step_becomes_one_step_per_bike_then_the_rest(obj):
    pos = sc.positions(obj, sc.pools(sc.ALL_ROUTES))                           # scenario A: one position per bike
    one = lambda s: [(s, "CMH+RENO")]
    w = Walk((Step("owed"), Step("target", {"line_id": "mtb-carbon"}, "ranked", ("RW-6416",)),
              Step("target", {"line_id": ["road-base", "road-carbon", "mtb-base"]})))
    steps = wk.resolve(w, obj, pos)
    assert [f for f, _ in steps] == ["owed", "target", "target", "target"]
    assert len(steps[0][1]) == 10
    assert steps[1][1] == one("RW-6416")                                       # the one ranked
    assert sorted(steps[2][1]) == sorted(one("RW-4418") + one("RW-9304"))      # the line's others follow, together
    assert len(steps[3][1]) == 7 and not {k[0] for k in steps[3][1]} & set(MTB)
    full = wk.resolve(sc.CASE_P1.walk, obj, pos)
    assert [(f, [k[0] for k in ks]) for f, ks in full[2:5]] == [("target", [s]) for s in MTB]
    assert len(full) == 6                                                       # nothing empty is handed over


def test_a_bike_with_two_positions_keeps_them_in_one_step(obj):
    """Scenario B: a bike has a position at Reno (dealer and commercial orders) and one at the PDC (web orders)."""
    pos = sc.positions(obj, sc.pools(sc.CASE_B.ship_routes))
    steps = wk.resolve(sc.CASE_P1.walk, obj, pos)
    assert [sorted(ks) for _, ks in steps[2:5]] == [[(s, "CMH"), (s, "RENO")] for s in MTB]
    assert len(steps[0][1]) == 20 and len(steps[5][1]) == 14


def _input(case, obj):
    pos = sc.positions(obj, sc.pools(case.ship_routes))
    tu_ = pd.DataFrame(100.0, index=pd.MultiIndex.from_tuples(list(pos), names=["item", "pool"]),
                       columns=range(1, len(obj.weeks) + 1))
    return pos, tu_, wk.solver_input(case, obj, pos, tu_)


def test_the_due_floor_is_minus_the_orders_not_yet_due_that_a_position_faces(obj):
    """Opening floors of the three MTB carbon bikes (docs/RANKED_WALK.md): due -146, -123, -56 in week 1; none from
    week 9. In B the dated orders sit at Reno; the PDC faces web orders, which seven days make due in week 1."""
    pos, tu_, (floors, steps) = _input(replace(sc.CASE_A, walk=EVEN), obj)
    due = floors["due"]
    assert [due.at[(s, "CMH+RENO"), 1] for s in MTB] == [-146, -123, -56]
    assert due[1].sum() == -1080 and due[8].sum() == -11 and (due[9] == 0).all() and (due.values <= 0).all()
    assert (floors["owed"].values == 0).all() and floors["target"] is tu_
    assert (due.diff(axis=1).iloc[:, 1:].values >= 0).all()                    # orders only become due
    posB, tuB, (floorsB, _) = _input(replace(sc.CASE_B, walk=EVEN), obj)
    assert [floorsB["due"].at[(s, "RENO"), 1] for s in MTB] == [-146, -123, -56]
    assert (floorsB["due"].loc[[k for k in posB if k[1] == "CMH"]].values == 0).all()
    late = replace(sc.CASE_B, walk=replace(EVEN, no_date_days=14))             # web orders of the last week: 216
    assert _input(late, obj)[2][0]["due"].loc[[k for k in posB if k[1] == "CMH"], 1].sum() == -216


def test_what_is_handed_to_the_solver_keeps_its_promises(obj):
    for case in (replace(sc.CASE_A, walk=sc.CASE_P1.walk), replace(sc.CASE_B, walk=sc.CASE_P1.walk),
                 replace(sc.CASE_B, walk=wk.standard(obj, "line_id", {"mtb-carbon": (MTB, True)}))):
        pos, tu_, (floors, steps) = _input(case, obj)
        assert (floors["due"].values <= floors["owed"].values).all() and (floors["owed"].values <= tu_.values).all()
        for f in wk.FLOORS:
            named = [k for g, ks in steps if g == f for k in ks]
            assert len(named) == len(set(named)) == len(pos) and set(named) == set(tu_.index)
        assert all(f in floors for f, _ in steps) and all(v.index.equals(tu_.index) for v in floors.values())


def test_floors_that_are_not_nested_are_refused(obj):
    pos = sc.positions(obj, sc.pools(sc.ALL_ROUTES))
    below = pd.DataFrame(-1.0, index=pd.MultiIndex.from_tuples(list(pos)), columns=range(1, len(obj.weeks) + 1))
    with pytest.raises(ValueError, match="not nested"):
        wk.floors(obj, pos, below, EVEN)


# ---------------- in words, and saved ----------------

def test_a_walk_in_words(obj):
    assert wk.lines(None) == ["1. Target · every item · shared evenly"]
    assert wk.lines(sc.CASE_P1.walk) == [
        "1. Orders past their date · every item · shared evenly",
        "2. All open orders · every item · shared evenly",
        "3. Target · line_id mtb-carbon · in order: RW-9304, then RW-4418, then RW-6416",
        "4. Target · line_id mtb-base, road-base, road-carbon · shared evenly"]
    part = Step("target", {"line_id": "mtb-carbon"}, "ranked", ("RW-6416",))
    assert wk.step_words(part, obj=obj) == "Target · line_id mtb-carbon · in order: RW-6416, then the others evenly"
    assert wk.step_words(sc.CASE_P1.walk.steps[2], obj=obj).endswith("then RW-6416")       # nobody is left out


def test_the_usual_walk_and_reading_it_back(obj):
    assert wk.standard(obj) == EVEN and wk.ranking(EVEN, obj, "line_id") == {}
    assert wk.standard(obj, "line_id", {"mtb-carbon": (MTB, False)}) == sc.CASE_P1.walk
    assert wk.ranking(sc.CASE_P1.walk, obj, "line_id") == {"mtb-carbon": (MTB, False)}
    both = {"mtb-carbon": (MTB, True), "road-base": (("RW-9835",), False)}
    w = wk.standard(obj, "line_id", both, 21)
    assert wk.ranking(w, obj, "line_id") == both and w.no_date_days == 21
    assert [st.floor for st in w.steps] == ["due", "due", "owed", "owed", "target", "target", "target"]
    assert wk.ranking(Walk((Step("target"),)), obj, "line_id") is None         # not of the usual form


def test_a_walk_is_saved_with_its_scenario_and_old_files_load_without_one(tmp_path, obj):
    w = wk.standard(obj, "line_id", {"mtb-carbon": (MTB, True)}, 10)
    assert wk.from_record(wk.to_record(w)) == w and wk.to_record(None) is None and wk.from_record(None) is None
    store.save(replace(sc.CASE_P1, key="Q", walk=w), tmp_path)
    store.save(replace(sc.CASE_E1, key="R"), tmp_path)
    back = store.load_all(tmp_path)
    assert back["Q"].walk == w and back["R"].walk is None and back["R"].changes == sc.CASE_E1.changes
    import json
    d = json.loads((tmp_path / "R.json").read_text()); d.pop("walk")           # a file from before walks existed
    (tmp_path / "R.json").write_text(json.dumps(d))
    assert store.load_all(tmp_path)["R"].walk is None


# ---------------- by hand: two bikes, one line ----------------

def two_bikes(due_rows):
    """X (item A) and Y (item B) share a line that builds 10 a week, three weeks, no new demand. Each has 10 open
    orders and should hold 20. One week of demand is 10 bikes for both."""
    obj = two_skus_one_line(capacity=10, H=3)
    obj.opening["order|A|C"] = obj.opening["order|B|C"] = 10
    obj = replace(obj, due=pd.DataFrame(due_rows, columns=rtn.DUE_COLUMNS).astype({"qty": float, "due": float, "placed": float}))
    rtn.validate(obj)
    tgt = pd.DataFrame(20.0, index=["A", "B"], columns=[1, 2, 3])
    pos = {i: {f"inventory|{i}|F": 1.0, f"order|{i}|C": -1.0} for i in ("A", "B")}
    return obj, tgt, pos


def plan_two(obj, tgt, pos, walk):
    args = (obj, ["make|A|L", "make|B|L"], tgt, pd.Series({"A": 10.0, "B": 10.0}), pd.Series({"A": "L", "B": "L"}))
    floors, steps = wk.solver_input(SimpleNamespace(key="T", walk=walk), obj, pos, tgt)
    p = engine.decide_walk(*args, floors, steps, positions=pos, w_run=1e-6) if steps else \
        engine.decide(*args, positions=pos, w_run=1e-6)
    whole = lambda task: (p.runs.loc[task].round(4) + 0.0).tolist()          # the solver's 1e-6 is not a bike
    return [f"{x:g}/{y:g}" for x, y in zip(whole("make|A|L"), whole("make|B|L"))], p


def test_the_customer_past_their_date_is_served_first_by_hand():
    """X's ten orders are past their date. Y's ten are due in week 3.

    No walk: both are ten short, so the line is shared: 5/5 every week, and X's customers, already late, wait
    two weeks. With the walk: week 1 goes to X (the only orders past their date); week 2 to Y, who is owed but not
    yet late, and is served before the date; week 3 is shared toward the target."""
    obj, tgt, pos = two_bikes([("order|A|C", 10, 0, -3.0), ("order|B|C", 10, 3, -1.0)])
    assert plan_two(obj, tgt, pos, None)[0] == ["5/5", "5/5", "5/5"]
    builds, p = plan_two(obj, tgt, pos, wk.standard(obj))
    assert builds == ["10/0", "0/10", "5/5"]
    r = wk.results(p.steps)
    assert r["floor"].tolist() == ["due", "owed", "target"]
    assert r["met"].tolist() == [True, False, False]               # nobody waits past their date
    # In weeks of demand (10 bikes). Owed: Y is 10 short for one week = 1. Target (20): X is short 20, 20, 15 and
    # Y 30, 20, 15: 5.5 + 6.5 = 12 in all; the larger of the two each week is 3, 2, 1.5 = 6.5.
    assert r["total"].round(4).tolist() == [0, 1, 12] and r["worst"].round(4).tolist() == [0, 1, 6.5]
    net = rtn.levels(obj, p.runs)
    assert (net.loc["inventory|A|F"] - net.loc["order|A|C"]).round(4).tolist() == [-10, 0, 0, 5]
    assert (net.loc["inventory|B|F"] - net.loc["order|B|C"]).round(4).tolist() == [-10, -10, 0, 5]


def test_with_the_same_dates_the_walk_changes_nothing_by_hand():
    """Both past their date: the due step is the owed step, and sharing evenly is what the plan did anyway."""
    obj, tgt, pos = two_bikes([("order|A|C", 10, 0, -3.0), ("order|B|C", 10, -1, -3.0)])
    assert plan_two(obj, tgt, pos, wk.standard(obj))[0] == plan_two(obj, tgt, pos, None)[0] == ["5/5", "5/5", "5/5"]


def test_an_order_with_no_date_is_late_or_not_by_the_rule_by_hand():
    """X's ten are past their date; Y's ten carry no date and were placed three days before the plan. Due in 7 days
    they are due in week 1, like X's: shared. Due in 14 days they are due in week 2: X goes first."""
    obj, tgt, pos = two_bikes([("order|A|C", 10, 0, -3.0), ("order|B|C", 10, np.nan, -3 / 7)])
    assert plan_two(obj, tgt, pos, wk.standard(obj, no_date_days=7))[0] == ["5/5", "5/5", "5/5"]
    assert plan_two(obj, tgt, pos, wk.standard(obj, no_date_days=14))[0] == ["10/0", "0/10", "5/5"]


def test_a_ranked_target_by_hand():
    """Orders first, evenly (5/5, 5/5: both cleared after two weeks), then the target in order: week 3 goes to Y."""
    obj, tgt, pos = two_bikes([("order|A|C", 10, 0, -3.0), ("order|B|C", 10, 0, -3.0)])
    w = wk.standard(obj, "item", {"B": (("B",), False)})
    assert wk.check(w, obj) == []
    assert plan_two(obj, tgt, pos, w)[0] == ["5/5", "5/5", "0/10"]
    both = wk.standard(obj, "item", {"B": (("B",), True)})         # Y's orders first too
    assert plan_two(obj, tgt, pos, both)[0] == ["0/10", "10/0", "0/10"]


# ---------------- end to end on Redwheel ----------------

@pytest.fixture(scope="module")
def A():
    return sc.run_case(sc.CASE_A)


@pytest.fixture(scope="module")
def P1():
    return sc.run_case(sc.CASE_P1)


def dates(R, ok):
    """position -> the Monday from which a condition holds to the end."""
    weeks = list(R["target_units"].columns)
    start = R["obj"].weeks.set_index("t")["week_start"]
    return {k: start[int(t)].date() for k, t in sc.held_from(ok[weeks]).items() if not pd.isna(t)}


def facts(R):
    s = sc.scorecard(R)
    ck = sc.checks(R)
    return {"cleared": s["Open orders cleared from"].date(), "fill": round(s["On-time fill rate"], 3),
            "below": s["Position-weeks below target"], "held": s["All targets held from"].date(),
            "built": s["Bikes built"], "checks": (int(ck["pass"].sum()), len(ck))}


def test_the_standing_rule_written_as_a_walk_is_the_same_plan(A):
    R = sc.run_case(replace(sc.CASE_A, key="W", walk=Walk((Step("target"),))))
    assert (R["builds"].values == A["builds"].values).all() and facts(R) == {**facts(A), "checks": (10, 10)}


def test_scenario_p1_nobody_waits_longer_and_two_bikes_reach_their_target_months_sooner(A, P1):
    a, p = facts(A), facts(P1)
    assert a == {"cleared": dt.date(2026, 12, 14), "fill": 0.964, "below": 278, "held": dt.date(2027, 9, 6),
                 "built": 94429, "checks": (9, 9)}
    assert p == {**a, "below": 244, "checks": (10, 10)}                        # same customers' dates, same total
    k = lambda s: (s, "CMH+RENO")
    cleared_a, cleared_p = (dates(R, R["flows"]["open_orders"] < 0.5) for R in (A, P1))
    assert [cleared_p[k(s)] for s in MTB] == [cleared_a[k(s)] for s in MTB] == [dt.date(2026, 12, 14)] * 3
    at_a, at_p = (dates(R, R["at_target"]) for R in (A, P1))
    assert [at_a[k(s)] for s in MTB] == [dt.date(2027, 9, 6)] * 3
    assert [at_p[k(s)] for s in MTB] == [dt.date(2027, 2, 22), dt.date(2027, 7, 26), dt.date(2027, 9, 6)]
    other = [i for i in A["builds"].index if not any(s in i for s in MTB)]
    d = (P1["builds"] - A["builds"]).abs()
    assert ((d.loc[other].values > 0).sum(), d.loc[other].values.max()) == (14, 11)     # other lines: the due step only
    assert ((d.drop(index=other).values > 0).sum(), d.drop(index=other).values.max()) == (138, 162)
    line = A["builds"].index.str.split("/").str[1]                             # each line builds as many bikes each
    assert (P1["builds"].groupby(line).sum().values == A["builds"].groupby(line).sum().values).all()   # week: the mix moved
    assert P1["walk"]["steps"][2:5] == [("target", [k(s)]) for s in MTB]
    r = wk.results(P1["lp"].steps)
    assert r["floor"].tolist() == ["due", "owed", "target", "target", "target", "target"] and not r["met"].any()
    assert (r["worst"] > 0).all() and (r["total"] >= r["worst"] - 1e-9).all()


def test_dates_first_shared_evenly_moves_no_headline(A):
    R = sc.run_case(replace(sc.CASE_A, key="W", walk=EVEN))
    assert facts(R) == {**facts(A), "checks": (10, 10)}
    d = np.abs(R["builds"].values - A["builds"].values)
    assert ((d > 0).sum(), d.max()) == (35, 24)


def test_one_week_or_none_for_an_order_with_no_date_is_the_same_weekly_plan(A):
    seven = sc.run_case(replace(sc.CASE_A, key="W", walk=EVEN))
    none = sc.run_case(replace(sc.CASE_A, key="W", walk=replace(EVEN, no_date_days=0)))
    month = sc.run_case(replace(sc.CASE_A, key="W", walk=replace(EVEN, no_date_days=28)))
    assert (seven["builds"].values == none["builds"].values).all()
    assert (seven["builds"].values != month["builds"].values).any() and facts(month) == facts(seven)


def test_the_order_decides_whose_orders_are_cleared_first_too(A, obj):
    R = sc.run_case(replace(sc.CASE_A, key="W", walk=wk.standard(obj, "line_id", {"mtb-carbon": (MTB, True)})))
    assert facts(R) == {**facts(A), "fill": 0.974, "below": 244, "checks": (10, 10)}
    cleared = dates(R, R["flows"]["open_orders"] < 0.5)
    assert [cleared[(s, "CMH+RENO")] for s in MTB] == [dt.date(2026, 10, 12), dt.date(2026, 11, 9), dt.date(2026, 12, 14)]
    assert len(R["lp"].steps) == 12


@pytest.mark.parametrize("orders_too", [False, True])
def test_a_priority_order_runs_on_scenario_b_with_every_check_passing(obj, orders_too):
    """In B each bike has two positions; the walk keeps them together. Every check passes, whole bikes included."""
    R = sc.run_case(replace(sc.CASE_B, key="W", walk=wk.standard(obj, "line_id", {"mtb-carbon": (MTB, orders_too)})))
    ck = sc.checks(R)
    assert len(ck) == 10 and ck["pass"].all(), ck[~ck["pass"]]
    at = dates(R, R["at_target"])                                              # B without a walk: all 27 Sep 2027
    assert [at[(s, p)] for s in MTB for p in ("RENO", "CMH")] == [dt.date(2027, 4, 19)] * 2 + [dt.date(2027, 8, 23)] * 2 \
        + [dt.date(2027, 9, 27)] * 2
    f = facts(R)
    assert (f["cleared"], f["below"], f["held"], f["built"]) == (dt.date(2027, 1, 4), 666, dt.date(2027, 9, 27), 94429)
    assert f["fill"] == (0.966 if orders_too else 0.953)                       # B without a walk: 0.953, 722 below


def test_a_scenario_with_a_walk_that_breaks_a_rule_does_not_run():
    with pytest.raises(ValueError, match="scenario W: the priority order cannot run: .*needs an owed step"):
        sc.run_case(replace(sc.CASE_A, key="W", walk=Walk((Step("target", {}, "ranked", MTB),))))


def test_a_walk_and_an_event_together(A, obj):
    """E3 (no RW-4418 built for eight weeks, known in advance) under P1's priority order: the pinned bike lets the
    line go to the next one, and every check passes."""
    R = sc.run_case(replace(sc.CASE_E3, key="W", walk=sc.CASE_P1.walk))
    ck = sc.checks(R)
    assert len(ck) == 10 and ck["pass"].all(), ck[~ck["pass"]]
    assert (R["builds"].loc["make|RW-4418|RENO/mtb-carbon", list(range(60, 68))] == 0).all()
