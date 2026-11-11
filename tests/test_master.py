"""Master data must reproduce figures recounted independently from the raw CSVs."""
from conftest import EXPECTED_NET0


def test_orders(m):
    assert len(m["fact_orders"]) == 13_974
    assert m["fact_orders"].loc[m["fact_orders"].open_at_snapshot, "qty"].sum() == 5_991


def test_weeks(m):
    w = m["dim_week"]
    assert len(w) == 156 and w["in_plan_horizon"].sum() == 121
    plan = w[w["in_plan_horizon"]]
    assert plan["week_idx"].tolist() == list(range(1, 122))
    assert str(plan["week_start"].iloc[0].date()) == "2026-09-07"
    assert str(plan["week_start"].iloc[-1].date()) == "2028-12-25"


def test_skus_lines_locations(m):
    assert len(m["dim_sku"]) == 10
    assert len(m["dim_line"]) == 4
    assert len(m["dim_location"]) == 10 and m["dim_location"]["location_id"].is_unique


def test_net0_per_sku(m):
    assert m["opening_position"].set_index("sku")["net0"].to_dict() == EXPECTED_NET0
