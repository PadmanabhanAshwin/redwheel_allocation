"""Demand sources: every breakdown reconciles to the same total, and the nearest-site rule is sane."""
import pytest

from redwheel import aux_fns


@pytest.fixture(scope="module")
def d(m):
    return aux_fns.demand_sources(m)


def test_every_breakdown_adds_up_to_the_same_total(d, m):
    total = m["fact_orders"]["qty"].sum()
    assert total == 32_652 == d["total"]
    assert d["by_channel"]["orders_last_52"].sum() == total
    assert d["weekly_orders"].values.sum() == total
    assert d["line_by_channel"].values.sum() == total


def test_located_demand_is_dealer_plus_web(d):
    """Commercial orders carry no location; dealer and web orders all do."""
    s = d["by_state"]
    ch = d["by_channel"]["orders_last_52"]
    assert "commercial" not in s.columns
    assert s["dealer"].sum() == ch["dealer"] and s["dtc"].sum() == ch["dtc"]
    assert len(s) == 20


def test_customers(d):
    ch = d["by_channel"]["orders_last_52"]
    assert len(d["dealers"]) == 45 and d["dealers"]["qty"].sum() == ch["dealer"]
    assert d["commercial_types"]["units"].sum() == ch["commercial"]
    assert d["commercial_accounts"] == 59


def test_forecast_reconciles(d, m):
    f = m["fact_forecast"]
    assert d["by_channel"]["forecast_horizon"].sum() == 79_622                 # same as the object's arrivals
    assert d["weekly_forecast"].values.sum() == 79_622
    assert d["by_channel"]["forecast_next_52"].sum() == f[f["week_start"] < "2027-09-06"]["forecast_units"].sum()


def test_nearest_site_is_geographically_sane():
    assert aux_fns.nearest_site("CA") == "RENO" and aux_fns.nearest_site("WA") == "RENO"
    assert aux_fns.nearest_site("MA") == "CMH" and aux_fns.nearest_site("FL") == "CMH"
    assert aux_fns.nearest_site("MI") == "CMH"
    with pytest.raises(ValueError):
        aux_fns.nearest_site("ZZ")
