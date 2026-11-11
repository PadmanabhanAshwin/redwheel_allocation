"""Scenarios: pools come from the routing rule, and the factory rolls up to all demand inside the network."""
import numpy as np
import pandas as pd
import pytest

from redwheel import aux_fns, rtn, scenarios as sc
from conftest import EXPECTED_NET0


# ---------------- pools from the routing rule ----------------

def test_base_routing_is_one_pool():
    assert sc.pools(sc.CASE_A.ship_routes) == {
        "CMH+RENO": {"stock": ["CMH", "RENO"], "customers": ["COMMERCIAL", "DEALERS", "WEB"]}}


def test_routing_b_is_two_pools_facing_their_own_demand():
    assert sc.pools(sc.CASE_B.ship_routes) == {
        "CMH": {"stock": ["CMH"], "customers": ["WEB"]},
        "RENO": {"stock": ["RENO"], "customers": ["COMMERCIAL", "DEALERS"]}}


def test_every_customer_is_served_by_exactly_one_pool():
    for case in sc.CASES.values():
        served = [c for p in sc.pools(case.ship_routes).values() for c in p["customers"]]
        assert sorted(served) == sorted(sc.CUSTOMERS)


# ---------------- pool positions on the real object ----------------

@pytest.fixture(scope="module")
def b(m):
    obj = aux_fns.build_object(m, sc.CASE_B.build_weeks, sc.CASE_B.transfer_weeks)
    pool_def = sc.pools(sc.CASE_B.ship_routes)
    return obj, pool_def, sc.positions(obj, pool_def)


def test_opening_positions_under_b(b, m):
    obj, _, pos = b
    net0 = sc.position_levels(rtn.levels(obj), pos)[0]
    inv, o = m["fact_inventory"], m["fact_orders"]
    o = o[o["open_at_snapshot"]]
    for s in m["dim_sku"]["sku"]:
        pdc = inv[(inv["location_code"] == "CMH-DC") & (inv["sku"] == s)]["on_hand"].sum()
        reno = inv[(inv["location_code"] == "RENO-FG") & (inv["sku"] == s)]["on_hand"].sum()
        web = o[(o["sku"] == s) & (o["channel"] == "dtc")]["qty"].sum()
        b2b = o[(o["sku"] == s) & (o["channel"] != "dtc")]["qty"].sum()
        assert net0[(s, "CMH")] == pdc - web
        assert net0[(s, "RENO")] == reno - b2b
    assert net0.xs("CMH", level="pool").sum() == 1_035 - 2_139
    assert net0.xs("RENO", level="pool").sum() == 1_965 - 3_852


def test_position_demand_splits_the_forecast_by_channel_served(b, m):
    _, pool_def, _ = b
    d = sc.position_demand(m, pool_def)
    total = aux_fns.forecast_by_item(m)
    assert np.allclose(d.groupby("item").sum().loc[total.index].values, total.values)       # nothing lost
    f = m["fact_forecast"]
    web = f[f["channel"] == "dtc"]["forecast_units"].sum()
    assert d.xs("CMH", level="pool").values.sum() == web


def test_the_factory_rolls_up_to_all_demand(b, m):
    """Run any builds and transfers through the object: Reno pool + PDC pool + in transit equals total net
    inventory, which equals opening + bikes landed - forecast. The rollup needs no extra construct."""
    obj, _, pos = b
    H = len(obj.weeks)
    rng = np.random.default_rng(0)
    runs = pd.DataFrame(0.0, index=obj.tasks["task_id"], columns=range(1, H + 1))
    make = obj.tasks.loc[obj.tasks["kind"] == "make", "task_id"]
    for k in make:
        cap = obj.arrivals.loc[obj.arrows[(obj.arrows["task_id"] == k) & (obj.arrows["amount"] < 0)]["resource_id"].iloc[0]]
        runs.loc[k] = np.floor(cap.values / 3 * rng.uniform(0.3, 1, H))
    X = rtn.levels(obj, runs)                                   # no transfers yet: find what may be moved
    for s in obj.items["item"]:
        reno = X.loc[f"inventory|{s}|RENO"]
        moved, plan = 0.0, []
        for t in range(1, H + 1):
            q = np.floor(0.5 * max(0.0, reno[t] - moved))
            plan.append(q)
            moved += q
        runs.loc[f"move|{s}|RENO>CMH"] = plan
    X = rtn.levels(obj, runs)
    assert X.values.min() >= 0
    assert runs[runs.index.str.startswith("move|")].values.sum() > 10_000        # transfers really happen
    pools_net = sc.position_levels(X, pos).groupby("item").sum()
    transit = X[X.index.str.endswith("|RENO>CMH")]
    transit.index = transit.index.str.split("|").str[1]
    total = rtn.net_position(obj, X)                              # the base case's measure
    assert np.abs((pools_net + transit.loc[pools_net.index]).values - total.loc[pools_net.index].values).max() == 0
    # and total net = opening + bikes landed (built one week earlier) - forecast
    built = runs.loc[make].copy()
    built.index = built.index.str.split("|").str[1]
    landed = built.shift(sc.CASE_B.build_weeks, axis=1, fill_value=0).cumsum(axis=1)
    demand = aux_fns.forecast_by_item(m).loc[:, 1:H].cumsum(axis=1)
    expected = (landed - demand).add(pd.Series(EXPECTED_NET0), axis=0)
    assert np.abs(total.loc[expected.index, 1:].values - expected.values).max() == 0


# ---------------- the two scenarios, run ----------------

@pytest.fixture(scope="module")
def A():
    return sc.run_case(sc.CASE_A)


@pytest.fixture(scope="module")
def B():
    return sc.run_case(sc.CASE_B)


def test_scenario_a_through_the_case_path_is_the_base_case(A):
    base = aux_fns.run_plan()
    assert (A["builds"].values == base["builds"].values).all()
    assert np.abs(A["net"].droplevel("pool").loc[base["net"].index].values - base["net"].values).max() == 0
    assert int((~A["at_target"]).values.sum()) == 278
    assert sc.scorecard(A)["Bikes built"] == 94_429


def test_new_shipping_projection_equals_the_base_one_when_nothing_is_transferred(A):
    base = aux_fns.run_plan()["flows"]
    new = A["flows"]
    for k in ("on_hand", "open_orders"):
        assert np.abs(new[k].droplevel("pool").loc[base[k].index].values - base[k].values).max() < 1e-9
    assert np.abs(new["shipped"].droplevel("pool").loc[base["shipped"].index].values - base["shipped"].values).max() < 1e-9


def test_shipping_never_uses_stock_the_plan_transfers_out_later():
    """Stock 10 now, 4 after a planned transfer next week, 10 owed: only 4 may ship now."""
    stock = pd.DataFrame([[10.0, 10.0, 4.0, 4.0]], columns=[0, 1, 2, 3])
    owed = pd.DataFrame([[10.0, 10.0, 10.0, 10.0]], columns=[0, 1, 2, 3])
    f = sc.ship_from_levels(stock, owed)
    assert f["shipped"].iloc[0].tolist() == [4, 0, 0]
    assert f["on_hand"].iloc[0].tolist() == [10, 6, 0, 0] and f["open_orders"].iloc[0].tolist() == [10, 6, 6, 6]


@pytest.mark.parametrize("which", ["A", "B"])
def test_every_check_passes(which, A, B):
    c = sc.checks({"A": A, "B": B}[which])
    assert len(c) == 8 and c["pass"].all(), c[~c["pass"]].to_string()


def test_scenario_b_is_whole_and_close_to_the_lp(B):
    lp = B["lp"].runs
    assert (B["runs"].values == np.round(B["runs"].values)).all()
    gb = B["builds"].cumsum(axis=1) - lp.loc[B["builds"].index].cumsum(axis=1)
    gm = B["moves"].cumsum(axis=1) - lp.loc[B["moves"].index].cumsum(axis=1)
    assert gb.values.min() > -1 and gb.values.max() < 1
    assert gm.values.max() <= 1e-9 and gm.values.min() >= -1 - 1e-9          # transfers never ahead of the LP


def test_lead_times_cost_what_they_should(A, B):
    """B has a 1-week build time and a 1-week transfer: targets are held later than in A, never earlier,
    and before the horizon end B has built more, to fill the pipeline."""
    ha, hb = sc.held_by_line(A).max(axis=1), sc.held_by_line(B).max(axis=1)
    assert (hb > ha).all()
    assert sc.scorecard(B)["On-time fill rate"] < sc.scorecard(A)["On-time fill rate"]
    assert B["builds"].loc[:, :119].values.sum() > A["builds"].loc[:, :119].values.sum()
    assert sc.scorecard(B)["Average bikes in transit"] > 0 == sc.scorecard(A)["Average bikes in transit"]


def test_known_end_of_horizon_effect_in_b(B):
    """Documented limitation (working notes O14): a bike built in the last week lands after the horizon,
    so B plans no builds in week 121 and no transfers in the last week."""
    assert B["builds"][121].sum() == 0 and B["moves"][121].sum() == 0


# ---------------- what the plan pages read, per SKU ----------------

def test_scenario_a_per_sku_equals_the_base_run(A):
    """The plan pages read every scenario through run_case; for A that must be the frozen base run exactly."""
    base = aux_fns.run_plan()
    net = A["net"].droplevel("pool").loc[base["net"].index]
    assert np.abs(net.values - base["net"].values).max() == 0
    H = len(base["obj"].weeks)
    ok = base["net"].loc[:, 1:H] >= base["target_units"] - 1e-6
    assert (A["at_target"].droplevel("pool").loc[ok.index].values == ok.values).all()
    assert (A["builds"].values == base["builds"].loc[A["builds"].index].values).all()


@pytest.mark.parametrize("which", ["A", "B"])
def test_balance_per_sku(which, A, B):
    """Inventory Balance page: opening net + built - forecast = closing net, per SKU, where net counts every
    site and stock in transit. Holds while nothing is built in the last build-time weeks (O14)."""
    R = {"A": A, "B": B}[which]
    H = len(R["obj"].weeks)
    net = R["net"].groupby(level="item").sum().add(R["transit"], fill_value=0)
    built = R["builds"].groupby(R["builds"].index.str.split("|").str[1]).sum().sum(axis=1)
    forecast = R["flows"]["demand"].groupby(level="item").sum().sum(axis=1)
    assert np.abs((net[0] + built - forecast - net[H]).values).max() < 1e-9
