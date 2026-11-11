"""Closure tests: master data must reproduce figures recounted independently from the raw CSVs."""
import pytest

from redwheel import aux_fns

EXPECTED_NET0 = {
    "RW-1378": 2, "RW-2984": -100, "RW-3980": -634, "RW-4418": -1285, "RW-6416": -752,
    "RW-7298": 61, "RW-9304": -1425, "RW-9324": 1840, "RW-9835": 9, "RW-9901": -707,
}


@pytest.fixture(scope="module")
def m():
    return aux_fns.build_master()


def test_orders(m):
    assert len(m["fact_orders"]) == 13_974
    assert m["fact_orders"].loc[m["fact_orders"].open_at_snapshot, "qty"].sum() == 5_991


def test_weeks(m):
    assert m["dim_week"]["in_plan_horizon"].sum() == 121
    assert len(m["dim_week"]) == 156


def test_skus_and_lines(m):
    assert len(m["dim_sku"]) == 10
    assert len(m["dim_line"]) == 4


def test_net0_per_sku(m):
    assert m["opening_position"].set_index("sku")["net0"].to_dict() == EXPECTED_NET0
