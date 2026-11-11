"""The report: KPIs are consistent with the plan and with each other."""
import numpy as np
import pandas as pd
import pytest

from redwheel import aux_fns, engine, rtn

ROAD_STEP_WEEK = 70        # 2028-01-03, road target 8 -> 10


@pytest.fixture(scope="module")
def r(obj, m):
    demand = aux_fns.forecast_by_item(m)
    tw = aux_fns.target_wos(m, obj.weeks)
    tu = engine.forward_sum(demand, tw)
    free = list(obj.tasks.loc[obj.tasks["kind"] == "make", "task_id"])
    line = m["dim_sku"].set_index("sku")["line_id"]
    p = engine.decide(obj, free, tu, demand.loc[:, 1:121].mean(axis=1), line)
    B = engine.round_runs(obj, p.runs)
    X = rtn.levels(obj, B)
    rep = aux_fns.target_report(m, obj, X, rtn.levels(obj), tu, tw, demand)
    wos = rtn.weeks_of_supply(rtn.net_position(obj, X), demand).loc[tu.index]
    return dict(B=B, X=X, tu=tu, rep=rep, wos=wos, line=line)


def test_target_kpis(r):
    rep = r["rep"]
    assert rep["weeks_below"].sum() == 278
    assert rep["held_from"].to_dict() == {
        "RW-1378": 48, "RW-2984": 48, "RW-3980": 48,                 # after the July 2027 spike
        "RW-4418": 53, "RW-6416": 53, "RW-9304": 53,                 # mtb-carbon capacity step 2027-09-06
        "RW-7298": 9, "RW-9835": 9, "RW-9901": 23, "RW-9324": 1}
    assert (rep["weeks_below"] <= rep["weeks_below_no_plan"]).all()
    assert (rep["first_at_target"] <= rep["held_from"]).all()


def test_group_is_lowest_sku(r, m):
    g = aux_fns.group_wos(r["wos"], m["dim_sku"])
    grp = m["dim_sku"].set_index("sku")["target_group"]
    for name, skus in grp.groupby(grp).groups.items():
        assert np.allclose(g.loc[name], r["wos"].loc[skus].min())


def test_build_plan_table(obj, r):
    t = aux_fns.build_plan_table(obj, r["B"])
    assert len(t) == 10 * 121 and t["units"].sum() == r["B"].values.sum()
    assert (t["units"] >= 0).all()
    cap = obj.arrivals[obj.arrivals.index.str.startswith("capacity|")]
    cap.index = cap.index.str.replace("capacity||RENO/", "", regex=False)
    tmap = obj.weeks.set_index("week_start")["t"]
    per = t.assign(t=t["week_start"].map(tmap)).groupby(["line", "t"])["units"].sum().unstack()
    assert (per <= cap.loc[per.index]).all().all()


def test_utilisation_is_built_over_capacity(obj, r):
    u = rtn.utilisation(obj, r["X"])
    built = r["B"].groupby("capacity||" + r["B"].index.str.split("|").str[2]).sum()
    assert np.abs(u.values - (built.loc[u.index] / obj.arrivals.loc[u.index]).values).max() < 1e-12
    assert u.values.min() >= 0 and u.values.max() <= 1 + 1e-12


def test_stock_above_target_only_to_build_ahead_of_the_2028_step(obj, r):
    """Once a SKU is held at target, more than one unit above it happens only in the weeks before
    the road step, with the line full in at least one week between then and the step."""
    net = rtn.net_position(obj, r["X"]).loc[r["tu"].index, 1:]
    held = r["rep"]["held_from"]
    cap = r["X"][r["X"].index.str.startswith("capacity|")]
    for s in net.index.drop("RW-9324"):                          # RW-9324 starts with 98 weeks of stock
        over = [t for t in net.columns if t >= held[s] and net.at[s, t] > r["tu"].at[s, t] + 1]
        for t in over:
            assert t < ROAD_STEP_WEEK, (s, t)
            assert (cap.loc[f"capacity||RENO/{r['line'][s]}", t:ROAD_STEP_WEEK] < 0.5).any(), (s, t)


def test_rw9324_built_only_once_stock_runs_down(r):
    b = r["B"].loc["make|RW-9324|RENO/mtb-base"]
    first = b[b > 0].index.min()
    assert first == 87
    assert (r["wos"].loc["RW-9324", :first - 1] > 12).all()


def test_limited_by_is_read_from_the_plan(r):
    lb = r["rep"]["limited_by"]
    assert set(lb[["RW-1378", "RW-2984", "RW-3980"]]) == {"demand peak ahead (below target May–Jul 2027)"}
    assert set(lb[["RW-4418", "RW-6416", "RW-9304"]]) == {"capacity until step-up, 6 Sep 2027"}
    assert set(lb[["RW-7298", "RW-9835", "RW-9901"]]) == {"opening backlog"}
    assert lb["RW-9324"] == "—"


def test_ship_asap_splits_net_position_exactly(obj, m):
    r = aux_fns.run_plan()
    f = r["flows"]
    net = r["net"].loc[f["on_hand"].index]
    assert (f["on_hand"] - f["open_orders"] - net).abs().values.max() < 1e-9          # parts add up to the plan
    assert (f["on_hand"].loc[:, 1:].clip(upper=f["open_orders"].loc[:, 1:]) == 0).all().all()   # never both
    assert f["on_hand"].values.min() >= 0 and f["open_orders"].values.min() >= 0
    # every bike built is either shipped or still on hand; every order is either shipped or still open
    built, dem, shp = f["built"].sum(axis=1), f["demand"].sum(axis=1), f["shipped"].sum(axis=1)
    assert (f["on_hand"][0] + built - shp - f["on_hand"][121]).abs().max() < 1e-9
    assert (f["open_orders"][0] + dem - shp - f["open_orders"][121]).abs().max() < 1e-9
