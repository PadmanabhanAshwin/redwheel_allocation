"""Redwheel as an RTN object: is the supply chain represented the way we defined it?

Three groups: structure (what exists and how it connects), numbers (opening levels and
arrivals tie back to the files exactly), and the equation (run plans through it).
"""
import networkx as nx
import numpy as np
import pandas as pd
import pytest

from conftest import EXPECTED_NET0
from redwheel import rtn
from redwheel.config import TRANSFER_WEEKS

SITES = ("RENO", "CMH")
CUSTOMERS = {"dtc": "WEB", "dealer": "DEALERS", "commercial": "COMMERCIAL"}


def arrows_of(obj, tid):
    return obj.arrows[obj.arrows["task_id"] == tid].set_index(["resource_id", "delay"])["amount"].to_dict()


# ---------------- structure ----------------

def test_locations(obj):
    loc = obj.locations.set_index("location_id")
    assert loc["location_class"].value_counts().to_dict() == {
        "production_line": 4, "customer": 2, "factory": 1, "distribution_center": 1,
        "in_transit": 1, "dealer": 1}
    lines = loc[loc["location_class"] == "production_line"]
    assert (lines["parent"] == "RENO").all()
    assert set(loc.index[loc["ours"]]) == {"RENO", "CMH", "RENO>CMH"}


def test_resource_counts(obj):
    r = obj.resources
    assert len(r) == 74
    assert r.groupby(["kind", "location"]).size().to_dict() == {
        ("capacity", "RENO/mtb-base"): 1, ("capacity", "RENO/mtb-carbon"): 1,
        ("capacity", "RENO/road-base"): 1, ("capacity", "RENO/road-carbon"): 1,
        ("inventory", "CMH"): 10, ("inventory", "DEALERS"): 10,
        ("inventory", "RENO"): 10, ("inventory", "RENO>CMH"): 10,
        ("order", "COMMERCIAL"): 10, ("order", "DEALERS"): 10, ("order", "WEB"): 10}


def test_task_and_arrow_counts(obj):
    assert obj.tasks["kind"].value_counts().to_dict() == {"fulfil": 60, "make": 10, "move": 10}
    per_task = obj.arrows.groupby("task_id").size()
    kind = obj.tasks.set_index("task_id")["kind"]
    assert per_task.groupby(kind).unique().map(list).to_dict() == {"fulfil": [2], "make": [2], "move": [4]}
    assert len(obj.arrows) == 180


def test_each_sku_is_made_on_its_own_line_only(obj, m):
    line = m["dim_sku"].set_index("sku")["line_id"]
    for sku in line.index:
        makes = obj.tasks[(obj.tasks["kind"] == "make") & (obj.tasks["item"] == sku)]["task_id"]
        assert len(makes) == 1
        assert arrows_of(obj, makes.iloc[0]) == {
            (f"capacity||RENO/{line[sku]}", 0): -1, (f"inventory|{sku}|RENO", 0): 1}


def test_each_line_is_shared_by_exactly_its_skus(obj, m):
    expected = m["dim_sku"].groupby("line_id")["sku"].apply(set).to_dict()
    cap = obj.arrows[obj.arrows["resource_id"].str.startswith("capacity|")]
    drawn = cap.merge(obj.tasks, on="task_id").groupby("resource_id")["item"].apply(set)
    assert {k.split("RENO/")[1]: v for k, v in drawn.items()} == expected
    assert expected == {"mtb-base": {"RW-9324", "RW-9901"}, "mtb-carbon": {"RW-4418", "RW-6416", "RW-9304"},
                        "road-base": {"RW-7298", "RW-9835"}, "road-carbon": {"RW-1378", "RW-2984", "RW-3980"}}


def test_move_goes_through_transit_and_takes_transfer_weeks(obj):
    for sku in obj.items["item"]:
        assert arrows_of(obj, f"move|{sku}|RENO>CMH") == {
            (f"inventory|{sku}|RENO", 0): -1,
            (f"inventory|{sku}|RENO>CMH", 0): 1,
            (f"inventory|{sku}|RENO>CMH", TRANSFER_WEEKS): -1,
            (f"inventory|{sku}|CMH", TRANSFER_WEEKS): 1}


def test_every_customer_can_be_served_from_both_sites(obj):
    for sku in obj.items["item"]:
        for cust in CUSTOMERS.values():
            for site in SITES:
                assert arrows_of(obj, f"fulfil|{sku}|{site}>{cust}") == {
                    (f"inventory|{sku}|{site}", 0): -1, (f"order|{sku}|{cust}", 0): -1}


def test_every_order_is_reachable_from_its_line(obj, m):
    """Graph view: line capacity -> make -> stock -> (move) -> stock -> fulfil, for every order."""
    g = rtn.to_networkx(obj)
    line = m["dim_sku"].set_index("sku")["line_id"]
    for r in obj.resources[obj.resources["kind"] == "order"].itertuples():
        fulfils = list(g.successors(r.resource_id))                  # tasks that take from this order
        assert len(fulfils) == 2
        for f in fulfils:
            stock = [u for u in g.predecessors(f) if g.nodes[u]["kind"] == "inventory"]
            assert len(stock) == 1
            assert nx.has_path(g, f"capacity||RENO/{line[r.item]}", stock[0])


def test_only_dealer_stock_is_unconnected(obj):
    g = rtn.to_networkx(obj)
    isolated = {n for n in g.nodes if g.degree(n) == 0}
    assert isolated == {f"inventory|{s}|DEALERS" for s in obj.items["item"]}


# ---------------- numbers ----------------

def test_opening_inventory_at_our_sites_matches_plant_file_row_by_row(obj, m):
    inv = m["fact_inventory"]
    plant = inv[inv["nettable"]]
    site = {"RENO-FG": "RENO", "CMH-DC": "CMH"}
    assert len(plant) == 20
    for row in plant.itertuples():
        assert obj.opening[f"inventory|{row.sku}|{site[row.location_code]}"] == row.on_hand


def test_opening_dealer_stock_matches_dealer_report(obj, m):
    inv = m["fact_inventory"]
    per_sku = inv[~inv["nettable"]].groupby("sku")["on_hand"].sum()
    for sku, q in per_sku.items():
        assert obj.opening[f"inventory|{sku}|DEALERS"] == q
    assert per_sku.sum() == 2_000


def test_opening_orders_match_backlog(obj, m):
    o = m["fact_orders"][m["fact_orders"]["open_at_snapshot"]]
    for (sku, ch), q in o.groupby(["sku", "channel"])["qty"].sum().items():
        assert obj.opening[f"order|{sku}|{CUSTOMERS[ch]}"] == q
    by_cust = obj.opening[obj.resources.set_index("resource_id")["kind"] == "order"]
    assert by_cust.groupby(lambda r: r.split("|")[2]).sum().to_dict() == {
        "COMMERCIAL": 938, "DEALERS": 2914, "WEB": 2139}


def test_opening_totals(obj):
    loc = obj.resources.set_index("resource_id")
    tot = obj.opening.groupby([loc["kind"], loc["location"]]).sum()
    assert tot[("inventory", "RENO")] == 1_965
    assert tot[("inventory", "CMH")] == 1_035
    assert tot[("inventory", "RENO>CMH")] == 0
    assert tot["capacity"].sum() == 0
    assert tot["order"].sum() == 5_991


def test_arrivals_match_forecast_and_capacity_exactly(obj, m):
    t = obj.weeks.set_index("week_start")["t"]
    f = m["fact_forecast"][m["fact_forecast"]["week_start"].isin(t.index)]
    assert len(f) == 121 * 30
    for row in f.itertuples():
        assert obj.arrivals.at[f"order|{row.sku}|{CUSTOMERS[row.channel]}", t[row.week_start]] == row.forecast_units
    for row in m["fact_capacity"].itertuples():
        assert obj.arrivals.at[f"capacity||RENO/{row.line_id}", t[row.week_start]] == row.capacity_units
    kind = obj.resources.set_index("resource_id")["kind"]
    assert obj.arrivals[kind == "inventory"].values.sum() == 0
    assert obj.arrivals[kind == "order"].values.sum() == 79_622
    assert obj.arrivals[kind == "capacity"].values.sum() == 123_150


def test_opening_net_position_matches_independent_recount(obj):
    npos = rtn.net_position(obj, rtn.levels(obj))
    assert npos[0].astype(int).to_dict() == EXPECTED_NET0


# ---------------- the equation ----------------

def test_no_plan(obj):
    """Nothing built or shipped: stock stays put, orders pile up by the forecast, capacity resets."""
    X = rtn.levels(obj)
    kind = obj.resources.set_index("resource_id")["kind"]
    inv = X[kind == "inventory"]
    assert (inv.sub(inv[0], axis=0) == 0).all().all()
    orders = X[kind == "order"]
    expected = obj.arrivals[kind == "order"].cumsum(axis=1).add(obj.opening[kind == "order"], axis=0)
    assert np.allclose(orders.loc[:, 1:].values, expected.values)
    assert np.allclose(X[kind == "capacity"].loc[:, 1:].values, obj.arrivals[kind == "capacity"].values)


def feasible_plan(obj, seed, build_share, move_share):
    """A deliberately simple plan that never takes more than is there:
    build a random share of each line's capacity, ship from CMH first then RENO, move a share
    of what is left at RENO to CMH. Week by week, reading levels from the object itself."""
    rng = np.random.default_rng(seed)
    H = len(obj.weeks)
    sku_line = obj.tasks[obj.tasks["kind"] == "make"].set_index("item")["task_id"].str.split("|").str[2]
    n_on_line = sku_line.value_counts()
    runs = pd.DataFrame(0.0, index=obj.tasks["task_id"], columns=range(1, H + 1))
    for t in range(1, H + 1):
        prev = rtn.levels(obj, runs)[t - 1]
        for sku, line in sku_line.items():
            cap = obj.arrivals.at[f"capacity||{line}", t]
            b = np.floor(cap / n_on_line[line] * build_share * rng.uniform(0.5, 1))
            runs.at[f"make|{sku}|{line}", t] = b
            landed = runs.at[f"move|{sku}|RENO>CMH", t - TRANSFER_WEEKS] if t > TRANSFER_WEEKS else 0
            avail = {"CMH": prev[f"inventory|{sku}|CMH"] + landed, "RENO": prev[f"inventory|{sku}|RENO"] + b}
            for cust in CUSTOMERS.values():
                owed = prev[f"order|{sku}|{cust}"] + obj.arrivals.at[f"order|{sku}|{cust}", t]
                for site in ("CMH", "RENO"):
                    q = min(avail[site], owed)
                    runs.at[f"fulfil|{sku}|{site}>{cust}", t] = q
                    avail[site] -= q
                    owed -= q
            runs.at[f"move|{sku}|RENO>CMH", t] = np.floor(move_share * avail["RENO"])
    return runs


PLANS = [(0, 1.0, 0.3), (1, 1.0, 1.0), (2, 0.2, 1.0), (3, 1.0, 0.0)]


@pytest.fixture(scope="module", params=PLANS, ids=lambda p: f"seed{p[0]}-build{p[1]}-move{p[2]}")
def run(request, obj):
    runs = feasible_plan(obj, *request.param)
    return runs, rtn.levels(obj, runs)


def per_sku(obj, runs, kind):
    k = obj.tasks.set_index("task_id")
    return runs[k["kind"] == kind].groupby(k["item"]).sum()


def test_no_level_below_zero(run):
    _, X = run
    assert X.values.min() >= 0


def test_net_position_reduces_to_built_minus_forecast(obj, run):
    runs, X = run
    built = per_sku(obj, runs, "make")
    kind = obj.resources.set_index("resource_id")
    demand = obj.arrivals[kind["kind"] == "order"].groupby(kind["item"]).sum()
    net0 = pd.Series(EXPECTED_NET0)
    expected = (built - demand).cumsum(axis=1).add(net0, axis=0)
    got = rtn.net_position(obj, X).loc[expected.index, 1:]
    assert np.abs(got.values - expected.values).max() == 0


def test_bikes_are_conserved(obj, run):
    runs, X = run
    res = obj.resources.set_index("resource_id")
    ours = res["location"].isin(["RENO", "CMH", "RENO>CMH"]) & (res["kind"] == "inventory")
    stock = X[ours].groupby(res["item"]).sum()
    change = stock.diff(axis=1).loc[:, 1:]
    expected = per_sku(obj, runs, "make") - per_sku(obj, runs, "fulfil")
    assert np.abs(change.values - expected.loc[change.index].values).max() == 0


def test_transfers_land_after_transfer_weeks(obj, run):
    runs, X = run
    for sku in obj.items["item"]:
        moved = runs.loc[f"move|{sku}|RENO>CMH"]
        shipped = sum(runs.loc[f"fulfil|{sku}|CMH>{c}"] for c in CUSTOMERS.values())
        change = X.loc[f"inventory|{sku}|CMH"].diff().loc[1:]
        landed = moved.shift(TRANSFER_WEEKS, fill_value=0)
        assert np.abs(change - (landed - shipped)).max() == 0


def test_dealer_stock_never_changes(obj, run):
    _, X = run
    dealer = X[obj.resources.set_index("resource_id")["location"] == "DEALERS"]
    dealer = dealer[dealer.index.str.startswith("inventory|")]
    assert (dealer.sub(dealer[0], axis=0) == 0).all().all()


def test_plans_actually_exercise_the_network(obj, run):
    """Guard against a vacuous pass: the plans build, ship from both sites, and (when asked) move."""
    runs, _ = run
    kind = obj.tasks.set_index("task_id")["kind"]
    assert runs[kind == "make"].values.sum() > 0
    assert runs[runs.index.str.contains(r"\|CMH>")].values.sum() > 0
    assert runs[runs.index.str.contains(r"\|RENO>(?:WEB|DEALERS|COMMERCIAL)")].values.sum() > 0
