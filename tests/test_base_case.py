"""The base case, pinned. If a later change (lead times, locations, scenarios) moves the base plan,
this fails. New behaviour must be opt-in; the base case stays the default run.

Base case = builds decided on net inventory pooled across sites, no lead times in play,
shipping and transfers not decided. Values recorded 2026-11-11.
"""
import numpy as np
import pytest

from redwheel import aux_fns

BUILT = {"RW-1378": 5586, "RW-2984": 9427, "RW-3980": 7163, "RW-4418": 21585, "RW-6416": 12934,
         "RW-7298": 3870, "RW-9304": 16267, "RW-9324": 631, "RW-9835": 6544, "RW-9901": 10422}
# sum over weeks of (week number x units built): changes if any build moves to a different week
TIMING = {"RW-1378": 320420, "RW-2984": 533185, "RW-3980": 354511, "RW-4418": 1450186, "RW-6416": 870204,
          "RW-7298": 196828, "RW-9304": 989807, "RW-9324": 66033, "RW-9835": 327354, "RW-9901": 574465}


@pytest.fixture(scope="module")
def r():
    return aux_fns.run_plan()


def by_sku(r):
    b = r["builds"].copy()                     # never touch the shared run
    b.index = b.index.str.split("|").str[1]
    return b


def test_base_build_quantities(r):
    assert by_sku(r).sum(axis=1).astype(int).to_dict() == BUILT
    assert sum(BUILT.values()) == 94_429


def test_base_build_timing(r):
    b = by_sku(r)
    weeks = np.arange(1, b.shape[1] + 1)
    assert {s: int((b.loc[s].values * weeks).sum()) for s in b.index} == TIMING


def test_base_scorecard(r):
    assert int(r["report"]["weeks_below"].sum()) == 278
    assert str(r["report"]["held_from_date"].max().date()) == "2027-09-06"
    assert aux_fns.plan_checks(r)["pass"].all()
