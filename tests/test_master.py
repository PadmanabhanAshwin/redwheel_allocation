"""Closure tests: the master data must reproduce figures independently derived
from the raw CSVs (stdlib recount, 2026-11-11). If these fail, the mapping is wrong.
"""
import pytest

from redwheel import master

EXPECTED_NET0 = {
    "RW-1378": 2, "RW-2984": -100, "RW-3980": -634, "RW-4418": -1285, "RW-6416": -752,
    "RW-7298": 61, "RW-9304": -1425, "RW-9324": 1840, "RW-9835": 9, "RW-9901": -707,
}


@pytest.fixture(scope="module")
def tables():
    return master.build()


def test_schema(tables):
    master.validate(tables)


def test_row_counts(tables):
    assert len(tables["fact_orders"]) == 13_974
    assert tables["dim_week"]["in_plan_horizon"].sum() == 121
    assert tables["fact_forecast"]["week_start"].nunique() == 156


def test_backlog_total(tables):
    assert tables["opening_position"]["backlog"].sum() == 5_991


def test_net0_per_sku(tables):
    net0 = tables["opening_position"].set_index("sku")["net0"].to_dict()
    assert net0 == EXPECTED_NET0
