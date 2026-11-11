"""Planning priors: the table every scenario runs from, checked against the network before a run."""
from dataclasses import replace

import pandas as pd
import pytest

from redwheel import aux_fns, priors, scenarios as sc
from redwheel.config import LINES


def edit(t, prior, applies_to, value, from_date=None):
    t = t.copy()
    sel = (t["prior"] == prior) & (t["applies_to"] == applies_to)
    if from_date is not None:
        sel &= t["from_date"] == from_date
    assert sel.sum() == 1
    t.loc[sel, "value"] = value
    return t


def test_every_scenario_table_is_valid(obj):
    for case in sc.CASES.values():
        assert priors.validate(case.priors, obj) == [], case.key


def test_table_reads_back_to_the_settings():
    a, b = sc.CASE_A, sc.CASE_B
    assert a.ship_routes == sc.ALL_ROUTES and a.decides == ("make",) and a.transfer_weeks == 1
    assert a.build_weeks == {ln: 0 for ln in LINES} and b.build_weeks == {ln: 1 for ln in LINES}
    assert set(b.ship_routes) == {("RENO", "DEALERS"), ("RENO", "COMMERCIAL"), ("CMH", "WEB")}
    assert b.decides == ("make", "move")
    pol = a.settings["dim_policy"]
    assert pol.assign(effective_from=pol["effective_from"].dt.strftime("%Y-%m-%d")).values.tolist() == \
        [["road", "2026-09-07", 8.0], ["road", "2028-01-03", 10.0], ["mtb_base", "2026-09-07", 12.0],
         ["mtb_carbon", "2026-09-07", 15.0]]


A = sc.CASE_A.priors
BAD = {
    "unknown prior": lambda: pd.concat([A, pd.DataFrame([["safety_stock", "road", 3, ""]], columns=priors.COLUMNS)]),
    "route not in the network": lambda: pd.concat([A, pd.DataFrame([["route", "CMH>RENO", "yes", ""]],
                                                                   columns=priors.COLUMNS)]),
    "route value not yes/no": lambda: edit(A, "route", "RENO>WEB", "maybe"),
    "customer unserved": lambda: edit(edit(A, "route", "RENO>WEB", "no"), "route", "CMH>WEB", "no"),
    "build weeks negative": lambda: edit(A, "build_weeks", "mtb-carbon", -1),
    "build weeks fractional": lambda: edit(A, "build_weeks", "mtb-carbon", 0.5),
    "line missing": lambda: A[~((A["prior"] == "build_weeks") & (A["applies_to"] == "road-base"))],
    "transfer too long": lambda: edit(A, "transfer_weeks", "RENO>CMH", 40),
    "target group missing from the start": lambda: A[~((A["prior"] == "target_weeks") & (A["applies_to"] == "mtb_base"))],
    "target not positive": lambda: edit(A, "target_weeks", "mtb_carbon", 0),
    "plan does not decide builds": lambda: edit(A, "decides", "make", "no"),
    "transfers inside one pool": lambda: edit(A, "decides", "move", "yes"),
    "PDC on its own, never restocked": lambda: edit(sc.CASE_B.priors, "decides", "move", "no"),
}


@pytest.mark.parametrize("name", BAD)
def test_validation_refuses(name, obj):
    assert priors.validate(BAD[name]().reset_index(drop=True), obj), name


def test_run_refuses_an_invalid_table():
    with pytest.raises(ValueError, match="same orders"):
        sc.run_case(replace(sc.CASE_A, key="X", priors=edit(A, "decides", "move", "yes")))


def test_build_time_per_line_reaches_only_that_line(m):
    t = priors.table(sc.ALL_ROUTES, {"road-base": 0, "road-carbon": 0, "mtb-base": 0, "mtb-carbon": 2},
                     transfer_weeks=1, decides=("make",), lines=LINES)
    s = priors.settings(t)
    obj = aux_fns.build_object(m, s["build_weeks"], s["transfer_weeks"])
    a = obj.arrows[obj.arrows["task_id"].str.startswith("make|") & (obj.arrows["amount"] > 0)]
    delay = a.set_index(a["task_id"].str.split("/").str[1])["delay"].groupby(level=0).unique()
    assert {k: list(v) for k, v in delay.items()} == {"mtb-base": [0], "mtb-carbon": [2], "road-base": [0],
                                                      "road-carbon": [0]}


def test_a_target_changed_in_the_table_changes_the_targets(m, obj):
    t = edit(A, "target_weeks", "mtb_carbon", 16)
    tw = aux_fns.target_wos(m | {"dim_policy": priors.settings(t)["dim_policy"]}, obj.weeks)
    grp = m["dim_sku"].set_index("sku")["target_group"]
    assert (tw.loc[grp[grp == "mtb_carbon"].index] == 16).all().all()
    assert (tw.loc[grp[grp == "mtb_base"].index] == 12).all().all()


def test_a_scenario_with_build_time_per_line_runs_and_passes_every_check():
    t = priors.table(sc.CASE_B.ship_routes, {"road-base": 0, "road-carbon": 1, "mtb-base": 1, "mtb-carbon": 2},
                     transfer_weeks=1, decides=("make", "move"), lines=LINES)
    R = sc.run_case(replace(sc.CASE_B, key="X", priors=t))
    c = sc.checks(R)
    assert c["pass"].all(), c[~c["pass"]].to_string()
    assert sc.rules(R["case"]).set_index("Rule").at["Build time", "Setting"] == \
        "road-base same week; road-carbon 1 week; mtb-base 1 week; mtb-carbon 2 weeks"
