"""R and R+: scenario A with a build time (R: a week on every line; R+: two on the carbon lines, one on the base
lines), and R+'s events. Pinned: each plan's dates; each event's footprint, the same as on A; the Christmas closure,
absorbed in 2027 and not in 2026; and that every plan delivers the most any plan could by every week, on every line
(docs/WORKING_NOTES.md, O36 and D28)."""
import numpy as np
import pandas as pd
import pytest

from redwheel import rtn, scenarios as sc

H = list(range(1, 122))


@pytest.fixture(scope="module")
def runs():
    return {k: sc.run_case(c) for k, c in sc.R_CASES.items()}


def day(ts):
    return str(pd.Timestamp(ts).date())


def held(R):
    return {ln: day(d) for ln, d in sc.held_by_line(R).max(axis=1).items()}


def owed(R):
    return R["flows"]["open_orders"][H].groupby(R["line"]).sum()


def line_builds(R):
    b = R["builds"][H]
    return b.groupby(b.index.str.split("/").str[1]).sum()


def lines_that_moved(R, base):
    d = (R["builds"][H] - base["builds"][H]).abs().gt(0.5)
    return sorted(d.groupby(d.index.str.split("/").str[1]).any().any(axis=1).loc[lambda s: s].index)


def test_every_r_scenario_passes_every_plan_check(runs):
    for k, R in runs.items():
        c = sc.checks(R)
        assert c["pass"].all(), (k, c.loc[~c["pass"], "check"].tolist())


def test_r_and_r_plus_pinned(runs):
    s = {k: sc.scorecard(runs[k]) for k in ("R", "R+")}
    assert s["R"]["Bikes built"] == s["R+"]["Bikes built"] == 94429
    assert day(s["R"]["All targets held from"]) == "2027-09-20"
    assert day(s["R"]["Open orders cleared from"]) == "2026-12-28"
    assert s["R"]["On-time fill rate"] == pytest.approx(0.95496, abs=1e-5)
    assert day(s["R+"]["All targets held from"]) == "2027-10-04"
    assert day(s["R+"]["Open orders cleared from"]) == "2027-01-11"
    assert s["R+"]["On-time fill rate"] == pytest.approx(0.94755, abs=1e-5)
    assert held(runs["R+"]) == {"mtb-base": "2027-03-08", "mtb-carbon": "2027-10-04", "road-base": "2026-11-16",
                                "road-carbon": "2027-08-30"}
    assert set(runs["R+"]["case"].build_weeks.values()) == {1, 2}
    assert all(n == (2 if "carbon" in ln else 1) for ln, n in runs["R+"]["case"].build_weeks.items())


def test_events_on_r_plus_leave_the_footprint_they_leave_on_a(runs):
    base, s0 = runs["R+"], sc.scorecard(runs["R+"])
    e1, e4 = sc.scorecard(runs["R+E1"]), sc.scorecard(runs["R+E4"])
    # line down three weeks: MTB carbon four weeks later (A: 6 Sep -> 4 Oct 2027), orders and fill unchanged
    assert lines_that_moved(runs["R+E1"], base) == ["mtb-carbon"]
    assert e1["Bikes built"] == s0["Bikes built"]
    assert day(e1["All targets held from"]) == "2027-11-01"
    assert e1["Open orders cleared from"] == s0["Open orders cleared from"]
    assert e1["On-time fill rate"] == pytest.approx(s0["On-time fill rate"], abs=1e-9)
    # a fleet order: exactly the 300 bikes more, MTB carbon a week later, orders two weeks later (as on A)
    assert lines_that_moved(runs["R+E4"], base) == ["mtb-carbon"]
    assert e4["Bikes built"] == s0["Bikes built"] + 300
    assert day(e4["All targets held from"]) == "2027-10-11"
    assert day(e4["Open orders cleared from"]) == "2027-01-25"
    assert e4["On-time fill rate"] == pytest.approx(0.94017, abs=1e-5)


def test_christmas_2027_is_absorbed_by_building_ahead(runs):
    R, base = runs["R+C27"], runs["R+"]
    lb, lb0 = line_builds(R), line_builds(base)
    assert (lb[[68, 69]] == 0).all().all()                                   # every line closed both weeks
    assert lb.sum(axis=1).equals(lb0.sum(axis=1))                            # the same bikes, every line
    changed = [t for t in H if (lb[t] - lb0[t]).abs().max() > 0.5]
    assert changed[0] >= 59 and changed[-1] == 69                            # only from 18 Oct 2027 to the closure
    ahead = (lb.cumsum(axis=1) - lb0.cumsum(axis=1))
    assert ahead.min().min() >= 0                                            # only ever earlier, never later
    assert ahead.max(axis=1).to_dict() == lb0[[68, 69]].sum(axis=1).to_dict()   # what R+ built in the closed weeks
    assert int(lb0[[68, 69]].sum().sum()) == 1928
    assert (lb.loc["mtb-carbon", 60:67] == 580).all()                        # the line runs full ahead of it
    assert np.abs((owed(R) - owed(base)).values).max() == 0                  # no customer waits, any week
    assert held(R) == held(base)
    s, s0 = sc.scorecard(R), sc.scorecard(base)
    assert s["Open orders cleared from"] == s0["Open orders cleared from"]
    assert s["On-time fill rate"] == pytest.approx(s0["On-time fill rate"], abs=1e-12)


def test_christmas_2026_costs_january_not_december(runs):
    R, base = runs["R+C26"], runs["R+"]
    lb, lb0 = line_builds(R), line_builds(base)
    assert (lb[[16, 17]] == 0).all().all()
    assert lb.sum(axis=1).equals(lb0.sum(axis=1))
    d = (owed(R) - owed(base))
    assert np.abs(d.drop("mtb-carbon").values).max() == 0                    # only MTB carbon customers wait
    late = d.loc["mtb-carbon"]
    assert late[:17].abs().max() == 0                                        # a two-week build: December is delivered
    assert (late[18:22] > 0).all() and late[23:].abs().max() == 0            # 4 Jan to 1 Feb 2027, then caught up
    assert int(late.max()) == 724 and int(late.sum()) == 2169
    s = sc.scorecard(R)
    assert day(s["Open orders cleared from"]) == "2027-02-08"
    assert s["On-time fill rate"] == pytest.approx(0.93783, abs=1e-5)
    assert held(R) == {"mtb-base": "2027-04-19", "mtb-carbon": "2027-10-25", "road-base": "2026-11-16",
                       "road-carbon": "2027-09-27"}


@pytest.mark.parametrize("key", ["R+", "R+C26", "R+C27"])
def test_the_plan_delivers_the_most_possible_by_every_week(runs, key):
    d = sc.most_delivered(runs[key])
    assert d["plan"].shape == (4, 121)
    assert d["gap"] <= 1e-6
    assert max(d["certificate"].values()) <= 1e-7
    assert d["fewest"].loc["mtb-carbon", 1] == pytest.approx(3592)          # not trivially zero


def test_the_deliveries_check_catches_a_plan_that_delivers_less(runs):
    R = runs["R+"]
    runs_ = R["runs"].copy()
    task = "make|RW-4418|RENO/mtb-carbon"
    runs_.loc[task, 3] -= 100                                                # 100 bikes built late: week 3 -> 59,
    runs_.loc[task, 59] += 100                                               # where the line has room
    assert line_builds(dict(R, builds=runs_.loc[R["builds"].index])).loc["mtb-carbon", 59] <= 580
    X = rtn.levels(R["obj"], runs_)
    assert X.values.min() >= -1e-9                                           # a plan the plant could run
    stock, open_orders = sc._split(X, R["positions"])
    late = dict(R, flows=sc.ship_from_levels(stock, open_orders))
    d = sc.most_delivered(late, [5, 10, 61])
    assert d["gap"] == pytest.approx(100)
    assert (d["plan"] - d["fewest"]).loc["mtb-carbon", 5] == pytest.approx(100)
    assert (d["plan"] - d["fewest"]).loc["mtb-carbon", 61] == pytest.approx(0)   # landed: nothing owed any more
