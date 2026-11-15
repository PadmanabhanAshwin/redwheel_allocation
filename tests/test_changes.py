"""Changes to an object's numbers. First on the tiny supply chain of test_rtn, worked out by hand; then on
Redwheel's object.

Tiny: one item A, factory F with line L, distribution center D, customer C, four weeks. Opening: 5 of A at F,
3 ordered by C. Capacity 10 a week. C orders 4 more in week 1. Here it also has an outlook: C orders 2 in week 5
and 1 in week 6."""
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from redwheel import changes as ch, engine, rtn
from redwheel.changes import Change
from test_rtn import tiny

CAP = {"kind": "capacity", "location": "L"}
ORD = {"kind": "order", "item": "A"}
STOCK_F = {"kind": "inventory", "location": "F"}


def tiny_outlook() -> rtn.RTN:
    obj = tiny()
    out = pd.DataFrame(0.0, index=obj.resources["resource_id"], columns=[5, 6])
    out.loc["order|A|C"] = [2, 1]
    obj = replace(obj, outlook=out)
    rtn.validate(obj)
    return obj


# ---------------- each kind of change, by hand ----------------

def test_line_down_is_a_change_to_the_capacity_arrival():
    obj = tiny_outlook()
    new, rep = ch.apply(obj, [Change("arrival", CAP, "set", 0, 2, 3, "line down")])
    assert new.arrivals.loc["capacity||L"].tolist() == [10, 0, 0, 10]
    assert rtn.levels(new).loc["capacity||L"].tolist() == [0, 10, 0, 0, 10]       # capacity does not carry over
    assert rep.iloc[0][["resources", "cells", "before", "after"]].tolist() == [1, 2, 20, 0]


def test_more_demand_is_a_change_to_the_order_arrival():
    new, rep = ch.apply(tiny_outlook(), [Change("arrival", ORD, "add", 3, 2, 2, "a big order")])
    assert new.arrivals.loc["order|A|C"].tolist() == [4, 3, 0, 0]
    assert rtn.levels(new).loc["order|A|C"].tolist() == [3, 7, 10, 10, 10]          # orders wait until shipped
    assert rep.iloc[0][["resources", "cells", "before", "after"]].tolist() == [1, 1, 0, 3]


def test_a_stock_correction_is_a_change_to_the_opening_level():
    new, _ = ch.apply(tiny_outlook(), [Change("opening", STOCK_F, "add", -2, reason="count was wrong")])
    assert new.opening["inventory|A|F"] == 3
    assert rtn.levels(new).loc["inventory|A|F"].tolist() == [3, 3, 3, 3, 3]
    new, _ = ch.apply(tiny_outlook(), [Change("opening", {"kind": "inventory", "location": "D"}, "set", 7)])
    assert new.opening["inventory|A|D"] == 7


def test_scale_rounds_to_whole_units_halves_up_unless_told_not_to():
    c = [Change("arrival", CAP, "scale", 0.25, 1, 4)]
    whole, rep = ch.apply(tiny_outlook(), c)
    assert whole.arrivals.loc["capacity||L"].tolist() == [3, 3, 3, 3]              # 2.5 -> 3
    assert rep.iloc[0][["before", "after"]].tolist() == [40, 12]
    exact, _ = ch.apply(tiny_outlook(), c, whole=False)
    assert exact.arrivals.loc["capacity||L"].tolist() == [2.5, 2.5, 2.5, 2.5]


def test_a_true_half_rounds_up_even_when_floating_point_lands_just_below_it():
    """50 x 0.29 is 14.5, but in floating point it comes out as 14.499999999999998. The rule says halves up: 15.
    (Checked against exact arithmetic for every whole number to 3,000 and factor 0.01 to 3.00: no disagreement.)"""
    assert 50 * 0.29 < 14.5
    obj = tiny_outlook()
    start, _ = ch.apply(obj, [Change("arrival", CAP, "set", 50, 1, 1)])
    new, _ = ch.apply(start, [Change("arrival", CAP, "scale", 0.29, 1, 1)])
    assert new.arrivals.at["capacity||L", 1] == 15


def test_stock_arriving_from_outside_raises_stock_and_is_not_demand():
    """6 of A delivered to F in week 2: stock at F goes 5, 5, 11, 11, 11. Demand is arrivals onto orders only,
    so the position's demand does not move."""
    obj = tiny_outlook()
    new, rep = ch.apply(obj, [Change("arrival", STOCK_F, "add", 6, 2, 2, "inbound delivery")])
    assert rtn.levels(new).loc["inventory|A|F"].tolist() == [5, 5, 11, 11, 11]
    position = {"A": {"inventory|A|F": 1, "inventory|A|D": 1, "order|A|C": -1}}
    assert rtn.order_arrivals(new, position).loc["A"].tolist() == rtn.order_arrivals(obj, position).loc["A"].tolist() \
        == [4, 0, 0, 0, 2, 1]
    assert "can change only on order resources" in ch.check(obj, [Change("arrival", STOCK_F, "add", 6, 5, 5)])[0]


def test_a_change_can_reach_into_the_outlook_and_the_target_moves_with_it():
    """Demand doubles from week 4 to 6. Weeks 5 and 6 are after the plan: nothing is decided there, but a target
    of two weeks of supply at week 4 reads them, so it goes from 2 + 1 = 3 to 4 + 2 = 6."""
    obj = tiny_outlook()
    new, rep = ch.apply(obj, [Change("arrival", ORD, "scale", 2, 4, 6, "forecast revised")])
    assert new.arrivals.loc["order|A|C"].tolist() == [4, 0, 0, 0]                  # week 4 was 0 and stays 0
    assert new.outlook.loc["order|A|C"].tolist() == [4, 2]
    assert rep.iloc[0]["cells"] == 2
    position = {"A": {"inventory|A|F": 1, "inventory|A|D": 1, "order|A|C": -1}}
    two_weeks = pd.DataFrame(2, index=["A"], columns=range(1, 5))
    target = lambda o: engine.forward_sum(rtn.order_arrivals(o, position), two_weeks).loc["A"].tolist()
    assert rtn.order_arrivals(new, position).loc["A"].tolist() == [4, 0, 0, 0, 4, 2]
    assert target(obj) == [0, 0, 2, 3] and target(new) == [0, 0, 4, 6]


def test_changes_apply_in_order():
    new, rep = ch.apply(tiny_outlook(), [Change("arrival", CAP, "set", 8, 1, 4), Change("arrival", CAP, "scale", 0.5, 1, 2)])
    assert new.arrivals.loc["capacity||L"].tolist() == [4, 4, 8, 8]
    assert rep["before"].tolist() == [40, 16] and rep["after"].tolist() == [32, 8]


def test_the_object_passed_in_is_never_modified_and_no_changes_gives_the_same_object():
    obj = tiny_outlook()
    before = (obj.opening.copy(), obj.arrivals.copy(), obj.outlook.copy())
    ch.apply(obj, [Change("arrival", CAP, "set", 0, 1, 4), Change("opening", STOCK_F, "set", 0),
                   Change("arrival", ORD, "add", 9, 5, 6)])
    assert obj.opening.equals(before[0]) and obj.arrivals.equals(before[1]) and obj.outlook.equals(before[2])
    same, rep = ch.apply(obj, [])
    assert same.opening.equals(obj.opening) and same.arrivals.equals(obj.arrivals) and same.outlook.equals(obj.outlook)
    assert len(rep) == 0


def test_resources_can_be_selected_on_their_item_and_location_descriptions():
    obj = tiny_outlook()
    obj = replace(obj, items=obj.items.assign(family="bikes"),
                  locations=obj.locations.assign(region=["west", "west", "east", None, "east"]))
    assert ch.selected(obj, {"kind": "inventory", "family": "bikes"})[0] == ["inventory|A|F", "inventory|A|D", "inventory|A|F>D"]
    assert ch.selected(obj, {"kind": "inventory", "region": "east"})[0] == ["inventory|A|D"]
    assert ch.selected(obj, {"kind": "inventory", "location": ["F", "D"]})[0] == ["inventory|A|F", "inventory|A|D"]
    assert ch.selected(obj, {"kind": "capacity", "family": "bikes"}) == ([], ["the selection matches no resource"])
    clash = replace(obj, items=obj.items.assign(region="x"))
    assert "ambiguous" in ch.selected(clash, {"kind": "order", "region": "east"})[1][0]


# ---------------- every rule that refuses a change ----------------

REFUSED = {
    "field must be one of": Change("delay", CAP, "set", 1, 1, 2),
    "op must be one of": Change("arrival", CAP, "halve", 1, 1, 2),
    "value must be a number": Change("arrival", CAP, "set", "none", 1, 2),
    "a set value cannot be negative": Change("arrival", CAP, "set", -1, 1, 2),
    "a scale value cannot be negative": Change("arrival", CAP, "scale", -0.5, 1, 2),
    "a set value must be a whole number": Change("arrival", CAP, "set", 2.5, 1, 2),
    "the selection is empty": Change("arrival", {}, "set", 0, 1, 2),
    "must name one kind": Change("arrival", {"location": "L"}, "set", 0, 1, 2),
    "unknown column": Change("arrival", {"kind": "capacity", "colour": "red"}, "set", 0, 1, 2),
    "matches no resource": Change("arrival", {"kind": "capacity", "location": "F"}, "set", 0, 1, 2),
    "an opening level has no weeks": Change("opening", STOCK_F, "set", 1, 1, 2),
    "capacity has no opening level": Change("opening", CAP, "set", 5),
    "needs a first and a last week": Change("arrival", CAP, "set", 0, 2),
    "weeks must satisfy": Change("arrival", ORD, "add", 1, 3, 2),
    "weeks must satisfy 1 <= first <= last <= 6": Change("arrival", ORD, "add", 1, 5, 7),
    "can change only on order resources": Change("arrival", CAP, "set", 0, 3, 5),
    "would go below zero": Change("arrival", ORD, "add", -1, 1, 2),
    "changes no number": Change("arrival", CAP, "set", 10, 1, 4),
}


@pytest.mark.parametrize("message", REFUSED)
def test_refused(message):
    obj = tiny_outlook()
    problems = ch.check(obj, [REFUSED[message]])
    assert len(problems) == 1 and message in problems[0], problems
    with pytest.raises(ValueError, match="change 1"):
        ch.apply(obj, [REFUSED[message]])


def test_every_problem_is_reported_and_a_later_change_sees_only_the_ones_applied():
    bad = [Change("arrival", CAP, "set", 0, 1, 4), Change("arrival", CAP, "set", 0, 1, 4),      # 2nd changes nothing
           Change("opening", CAP, "set", 1), Change("arrival", ORD, "scale", 2, 1, 1)]
    problems = ch.check(tiny_outlook(), bad)
    assert [p.split(" ")[1] for p in problems] == ["2", "3"]
    assert "changes no number" in problems[0] and "capacity has no opening level" in problems[1]


def test_without_an_outlook_the_plan_weeks_are_the_only_weeks():
    assert "weeks must satisfy 1 <= first <= last <= 4" in ch.check(tiny(), [Change("arrival", ORD, "add", 1, 4, 5)])[0]
    new, _ = ch.apply(tiny(), [Change("arrival", ORD, "add", 1, 4, 4)])
    assert new.outlook is None and new.arrivals.loc["order|A|C"].tolist() == [4, 0, 0, 1]


# ---------------- Redwheel's object ----------------

def test_redwheel_outlook_is_the_forecast_after_the_plan(obj, m):
    """Weeks 122-156, cell by cell against the forecast file; nothing on resources that are not orders."""
    H = len(obj.weeks)
    assert list(obj.outlook.columns) == list(range(H + 1, 157))
    cust = m["dim_location"].dropna(subset=["channel"]).set_index("channel")["location_id"]
    t = m["dim_week"].set_index("week_start")["week_idx"]
    f = m["fact_forecast"].assign(t=m["fact_forecast"]["week_start"].map(t))
    f = f[f["t"] > H]
    for (sku, channel, week), units in f.groupby(["sku", "channel", "t"])["forecast_units"].sum().items():
        assert obj.outlook.at[f"order|{sku}|{cust[channel]}", week] == units
    orders = (obj.resources["kind"] == "order").to_numpy()
    assert obj.outlook[~orders].values.sum() == 0
    assert obj.outlook.values.sum() == f["forecast_units"].sum() == 36_177


def only_these_differ(obj, new, opening=0, arrivals=0, outlook=0):
    assert int((new.opening != obj.opening).sum()) == opening
    assert int((new.arrivals.values != obj.arrivals.values).sum()) == arrivals
    assert int((new.outlook.values != obj.outlook.values).sum()) == outlook


def test_redwheel_line_down_touches_three_numbers(obj):
    """MTB carbon line down for the three weeks from 1 Mar 2027 (weeks 26-28): 3 x 375 = 1,125 of capacity."""
    c = Change("arrival", {"kind": "capacity", "location": "RENO/mtb-carbon"}, "set", 0, 26, 28, "line down")
    new, rep = ch.apply(obj, [c])
    assert new.arrivals.loc["capacity||RENO/mtb-carbon", 25:29].tolist() == [375, 0, 0, 0, 375]
    assert rep.iloc[0][["resources", "cells", "before", "after"]].tolist() == [1, 3, 1125, 0]
    only_these_differ(obj, new, arrivals=3)


def test_redwheel_demand_up_touches_thirteen_numbers(obj):
    """RW-4418 dealer forecast up 30% for 4 Jan - 29 Mar 2027 (weeks 18-30). One week is 65: 84.5 rounds up to 85."""
    c = Change("arrival", {"kind": "order", "item": "RW-4418", "channel": "dealer"}, "scale", 1.3, 18, 30, "revised")
    new, rep = ch.apply(obj, [c])
    assert obj.arrivals.loc["order|RW-4418|DEALERS", 18:30].tolist() == [37, 38, 38, 38, 39, 39, 39, 40, 64, 65, 66, 66, 67]
    assert new.arrivals.loc["order|RW-4418|DEALERS", 18:30].tolist() == [48, 49, 49, 49, 51, 51, 51, 52, 83, 85, 86, 86, 87]
    assert rep.iloc[0][["resources", "cells", "before", "after"]].tolist() == [1, 13, 636, 827]
    only_these_differ(obj, new, arrivals=13)


def test_redwheel_stock_correction_touches_one_number(obj):
    c = Change("opening", {"kind": "inventory", "item": "RW-9324", "location": "RENO"}, "add", -200, reason="count")
    new, rep = ch.apply(obj, [c])
    assert (obj.opening["inventory|RW-9324|RENO"], new.opening["inventory|RW-9324|RENO"]) == (1250, 1050)
    only_these_differ(obj, new, opening=1)


def test_redwheel_selection_by_line_and_channel(obj):
    assert ch.selected(obj, {"kind": "order", "line_id": "mtb-carbon", "channel": "dtc"})[0] == \
        ["order|RW-4418|WEB", "order|RW-6416|WEB", "order|RW-9304|WEB"]
    assert len(ch.selected(obj, {"kind": "capacity"})[0]) == 4
    assert ch.check(obj, [Change("arrival", {"kind": "capacity", "location": "RENO/mtb-carbon"}, "set", 0, 120, 122)])


def test_redwheel_changes_keep_whole_numbers_whole(obj):
    new, _ = ch.apply(obj, [Change("arrival", {"kind": "order", "class": "road"}, "scale", 1.07, 1, 156)])
    assert new.arrivals.dtypes.unique().tolist() == obj.arrivals.dtypes.unique().tolist()
    assert new.outlook.dtypes.unique().tolist() == obj.outlook.dtypes.unique().tolist()


# ---------------- against a second implementation, on random changes ----------------

def reference(obj, changes):
    """The same rules written a different way: one resource and one number at a time, no tables."""
    import math
    res = obj.resources.set_index("resource_id")
    items, locs = obj.items.set_index("item"), obj.locations.set_index("location_id")
    A = rtn.arrivals_all(obj)
    opening = {r: float(v) for r, v in obj.opening.items()}
    arrival = {(r, int(t)): float(A.at[r, t]) for r in A.index for t in A.columns}
    for c in changes:
        for r in res.index:
            row, match = res.loc[r], True
            for k, v in c.select.items():
                wanted = v if isinstance(v, list) else [v]
                if k == "resource_id":
                    have = r
                elif k in ("kind", "item", "location"):
                    have = row[k]
                elif k in items.columns:
                    have = items.at[row["item"], k] if row["item"] in items.index else None
                else:
                    have = locs.at[row["location"], k]
                match = match and have in wanted
            if not match:
                continue
            for t in ([None] if c.field == "opening" else range(c.from_t, c.to_t + 1)):
                old = opening[r] if t is None else arrival[(r, t)]
                new = c.value if c.op == "set" else old + c.value if c.op == "add" else math.floor(old * c.value + 0.5 + 1e-9)
                if t is None:
                    opening[r] = float(new)
                else:
                    arrival[(r, t)] = float(new)
    return opening, arrival


def random_change(rng, obj):
    H, T = len(obj.weeks), int(obj.outlook.columns.max())
    sku = obj.items.sample(1, random_state=int(rng.integers(1e9))).iloc[0]
    kind = rng.choice(["order", "capacity", "inventory"])
    if kind == "order":
        select = [{"kind": "order", "item": sku["item"]}, {"kind": "order", "line_id": sku["line_id"], "channel": "dtc"},
                  {"kind": "order", "class": sku["class"], "location": ["DEALERS", "COMMERCIAL"]},
                  {"kind": "order", "target_group": sku["target_group"]}][rng.integers(4)]
        last = T
    elif kind == "capacity":
        select = [{"kind": "capacity", "location": "RENO/" + sku["line_id"]}, {"kind": "capacity", "parent": "RENO"}][rng.integers(2)]
        last = H
    else:
        select = [{"kind": "inventory", "item": sku["item"], "location": "RENO"}, {"kind": "inventory", "ours": True, "size": sku["size"]},
                  {"kind": "inventory", "location_class": "distribution_center"}][rng.integers(3)]
        last = H
    op = rng.choice(["set", "add", "scale"])
    value = float(rng.integers(0, 400)) if op == "set" else float(rng.integers(-30, 200)) if op == "add" else \
        float(rng.choice([0, 0.25, 0.5, 0.7, 0.9, 1.1, 1.3, 1.45, 2]))
    if kind != "capacity" and rng.random() < 0.3:
        return Change("opening", select, op, value)
    first = int(rng.integers(1, last + 1))
    return Change("arrival", select, op, value, first, int(rng.integers(first, min(last, first + 30) + 1)))


def test_random_changes_match_a_second_implementation(obj):
    rng = np.random.default_rng(20261115)
    applied = 0
    for _ in range(120):
        changes = [random_change(rng, obj) for _ in range(int(rng.integers(1, 4)))]
        if ch.check(obj, changes):                       # refused lists are covered by the rule tests above
            continue
        new, rep = ch.apply(obj, changes)
        opening, arrival = reference(obj, changes)
        A = rtn.arrivals_all(new)
        assert new.opening.astype(float).to_dict() == opening
        assert {(r, int(t)): float(A.at[r, t]) for r in A.index for t in A.columns} == arrival
        applied += 1
    assert applied >= 40                                 # enough of the random lists were valid to mean something
