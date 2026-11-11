"""The generic object on a supply chain small enough to compute by hand.

One item A. Factory F with line L. Distribution center D, 2 weeks from F. One customer C.
Opening: 5 of A at F, 3 of A ordered by C. Line capacity 10 a week. C orders 4 more in week 1.
Four weeks.
"""
import numpy as np
import pandas as pd
import pytest

from redwheel import rtn

H = 4


def tiny(route_delay: int = 2) -> rtn.RTN:
    items = pd.DataFrame({"item": ["A"]})
    locations = pd.DataFrame({
        "location_id": ["F", "L", "D", "F>D", "C"],
        "location_class": ["factory", "production_line", "distribution_center", "in_transit", "customer"],
        "parent": [None, "F", None, None, None],
        "ours": [True, False, True, True, False],
    })
    weeks = pd.DataFrame({"t": range(1, H + 1), "week_start": pd.date_range("2026-01-05", periods=H, freq="7D")})
    routing = pd.DataFrame({"item": ["A"], "line": ["L"], "output": ["F"], "capacity_per_unit": [1], "delay": [0]})
    routes = pd.DataFrame({"origin": ["F", "F", "D"], "destination": ["D", "C", "C"], "delay": [route_delay, 0, 0]})
    resources = rtn.generate_resources(items, locations)
    tasks, arrows = rtn.generate_tasks(routing, routes, items, locations)
    ids = resources["resource_id"]
    opening = pd.Series(0.0, index=ids)
    opening["inventory|A|F"], opening["order|A|C"] = 5, 3
    arrivals = pd.DataFrame(0.0, index=ids, columns=range(1, H + 1))
    arrivals.loc["capacity||L", :] = 10
    arrivals.loc["order|A|C", 1] = 4
    obj = rtn.RTN(items, locations, weeks, resources, tasks, arrows, opening, arrivals)
    rtn.validate(obj)
    return obj


def runs(obj, plan: dict) -> pd.DataFrame:
    """plan: {(task_id, week): runs}"""
    r = pd.DataFrame(0.0, index=obj.tasks["task_id"], columns=range(1, H + 1))
    for (tid, t), n in plan.items():
        r.loc[tid, t] = n
    return r


# Week 1: build 6, ship 7 from F to C, move 4 from F to D (arrives week 3).
PLAN = {("make|A|L", 1): 6, ("fulfil|A|F>C", 1): 7, ("move|A|F>D", 1): 4}


def test_structure():
    obj = tiny()
    assert list(obj.resources["resource_id"]) == [
        "inventory|A|F", "capacity||L", "inventory|A|D", "inventory|A|F>D", "order|A|C"]
    assert list(obj.tasks["task_id"]) == ["make|A|L", "move|A|F>D", "fulfil|A|F>C", "fulfil|A|D>C"]
    a = obj.arrows.set_index(["task_id", "resource_id", "delay"])["amount"]
    assert a.to_dict() == {
        ("make|A|L", "capacity||L", 0): -1, ("make|A|L", "inventory|A|F", 0): 1,
        ("move|A|F>D", "inventory|A|F", 0): -1, ("move|A|F>D", "inventory|A|F>D", 0): 1,
        ("move|A|F>D", "inventory|A|F>D", 2): -1, ("move|A|F>D", "inventory|A|D", 2): 1,
        ("fulfil|A|F>C", "inventory|A|F", 0): -1, ("fulfil|A|F>C", "order|A|C", 0): -1,
        ("fulfil|A|D>C", "inventory|A|D", 0): -1, ("fulfil|A|D>C", "order|A|C", 0): -1,
    }


def test_levels_by_hand():
    obj = tiny()
    X = rtn.levels(obj, runs(obj, PLAN))
    expected = {                      # t = 0, 1, 2, 3, 4
        "inventory|A|F":   [5, 0, 0, 0, 0],    # 5 + 6 built - 7 shipped - 4 moved
        "inventory|A|F>D": [0, 4, 4, 0, 0],    # on the road weeks 1-2, lands week 3
        "inventory|A|D":   [0, 0, 0, 4, 4],
        "order|A|C":       [3, 0, 0, 0, 0],    # 3 + 4 ordered - 7 shipped
        "capacity||L":     [0, 4, 10, 10, 10], # 10 - 6 built in week 1, unused capacity not carried
    }
    for r, row in expected.items():
        assert list(X.loc[r]) == row, r


def test_net_position_by_hand():
    obj = tiny()
    npos = rtn.net_position(obj, rtn.levels(obj, runs(obj, PLAN)))
    # opening 5 - 3 = 2; then 2 + 6 built - 4 ordered = 4; moving and shipping change nothing
    assert list(npos.loc["A"]) == [2, 4, 4, 4, 4]


def test_no_runs_only_arrivals_move_levels():
    obj = tiny()
    X = rtn.levels(obj)
    assert list(X.loc["inventory|A|F"]) == [5] * (H + 1)
    assert list(X.loc["order|A|C"]) == [3, 7, 7, 7, 7]
    assert list(X.loc["capacity||L"]) == [0, 10, 10, 10, 10]


def test_arrival_after_horizon_stays_in_transit():
    obj = tiny()
    X = rtn.levels(obj, runs(obj, {("move|A|F>D", 4): 2}))
    assert X.loc["inventory|A|F>D", 4] == 2 and X.loc["inventory|A|D", 4] == 0
    # still ours while on the road: 2 opening + 0 built - 4 ordered = -2, same as with no move
    assert rtn.net_position(obj, X).loc["A", 4] == -2
    assert rtn.net_position(obj, rtn.levels(obj)).loc["A", 4] == -2


def test_zero_delay_route_passes_through_transit():
    obj = tiny(route_delay=0)
    X = rtn.levels(obj, runs(obj, {("move|A|F>D", 1): 2}))
    assert list(X.loc["inventory|A|F>D"]) == [0] * (H + 1)
    assert X.loc["inventory|A|D", 1] == 2


def test_graph_view():
    g = rtn.to_networkx(tiny())
    assert g.number_of_nodes() == 5 + 4 and g.number_of_edges() == 10
    assert g.has_edge("capacity||L", "make|A|L") and g.has_edge("make|A|L", "inventory|A|F")
    assert g.has_edge("order|A|C", "fulfil|A|F>C")          # fulfil takes from the order
    assert g.has_edge("move|A|F>D", "inventory|A|F>D") and g.has_edge("inventory|A|F>D", "move|A|F>D")


def capacity_at_customer(o):
    o.resources.loc[o.resources["kind"] == "capacity", "location"] = "C"


def arrow_to_nowhere(o):
    o.arrows.loc[0, "resource_id"] = "inventory|A|nowhere"


def negative_delay(o):
    o.arrows.loc[0, "delay"] = -1


def negative_opening(o):
    o.opening["inventory|A|F"] = -1


def capacity_opening(o):
    o.opening["capacity||L"] = 5


def capacity_carries(o):
    o.resources["carry"] = True


@pytest.mark.parametrize("break_it, message", [
    (capacity_at_customer, "not allowed"),
    (arrow_to_nowhere, "unknown resource"),
    (negative_delay, "delay"),
    (negative_opening, "negative opening"),
    (capacity_opening, "capacity has no opening"),
    (capacity_carries, "carry"),
])
def test_validate_catches(break_it, message):
    obj = tiny()
    rtn.validate(obj)              # valid before
    break_it(obj)
    with pytest.raises(ValueError, match=message):
        rtn.validate(obj)


def test_levels_rejects_bad_runs():
    obj = tiny()
    with pytest.raises(ValueError, match="negative"):
        rtn.levels(obj, runs(obj, {("make|A|L", 1): -1}))
    with pytest.raises(ValueError, match="unknown task"):
        rtn.levels(obj, pd.DataFrame({1: [1.0]}, index=["make|A|nowhere"]))
    assert np.isfinite(rtn.levels(obj).values).all()
