"""The LP against the planner's rule (lowest cover first). Each test checks a logical property, not a tuned number."""
import numpy as np
import pandas as pd
import pytest

from redwheel import aux_fns, engine, rtn
from test_engine import two_skus_one_line


# ---------------- the rule does what it says, by hand ----------------

def test_rule_builds_lowest_cover_first_within_capacity():
    """Line capacity 3/week, no demand, opening 0. Targets A=2, B=4 every week; weekly demand 1 each.
    Week 1: cover A=-2, B=-4 -> B first, gets all 3. Week 2: A=-2, B=-1 -> A gets 2, B gets the last 1.
    Week 3: both at target -> nothing."""
    obj = two_skus_one_line()
    tgt = pd.DataFrame([[2, 2, 2], [4, 4, 4]], index=["A", "B"], columns=[1, 2, 3], dtype=float)
    runs = engine.lowest_cover_first(obj, ["make|A|L", "make|B|L"], tgt, pd.Series({"A": 1.0, "B": 1.0}))
    assert runs.loc["make|A|L"].tolist() == [0, 2, 0]
    assert runs.loc["make|B|L"].tolist() == [3, 1, 0]


# ---------------- Redwheel ----------------

@pytest.fixture(scope="module")
def cmp():
    r = aux_fns.run_plan()
    return r, aux_fns.compare_plans(r)


def test_rule_plan_is_feasible(cmp):
    r, c = cmp
    rule = c["plans"]["Lowest-cover-first rule"]
    assert (rule.values == np.round(rule.values)).all() and rule.values.min() >= 0
    assert rtn.levels(r["obj"], rule).values.min() >= -1e-9          # capacity never exceeded, no negative level


def test_rule_follows_its_own_definition(cmp):
    """Each week, on each line, the rule stops only when capacity is used up or every SKU on the line is at target."""
    r, c = cmp
    obj, tu = r["obj"], r["target_units"]
    rule = c["plans"]["Lowest-cover-first rule"]
    X = rtn.levels(obj, rule)
    net = rtn.net_position(obj, X).loc[tu.index, tu.columns]
    at_target = net >= tu - 1e-6
    for ln, skus in r["line"].groupby(r["line"]).groups.items():
        cap_left = X.loc[f"capacity||RENO/{ln}", tu.columns]
        assert ((cap_left < 0.5) | at_target.loc[skus].all(axis=0)).all(), ln


def test_scoring_reproduces_the_solver(cmp):
    _, c = cmp
    assert abs(c["lp_unrounded_objective"] - c["lp_solver_objective"]) < 1e-6


def test_no_feasible_plan_beats_the_lp_on_its_objective(cmp):
    """The LP is optimal over every feasible plan; the rule and 'no builds' are feasible plans."""
    _, c = cmp
    s = c["summary"].loc["LP objective (lower is better)"]
    assert c["lp_unrounded_objective"] <= s["Lowest-cover-first rule"] + 1e-6
    assert c["lp_unrounded_objective"] <= s["No builds"] + 1e-6


def test_both_plans_end_at_target_so_build_about_the_same_total(cmp):
    """Total built = closing net - opening net + demand. Both plans end every SKU at target, each rounding a SKU
    up by less than one bike, so their totals can differ by at most one bike per SKU."""
    r, c = cmp
    s = c["summary"]
    assert s.at["All targets held from", "LP plan"] is not None
    assert s.at["All targets held from", "Lowest-cover-first rule"] is not None
    gap = abs(s.at["Bikes built", "LP plan"] - s.at["Bikes built", "Lowest-cover-first rule"])
    assert gap <= len(r["target_units"])


def test_comparison_reuses_the_plan_measures(cmp):
    """The LP's weeks of supply and at-target flags in the comparison are the same as the plan's own."""
    r, c = cmp
    lp = "LP plan"
    assert (c["wos"][lp] - r["wos"]).abs().values.max() < 1e-9
    net = r["net"].loc[r["target_units"].index, r["target_units"].columns]
    assert c["at_target"][lp].equals(net >= r["target_units"] - 1e-6)
