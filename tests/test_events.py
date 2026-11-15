"""Events: scenarios whose world differs from the base, solved by the object itself.

A scenario is settings plus changes to the object's numbers. Each event below is scenario A's settings with one
change, and is checked three ways: the change touched exactly the numbers it says; the plan responds where it must
and nowhere else (every other line's builds identical to A, week by week); and every plan check still passes.
The expected numbers were worked out before the code was written (docs/WORKING_NOTES.md, D15)."""
from dataclasses import replace

import numpy as np
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
    the line's total, not for each SKU.) Re-pinned for D21 (weeks short over the target window): the re-mix is smaller
    in weeks 25 and 29 and spread as swaps of at most 2 bikes over weeks 30-51 (31 bikes in all)."""
    R = sc.run_case(sc.CASE_E1)
    d = (by_sku(R) - by_sku(A)).astype(int)
    mtb = ["RW-4418", "RW-6416", "RW-9304"]
    assert (d.drop(index=mtb) == 0).all().all()
    total = d.loc[mtb].sum()
    assert list(total[total != 0].index) == [26, 27, 28, 53, 54, 55, 56, 57]
    assert d.loc[mtb, 25].to_dict() == {"RW-4418": -2, "RW-6416": -1, "RW-9304": 3}              # the re-mix before the stoppage
    assert d.loc[mtb, 29].to_dict() == {"RW-4418": -1, "RW-6416": -1, "RW-9304": 2}
    quiet = [t for t in d.columns if t not in (25, 26, 27, 28, 29, *range(53, 58))]
    assert d.loc[mtb, quiet].abs().max().max() <= 2                                              # elsewhere: small swaps
    assert (d.loc[mtb, quiet].sum() == 0).all()                                                  # between SKUs, none added


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


def test_event_3_parts_late_the_plan_builds_ahead(A):
    """No RW-4418 can be built for the eight weeks from 25 Oct 2027 (plan weeks 60-67): its frames are late. The line
    has spare capacity before then and the plan knows, so it builds the 1,394 bikes it would have made in those weeks
    in the five weeks before. Nothing else moves: no other SKU, no date, no total."""
    R = sc.run_case(sc.CASE_E3)
    rep = R["change_report"].iloc[0]
    assert (rep["field"], rep["resources"], rep["cells"], rep["after"]) == ("run_max", 1, 8, 0) and np.isnan(rep["before"])
    b, b0 = by_sku(R), by_sku(A)
    d = (b - b0).astype(int)
    assert d.loc["RW-4418"][d.loc["RW-4418"] != 0].to_dict() == {
        55: 255, 56: 289, 57: 284, 58: 284, 59: 282, 60: -130, 61: -131, 62: -132, 63: -132, 64: -215, 65: -216,
        66: -218, 67: -220}
    assert b.loc["RW-4418", list(range(60, 68))].sum() == 0 and d.loc["RW-4418"].sum() == 0
    assert (d.drop(index="RW-4418") == 0).all().all()
    assert sc.scorecard(R) == sc.scorecard(A) and held(R) == held(A)
    assert R["lp"].objective > A["lp"].objective                   # a limit can only cost: here the stock carried ahead
    all_checks_pass(R)


def test_event_3_is_not_absorbed_under_bs_rules():
    """The same event on scenario B (a week to build, web orders from the PDC, transfers planned): less room before the
    gap, so 142 bikes cannot be made up and one position is short for one week inside the gap. Since D21 that is
    RW-4418 at Reno in week 68 (20 Dec 2027), so all targets are held from 27 Dec 2027, not 27 Sep. (Before D21 the
    same 142 bikes fell on RW-6416 and RW-9304 in week 60, giving 1 Nov: the objective does not prefer a week for an
    unavoidable shortfall, and "held from" dates the last one; see docs/SOLVER.md.)"""
    B = sc.run_case(sc.CASE_B)
    R = sc.run_case(replace(sc.CASE_B, key="X", changes=sc.CASE_E3.changes))
    assert str(sc.scorecard(B)["All targets held from"].date()) == "2027-09-27"
    assert str(sc.scorecard(R)["All targets held from"].date()) == "2027-12-27"
    H = len(R["obj"].weeks)
    late = (R["target_units"] - R["net"][list(range(1, H + 1))]).clip(lower=0).loc[:, 56:].stack()
    assert late[late > 1e-6].round(6).to_dict() == {("RW-4418", "RENO", 68): 142.0}      # the only shortfall after week 55
    assert by_sku(R).loc["RW-4418", list(range(60, 68))].sum() == 0
    assert int(R["builds"].values.sum()) == int(B["builds"].values.sum())            # the same bikes, at other times
    all_checks_pass(R)


def test_event_3_solved_a_second_way_gives_the_same_plan():
    """The run limit, against the same event written without one: a 'frames' capacity that RW-4418 uses one of per bike,
    with none arriving in weeks 60-67 and plenty otherwise. The two allow exactly the same plans, so the optimum must
    match: objective, every run, every level."""
    from redwheel import aux_fns, engine, rtn
    from redwheel.changes import apply
    m = aux_fns.build_master()
    base = aux_fns.build_object(m, sc.CASE_A.build_weeks, sc.CASE_A.transfer_weeks)
    H, task = len(base.weeks), "make|RW-4418|RENO/mtb-carbon"

    def lp(obj):
        st = sc.CASE_A.settings
        pos = sc.positions(obj, sc.pools(st["ship_routes"]))
        demand = rtn.order_arrivals(obj, pos)
        it = aux_fns.target_wos(m | {"dim_policy": st["dim_policy"]}, obj.weeks)
        tw = pd.DataFrame({t: [it.at[k[0], t] for k in pos] for t in it.columns}, index=demand.index)
        sku = m["dim_sku"].set_index("sku")
        free = list(obj.tasks.loc[obj.tasks["kind"].isin(st["decides"]), "task_id"])
        tu = engine.forward_sum(demand, tw)
        return engine.decide(obj, free, tu, engine.window_demand(tu, tw),
                             pd.Series({k: sku.at[k[0], "line_id"] for k in pos}), positions=pos, w_run=1e-6)

    limited = apply(base, list(sc.CASE_E3.changes))[0]
    rid, loc = "capacity||SUPPLIER/frames", "SUPPLIER/frames"
    frames = pd.Series(100_000.0, index=range(1, H + 1))
    frames.loc[60:67] = 0
    other = replace(base,
                    locations=pd.concat([base.locations, pd.DataFrame([{"location_id": loc, "location_class": "production_line",
                                                                        "parent": None, "ours": False}])], ignore_index=True),
                    resources=pd.concat([base.resources, pd.DataFrame([{"resource_id": rid, "kind": "capacity", "item": None,
                                                                        "location": loc, "carry": False}])], ignore_index=True),
                    arrows=pd.concat([base.arrows, pd.DataFrame([{"task_id": task, "resource_id": rid, "amount": -1,
                                                                  "delay": 0}])], ignore_index=True),
                    arrivals=pd.concat([base.arrivals, frames.to_frame().T.set_axis([rid])]),
                    outlook=pd.concat([base.outlook, pd.DataFrame(0, index=[rid], columns=base.outlook.columns)]),
                    opening=pd.concat([base.opening, pd.Series([0], index=[rid])]))
    rtn.validate(other)
    assert other.run_max is None
    p1, p2 = lp(limited), lp(other)
    assert p1.objective == pytest.approx(p2.objective, abs=1e-9)
    assert np.abs((p1.runs - p2.runs).to_numpy()).max() < 1e-9
    shared = base.resources["resource_id"]
    assert np.abs((p1.levels.loc[shared] - p2.levels.loc[shared]).to_numpy()).max() < 1e-9


def limited(sku, first, last, value=0, kind="make", base=sc.CASE_A):
    return replace(base, key="L", changes=(Change("run_max", {"kind": kind, "item": sku}, "set", value, first, last),))


def test_below_target_while_the_line_has_room_is_explained_by_the_limit():
    """No RW-9835 built in weeks 1-4. It starts below target; the road base line has room some of those weeks, yet
    RW-9835 cannot use it. The check, as it was before run limits, would call 9 of those position-weeks unexplained; it
    now counts a SKU at its limit as held back, like a full line."""
    R = sc.run_case(limited("RW-9835", 1, 4))
    assert by_sku(R).loc["RW-9835", [1, 2, 3, 4]].sum() == 0
    all_checks_pass(R)
    c = sc.checks(R).set_index("check")
    assert c.filter(like="Below target", axis=0)["value"].iloc[0].endswith(", 0 unexplained")
    # the same plan judged without the limit (as if it held RW-9835 back for no reason) fails the check
    R_no_reason = {**R, "obj": replace(R["obj"], run_max=None)}
    c2 = sc.checks(R_no_reason).set_index("check")
    below = c2.filter(like="Below target", axis=0).iloc[0]
    assert not below["pass"] and below["value"].endswith(", 9 unexplained")


def test_runs_above_a_limit_fail_the_check():
    R = sc.run_case(sc.CASE_E3)
    runs = R["runs"].copy()
    runs.loc["make|RW-4418|RENO/mtb-carbon", 61] += 1                # one bike built while its frames are missing
    c = sc.checks({**R, "runs": runs}).set_index("check")
    assert not c.at["No task runs above its run limit", "pass"] and c.at["No task runs above its run limit", "value"] == "most above 1"


def test_a_limit_on_runs_the_plan_does_not_decide_is_refused():
    """In A the plan decides builds only; transfers are never planned, so a transfer limit would change nothing."""
    with pytest.raises(ValueError, match="would change nothing: move\\|RW-4418\\|RENO>CMH"):
        sc.run_case(limited("RW-4418", 10, 20, value=5, kind="move"))


def test_a_transfer_limit_in_b():
    """B plans transfers to the PDC; RW-4418 moves up to 59 a week in weeks 10-20. At most 20 a week: kept to in the LP
    and after rounding, every check passes, and the plan can only get worse."""
    B = sc.run_case(sc.CASE_B)
    R = sc.run_case(limited("RW-4418", 10, 20, value=20, kind="move", base=sc.CASE_B))
    moves = R["moves"].loc["move|RW-4418|RENO>CMH"]
    assert B["moves"].loc["move|RW-4418|RENO>CMH", 10:20].max() > 20                 # the limit binds
    assert moves.loc[10:20].max() <= 20 and R["lp"].runs.loc["move|RW-4418|RENO>CMH", 10:20].max() <= 20 + 1e-9
    assert R["lp"].objective >= B["lp"].objective - 1e-9
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


def test_a_run_limit_is_saved_and_loaded_with_the_scenario(tmp_path, A):
    store.save(sc.CASE_E3, tmp_path)
    back = store.load_all(tmp_path)["E3"]
    assert back.changes == sc.CASE_E3.changes
    R = sc.run_case(back)
    assert by_sku(R).loc["RW-4418", list(range(60, 68))].sum() == 0 and held(R) == held(A)


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


def test_event_4_a_fleet_order_when_the_line_is_full(A):
    """300 RW-4418 for a commercial customer in the week of 9 Nov 2026 (plan week 10), on scenario A. The line is full,
    so the 300 are built when capacity rises (weeks 53-54); MTB carbon holds its targets from 13 Sep 2027 instead of
    6 Sep, every open order is cleared from 28 Dec 2026 instead of 14 Dec, and the other lines do not move."""
    R = sc.run_case(sc.CASE_E4)
    rep = R["change_report"].iloc[0]
    assert (rep["field"], rep["op"], rep["value"], rep["cells"], rep["before"], rep["after"]) == ("arrival", "add", 300, 1, 7, 307)
    d = (by_sku(R) - by_sku(A)).astype(int)
    assert d.sum(axis=1)[lambda x: x != 0].to_dict() == {"RW-4418": 300}
    mtb = ["RW-4418", "RW-6416", "RW-9304"]
    assert d.loc[mtb].sum()[lambda x: x != 0].to_dict() == {53: 77, 54: 223}
    assert (d.drop(index=mtb) == 0).all().all()
    s = sc.scorecard(R)
    assert str(sc.held_by_line(R).at["mtb-carbon", "CMH+RENO"].date()) == "2027-09-13"
    assert str(s["Open orders cleared from"].date()) == "2026-12-28" and round(s["On-time fill rate"], 4) == 0.9564
    all_checks_pass(R)


def test_event_5_a_bike_built_in_lots(A):
    """RW-9304 built in lots of 50 (a fixed order quantity), on scenario A. Every build of it is a whole lot; the line
    stays as full as in A every week it was full (weeks 1-52, the lots' room goes to the line's other bikes); every
    line's date is as in A; the cost is a week on the day every order is cleared (21 Dec, not 14 Dec), a little fill,
    and 1,744 bike-weeks of RW-9304 carried above target. The other lines do not move."""
    R = sc.run_case(sc.CASE_E5)
    b, b0 = by_sku(R), by_sku(A)
    assert (b.loc["RW-9304"] % 50 == 0).all()
    mtb = ["RW-4418", "RW-6416", "RW-9304"]
    assert (b.loc[mtb, 1:52].sum() == b0.loc[mtb, 1:52].sum()).all()
    assert (b.drop(index=mtb) == b0.drop(index=mtb)).all().all()
    assert sc.held_by_line(R).equals(sc.held_by_line(A))
    s = sc.scorecard(R)
    assert str(s["Open orders cleared from"].date()) == "2026-12-21" and round(s["On-time fill rate"], 4) == 0.9631
    w = list(range(1, len(R["obj"].weeks) + 1))
    above = (R["net"][w] - R["target_units"]).clip(lower=0).loc[[("RW-9304", "CMH+RENO")]].values.sum()
    assert round(above) == 1744 and round((A["net"][w] - A["target_units"]).clip(lower=0).loc[[("RW-9304", "CMH+RENO")]].values.sum()) == 0
    chk = sc.checks(R)
    assert chk["pass"].all() and "largest lot" in chk["check"].iloc[3]
    gap = R["runs"].cumsum(axis=1) - R["lp"].runs.loc[R["runs"].index].cumsum(axis=1)
    assert gap.abs().values.max() < 50
