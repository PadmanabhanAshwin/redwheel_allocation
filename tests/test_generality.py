"""How far the generic object carries, beyond what Redwheel's data has: a component and a supplier.

Redwheel has no bill of material and no purchasing, so nothing else tests this. A small network worked out by hand:
bike A is built on line L from one frame F each (a joint input: a make needs line capacity AND a frame), and frames
are bought with a two-week lead time. It needs no new kind of resource, task or edge, and no change to the solver:
one more arrow on make, and a buy task. What does not carry yet is whole-unit rounding, which is written for tasks
that use one unit of a line."""
import numpy as np
import pandas as pd
import pytest

from redwheel import engine, rtn

H = 6


def bike_from_a_frame() -> rtn.RTN:
    """Line L builds 10 a week. 3 frames on hand, none on order. Customers order 4 bikes every week."""
    items = pd.DataFrame({"item": ["A", "F"]})
    locations = pd.DataFrame({"location_id": ["P", "L", "C"], "location_class": ["factory", "production_line", "customer"],
                              "parent": [None, "P", None], "ours": [True, False, False]})
    weeks = pd.DataFrame({"t": range(1, H + 1), "week_start": pd.date_range("2026-01-05", periods=H, freq="7D")})
    res = rtn.generate_resources(items, locations)
    routing = pd.DataFrame({"item": ["A"], "line": ["L"], "output": ["P"], "capacity_per_unit": [1], "delay": [0]})
    routes = pd.DataFrame({"origin": ["P"], "destination": ["C"], "delay": [0]})
    tasks, arrows = rtn.generate_tasks(routing, routes, items, locations)
    arrows = pd.concat([arrows, pd.DataFrame([("make|A|L", "inventory|F|P", -1, 0),        # the bill of material
                                              ("buy|F|SUP", "inventory|F|P", 1, 2)],        # the supplier, 2 weeks
                                             columns=arrows.columns)], ignore_index=True)
    tasks = pd.concat([tasks, pd.DataFrame([("buy|F|SUP", "buy", "F")], columns=tasks.columns)], ignore_index=True)
    opening = pd.Series(0.0, index=res["resource_id"])
    opening["inventory|F|P"] = 3
    arrivals = pd.DataFrame(0.0, index=res["resource_id"], columns=range(1, H + 1))
    arrivals.loc["capacity||L"] = 10
    arrivals.loc["order|A|C"] = 4
    obj = rtn.RTN(items, locations, weeks, res, tasks, arrows, opening, arrivals)
    rtn.validate(obj)
    return obj


def plan(obj):
    """Decide builds and purchases so that no bike is owed (target: net position of A never below zero)."""
    never_owe = pd.DataFrame([[0.0] * H], index=["A"], columns=range(1, H + 1))
    return engine.decide(obj, ["make|A|L", "buy|F|SUP"], never_owe, pd.Series({"A": 4.0}), pd.Series({"A": "L"}),
                         positions={"A": {"inventory|A|P": 1.0, "order|A|C": -1.0}}, w_run=1e-6)


def test_a_bike_built_from_a_bought_frame_plans_with_no_new_code():
    """By hand. Week 1: only 3 frames, so 3 bikes against 4 ordered: 1 owed. Frames bought in week 1 arrive in week 3,
    so week 2 builds nothing: 5 owed. Week 3: 9 frames arrive, 9 bikes clear the 5 owed and the week's 4. After that,
    4 frames in, 4 bikes out. Frames bought in weeks 5 and 6 would arrive after the plan, so none are bought."""
    obj = bike_from_a_frame()
    p = plan(obj)
    assert p.runs.loc["make|A|L"].round(6).tolist() == [3, 0, 9, 4, 4, 4]
    assert p.runs.loc["buy|F|SUP"].round(6).tolist() == [9, 4, 4, 4, 0, 0]
    X = rtn.levels(obj, p.runs)
    assert X.loc["inventory|F|P"].round(6).tolist() == [3, 0, 0, 0, 0, 0, 0]                 # every frame is used
    assert (X.loc["inventory|A|P"] - X.loc["order|A|C"]).round(6).tolist() == [0, -1, -5, 0, 0, 0, 0]
    assert X.values.min() >= -1e-9                                                           # no level below zero
    assert np.abs(X.values - p.levels.values).max() < 1e-9                                   # the object's own equation


def test_the_frame_is_what_holds_the_bikes_back():
    """With 9 frames on hand at the start, nothing waits: the line (10 a week) was never the limit."""
    obj = bike_from_a_frame()
    obj.opening["inventory|F|P"] = 9
    p = plan(obj)
    net = rtn.levels(obj, p.runs)
    assert (net.loc["inventory|A|P"] - net.loc["order|A|C"]).round(6).min() == 0
    assert p.runs.loc["make|A|L"].round(6).tolist() == [4, 4, 4, 4, 4, 4]


def test_whole_unit_rounding_does_not_cover_a_purchase_yet():
    """Known limit (WORKING_NOTES O26, SOLVER_NOTES 5e): rounding is written for tasks that use one unit of a line."""
    obj = bike_from_a_frame()
    with pytest.raises(ValueError, match="must draw on a capacity resource"):
        engine.round_runs(obj, plan(obj).runs)
