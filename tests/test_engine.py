"""The LP on the RTN object: by hand on the tiny chain, then the Redwheel build plan."""
import numpy as np
import pandas as pd
import pytest

from redwheel import aux_fns, engine, rtn
from test_rtn import tiny

# ---------------- by hand ----------------
# Tiny chain: opening net position 2, 4 more ordered in week 1, line capacity 10 a week.


def decide_tiny(target, build_delay=0):
    obj = tiny(build_delay=build_delay)
    tgt = pd.DataFrame([target], index=["A"], columns=[1, 2, 3, 4], dtype=float)
    return obj, engine.decide(obj, ["make|A|L"], tgt, pd.Series({"A": 1.0}), pd.Series({"A": "L"}))


def test_reachable_target_builds_exactly_enough():
    _, p = decide_tiny([6, 6, 6, 6])
    assert p.runs.loc["make|A|L"].round(9).tolist() == [8, 0, 0, 0]     # 2 + 8 - 4 = 6
    assert p.short.values.max() == pytest.approx(0)


def test_unreachable_target_builds_flat_out_then_stops():
    _, p = decide_tiny([20, 20, 20, 20])
    assert p.runs.loc["make|A|L"].round(9).tolist() == [10, 10, 2, 0]   # 8, 18, 20, 20
    assert p.short.loc["A"].round(9).tolist() == [12, 2, 0, 0]


def test_build_delay_lands_a_week_later():
    """Build takes 1 week: week 1 cannot be helped (short 2); a week-1 build of 8 covers week 2."""
    obj, p = decide_tiny([0, 6, 6, 6], build_delay=1)
    assert p.runs.loc["make|A|L", [1, 2, 3]].round(9).tolist() == [8, 0, 0]
    assert p.short.loc["A"].round(9).tolist() == [2, 0, 0, 0]
    X = rtn.levels(obj, p.runs)
    assert list(X.loc["inventory|A|F"]) == [5, 5, 13, 13, 13]           # lands in week 2
    assert np.abs(X.values - p.levels.values).max() < 1e-9


def test_forward_sum():
    demand = pd.DataFrame([[1, 2, 3, 4, 5]], index=["A"], columns=[1, 2, 3, 4, 5])
    n = pd.DataFrame([[2, 2, 1]], index=["A"], columns=[1, 2, 3])
    assert engine.forward_sum(demand, n).loc["A"].tolist() == [5, 7, 4]   # 2+3, 3+4, 4


# ---------------- Redwheel ----------------

@pytest.fixture(scope="module")
def plan(obj, m):
    demand = aux_fns.forecast_by_item(m)
    tgt = engine.forward_sum(demand, aux_fns.target_wos(m, obj.weeks))
    free = list(obj.tasks.loc[obj.tasks["kind"] == "make", "task_id"])
    line = m["dim_sku"].set_index("sku")["line_id"]
    p = engine.decide(obj, free, tgt, demand.loc[:, 1:121].mean(axis=1), line)
    return p, rtn.levels(obj, p.runs), tgt, line


def test_closure(plan):
    p, X, _, _ = plan
    assert np.abs(X.values - p.levels.values).max() < 1e-6


def test_capacity_never_exceeded_and_no_level_below_zero(plan):
    _, X, _, _ = plan
    assert X.values.min() > -1e-6


def test_shortfall_is_exactly_the_gap_to_target(obj, plan):
    p, X, tgt, _ = plan
    net = rtn.net_position(obj, X).loc[tgt.index, 1:]
    assert np.abs(p.short.values - np.maximum(0, tgt.values - net.values)).max() < 1e-6


def test_below_target_only_when_line_was_full_every_week_until_then(obj, plan):
    """The proof: no plan could have done better on any missed target."""
    _, X, tgt, line = plan
    net = rtn.net_position(obj, X).loc[tgt.index, 1:]
    below = net < tgt - 1e-6
    full_so_far = (X[X.index.str.startswith("capacity|")].loc[:, 1:] < 1e-6).cumprod(axis=1).astype(bool)
    assert below.values.sum() > 0                                        # not vacuous
    for s in below.index:
        for t in below.columns[below.loc[s]]:
            assert full_so_far.at[f"capacity||RENO/{line[s]}", t], (s, t)


def test_targets_met_from_known_weeks(obj, plan):
    _, X, tgt, _ = plan
    net = rtn.net_position(obj, X).loc[tgt.index, 1:]
    below = net < tgt - 1e-6
    last_below = below.apply(lambda r: r[r].index.max() if r.any() else 0, axis=1)
    assert last_below[["RW-4418", "RW-6416", "RW-9304"]].max() == 52    # mtb-carbon: met from 2027-09-06
    assert last_below[["RW-1378", "RW-2984", "RW-3980"]].max() == 47    # road-carbon: July 2027 spike
    assert last_below["RW-9324"] == 0


# ---------------- whole bikes ----------------

def two_skus_one_line(capacity=3, H=3):
    """Items A and B share line L (capacity per week), both shipped from factory F to customer C."""
    items = pd.DataFrame({"item": ["A", "B"]})
    locations = pd.DataFrame({"location_id": ["F", "L", "C"],
                              "location_class": ["factory", "production_line", "customer"],
                              "parent": [None, "F", None], "ours": [True, False, False]})
    weeks = pd.DataFrame({"t": range(1, H + 1), "week_start": pd.date_range("2026-01-05", periods=H, freq="7D")})
    routing = pd.DataFrame({"item": ["A", "B"], "line": "L", "output": "F", "capacity_per_unit": 1, "delay": 0})
    routes = pd.DataFrame({"origin": ["F"], "destination": ["C"], "delay": [0]})
    res = rtn.generate_resources(items, locations)
    tasks, arrows = rtn.generate_tasks(routing, routes, items, locations)
    arrivals = pd.DataFrame(0.0, index=res["resource_id"], columns=range(1, H + 1))
    arrivals.loc["capacity||L"] = capacity
    return rtn.RTN(items, locations, weeks, res, tasks, arrows, pd.Series(0.0, index=res["resource_id"]), arrivals)


def lp_runs(a, b):
    return pd.DataFrame([a, b], index=["make|A|L", "make|B|L"], columns=[1, 2, 3], dtype=float)


def test_round_up_when_capacity_allows():
    R = engine.round_runs(two_skus_one_line(), lp_runs([0.2, 0.2, 0.2], [0, 0, 0]))
    assert R.loc["make|A|L"].tolist() == [1, 0, 0]          # cumulative 0.2, 0.4, 0.6 -> 1, 1, 1


def test_round_takes_back_when_line_is_full():
    R = engine.round_runs(two_skus_one_line(), lp_runs([1.5, 1.5, 0], [1.5, 1.5, 0]))
    assert R.sum().tolist() == [3, 3, 0]                    # never above capacity 3
    assert R.loc["make|A|L"].tolist() == [1, 2, 0]          # week 1: 2 + 2 > 3, one unit back from A
    assert R.loc["make|B|L"].tolist() == [2, 1, 0]          # week 2: both back to cumulative 3


@pytest.fixture(scope="module")
def rounded(obj, plan):
    p, _, _, _ = plan
    R = engine.round_runs(obj, p.runs)
    return R, rtn.levels(obj, R)


def test_rounded_is_whole_and_within_capacity(rounded):
    R, X = rounded
    assert (R.values == np.round(R.values)).all() and R.values.min() >= 0
    assert X.values.min() >= 0                              # capacity level >= 0 every line, every week


def test_rounded_stays_within_one_bike_of_lp(plan, rounded):
    p, _, _, _ = plan
    R, _ = rounded
    gap = R.cumsum(axis=1) - p.runs.cumsum(axis=1)
    assert gap.values.min() > -1 and gap.values.max() < 1


def test_rounding_adds_no_missed_targets_and_proof_holds(obj, plan, rounded):
    p, X_lp, tgt, line = plan
    _, X = rounded
    net = rtn.net_position(obj, X).loc[tgt.index, 1:]
    net_lp = rtn.net_position(obj, X_lp).loc[tgt.index, 1:]
    below, below_lp = net < tgt - 1e-9, net_lp < tgt - 1e-6
    assert not (below & ~below_lp).values.any()
    full_so_far = (X[X.index.str.startswith("capacity|")].loc[:, 1:] < 0.5).cumprod(axis=1).astype(bool)
    for s in below.index:
        for t in below.columns[below.loc[s]]:
            assert full_so_far.at[f"capacity||RENO/{line[s]}", t], (s, t)


# ---------------- positions and transfers, by hand ----------------
# Tiny chain, customer served from the DC only. Opening: 5 at the factory, 0 at the DC, 3 ordered; 4 more
# ordered in week 1. So the DC position (DC stock - orders) is -7 until stock arrives.

def decide_dc(route_delay, target, w_run=1e-6):
    obj = tiny(route_delay=route_delay)
    pos = {"A@D": {"inventory|A|D": 1.0, "order|A|C": -1.0}}
    tgt = pd.DataFrame([target], index=["A@D"], columns=[1, 2, 3, 4], dtype=float)
    p = engine.decide(obj, ["make|A|L", "move|A|F>D"], tgt, pd.Series({"A@D": 1.0}), pd.Series({"A@D": "L"}),
                      positions=pos, w_run=w_run)
    return obj, p


def test_transfer_lead_time_delays_when_stock_counts():
    """DC target 6 from week 3. Needs 13 at the DC (7 owed + 6): 5 on hand + 8 built, moved in week 1,
    arriving week 3. Weeks 1-2 cannot be helped: short 7 each."""
    obj, p = decide_dc(route_delay=2, target=[0, 0, 6, 6])
    assert p.runs.loc["make|A|L"].round(6).tolist() == [8, 0, 0, 0]
    assert p.runs.loc["move|A|F>D"].round(6).tolist() == [13, 0, 0, 0]
    assert p.short.loc["A@D"].round(6).tolist() == [7, 7, 0, 0]
    X = rtn.levels(obj, p.runs)
    assert list(X.loc["inventory|A|D"].round(6)) == [0, 0, 0, 13, 13]         # lands in week 3
    assert list(X.loc["inventory|A|F>D"].round(6)) == [0, 13, 13, 0, 0]       # in transit weeks 1-2
    assert np.abs(X.values - p.levels.values).max() < 1e-9


def test_no_transfer_lead_time_no_delay():
    """Same chain with an instant transfer: the same 8 built and 13 moved, and the target is met from week 1."""
    _, p = decide_dc(route_delay=0, target=[6, 6, 6, 6])
    assert p.runs.loc["make|A|L"].round(6).tolist() == [8, 0, 0, 0]
    assert p.runs.loc["move|A|F>D"].round(6).tolist() == [13, 0, 0, 0]
    assert p.short.loc["A@D"].round(6).max() == 0


def test_cannot_move_stock_that_is_not_there():
    """Target far above what exists: the LP may move only what the factory holds (5 + capacity 10 a week)."""
    obj, p = decide_dc(route_delay=0, target=[100, 100, 100, 100])
    X = rtn.levels(obj, p.runs)
    assert X.loc["inventory|A|F"].min() >= -1e-9
    assert p.runs.loc["move|A|F>D"].round(6).tolist() == [15, 10, 10, 10]


def test_without_a_run_cost_idle_stock_is_free():
    """Why w_run exists: factory stock is in no position here, so with w_run = 0 the LP may build bikes
    nobody needs. With it, builds stop at what the target requires."""
    _, free_builds = decide_dc(route_delay=2, target=[0, 0, 6, 6], w_run=0.0)
    _, costed = decide_dc(route_delay=2, target=[0, 0, 6, 6], w_run=1e-6)
    assert costed.runs.loc["make|A|L"].sum() == pytest.approx(8)
    assert free_builds.runs.loc["make|A|L"].sum() >= 8 - 1e-9          # may be more: nothing stops it
