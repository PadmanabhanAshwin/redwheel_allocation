"""Scenarios: a case is a named set of rules; the same object and solver run each one.

Scenario A is the base case and runs through `aux_fns.run_plan` untouched.
Other cases run through `run_case`: lead times go into the object, the routing rule defines
which stock faces which demand (pools), and the LP decides builds and transfers.
"""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import numpy as np
import pandas as pd

from redwheel import aux_fns, engine, rtn

SITES = ("RENO", "CMH")
CUSTOMERS = ("WEB", "DEALERS", "COMMERCIAL")
ALL_ROUTES = tuple((s, c) for s in SITES for c in CUSTOMERS)


@dataclass(frozen=True)
class Case:
    key: str
    name: str
    build_weeks: int                 # weeks from using line capacity to stock at the factory
    transfer_weeks: int              # weeks Reno -> PDC
    ship_routes: tuple               # routing rule (a planning prior): allowed (stock site, customer) pairs
    decides: tuple                   # task kinds the LP may run

    @property
    def is_base(self) -> bool:
        return self.key == "A"


CASE_A = Case("A", "Scenario A · base case", build_weeks=0, transfer_weeks=1,
              ship_routes=ALL_ROUTES, decides=("make",))
CASE_B = Case("B", "Scenario B · web via PDC, others direct", build_weeks=1, transfer_weeks=1,
              ship_routes=(("RENO", "DEALERS"), ("RENO", "COMMERCIAL"), ("CMH", "WEB")), decides=("make", "move"))
CASES = {c.key: c for c in (CASE_A, CASE_B)}


# ---------- pools: which stock faces which demand, read from the routing rule ----------

def pools(ship_routes: tuple) -> dict:
    """Connected groups of (stock site, customer) under the allowed routes.
    Returns {pool name: {"stock": [sites], "customers": [customers]}}; the name is its stock sites."""
    g = nx.Graph()
    g.add_edges_from((("site", s), ("cust", c)) for s, c in ship_routes)
    out = {}
    for comp in nx.connected_components(g):
        stock = sorted(n for k, n in comp if k == "site")
        out["+".join(stock)] = {"stock": stock, "customers": sorted(n for k, n in comp if k == "cust")}
    return dict(sorted(out.items()))


def positions(obj: rtn.RTN, pool_def: dict) -> dict:
    """One position per (item, pool): +1 on the pool's stock, -1 on the orders it serves.
    {(item, pool): {resource_id: sign}}"""
    out = {}
    for item in obj.items["item"]:
        for name, p in pool_def.items():
            signs = {rtn.resource_id("inventory", item, s): 1.0 for s in p["stock"]}
            signs.update({rtn.resource_id("order", item, c): -1.0 for c in p["customers"]})
            out[(item, name)] = signs
    return out


def position_levels(X: pd.DataFrame, pos: dict) -> pd.DataFrame:
    """Net inventory per position: stock that can ship - the orders it faces. (item, pool) x t."""
    rows = {k: sum(sign * X.loc[rid] for rid, sign in signs.items()) for k, signs in pos.items()}
    out = pd.DataFrame(rows).T
    out.index = pd.MultiIndex.from_tuples(out.index, names=["item", "pool"])
    return out


def position_demand(m: dict, pool_def: dict) -> pd.DataFrame:
    """Forecast per (item, pool) x week index (all forecast weeks): the channels the pool serves."""
    cust = m["dim_location"].dropna(subset=["channel"]).set_index("channel")["location_id"]
    t = m["dim_week"].set_index("week_start")["week_idx"]
    f = m["fact_forecast"].assign(t=m["fact_forecast"]["week_start"].map(t),
                                  customer=m["fact_forecast"]["channel"].map(cust))
    pool_of = {c: name for name, p in pool_def.items() for c in p["customers"]}
    f = f.assign(pool=f["customer"].map(pool_of))
    out = f.pivot_table(index=["sku", "pool"], columns="t", values="forecast_units", aggfunc="sum")
    out.index.names = ["item", "pool"]
    return out


# ---------- whole-bike transfers ----------

def round_moves(obj: rtn.RTN, lp_moves: pd.DataFrame, builds: pd.DataFrame) -> pd.DataFrame:
    """Whole-bike transfers: cumulative LP transfers rounded down, and never more than the origin holds
    once the whole-bike builds have landed. Week by week, per move task."""
    out = pd.DataFrame(0, index=lp_moves.index, columns=lp_moves.columns, dtype=int)
    a = obj.arrows
    for task in lp_moves.index:
        origin = a[(a["task_id"] == task) & (a["amount"] < 0) & (a["delay"] == 0)]["resource_id"].iloc[0]
        runs = pd.concat([builds, out.drop(index=task)])                       # everything except this task
        stock = rtn.levels(obj, runs).loc[origin]                               # origin stock with no transfers out
        lp_cum = lp_moves.loc[task].cumsum()
        done = 0
        for t in lp_moves.columns:
            want = int(np.floor(lp_cum[t] + 1e-9)) - done
            q = max(0, min(want, int(np.floor(stock[t] + 1e-9)) - done))
            out.at[task, t] = q
            done += q
    return out


# ---------- shipping projection ----------

def ship_from_levels(stock: pd.DataFrame, owed: pd.DataFrame) -> dict:
    """Orders ship as soon as stock exists, oldest first, without touching stock the plan transfers out later.

    stock, owed: position x t (0..H), with no shipping in them (cumulative). Cumulative shipped by week t is
    min(owed so far, the lowest stock level from t onwards); nothing has shipped at the snapshot (t = 0)."""
    floor_ahead = stock.iloc[:, ::-1].cummin(axis=1).iloc[:, ::-1]              # lowest level from t to the end
    shipped_cum = np.minimum(owed, floor_ahead)
    shipped_cum[0] = 0.0
    shipped_cum = shipped_cum.cummax(axis=1)                                    # t = 0 reset cannot un-ship
    weeks = list(stock.columns[1:])
    return {"on_hand": stock - shipped_cum, "open_orders": owed - shipped_cum,
            "shipped": shipped_cum.diff(axis=1)[weeks], "demand": owed.diff(axis=1)[weeks]}


# ---------- run a case ----------

def _split(X: pd.DataFrame, pos: dict):
    """Stock and orders per position, from levels without shipping."""
    idx = pd.MultiIndex.from_tuples(pos.keys(), names=["item", "pool"])
    stock = pd.DataFrame([sum(X.loc[r] for r, sg in v.items() if sg > 0) for v in pos.values()], index=idx)
    owed = pd.DataFrame([sum(X.loc[r] for r, sg in v.items() if sg < 0) for v in pos.values()], index=idx)
    return stock, owed


def _finish(case: Case, m: dict, obj: rtn.RTN, pool_def: dict, pos: dict, runs: pd.DataFrame, lp,
            demand: pd.DataFrame, target_wos: pd.DataFrame, target_units: pd.DataFrame) -> dict:
    """Everything measured from a plan, the same way for every case."""
    H = len(obj.weeks)
    X = rtn.levels(obj, runs)
    net = position_levels(X, pos)
    stock, owed = _split(X, pos)
    make = runs[runs.index.str.startswith("make|")]
    transit = X[X.index.str.contains(r"\|[A-Z]+>[A-Z]+$") & X.index.str.startswith("inventory|")]
    transit = transit.groupby(transit.index.str.split("|").str[1]).sum()
    return {
        "case": case, "m": m, "obj": obj, "pools": pool_def, "positions": pos, "lp": lp,
        "runs": runs, "builds": make, "moves": runs[runs.index.str.startswith("move|")],
        "X": X, "net": net, "demand": demand, "target_wos": target_wos, "target_units": target_units,
        "at_target": net[list(range(1, H + 1))] >= target_units - 1e-6,
        "wos": rtn.weeks_of_supply(net, demand),
        "flows": ship_from_levels(stock, owed), "transit": transit,
        "line": pd.Series({k: m["dim_sku"].set_index("sku").at[k[0], "line_id"] for k in pos}),
    }


def run_case(case: Case) -> dict:
    m = aux_fns.build_master()
    pool_def = pools(case.ship_routes)
    sku = m["dim_sku"].set_index("sku")
    if case.is_base:                                             # the frozen base case, measured per position
        r = aux_fns.run_plan()
        obj = r["obj"]
        pos = positions(obj, pool_def)
        demand = position_demand(m, pool_def)
        tw = pd.DataFrame({t: [r["target_wos"].at[k[0], t] for k in pos] for t in r["target_wos"].columns},
                          index=demand.index)
        return _finish(case, m, obj, pool_def, pos, r["builds"].astype(float), r["lp"], demand, tw,
                       engine.forward_sum(demand, tw))
    obj = aux_fns.build_object(m, case.build_weeks, case.transfer_weeks)
    H = len(obj.weeks)
    pos = positions(obj, pool_def)
    demand = position_demand(m, pool_def)
    item_target = aux_fns.target_wos(m, obj.weeks)
    tw = pd.DataFrame({t: [item_target.at[k[0], t] for k in pos] for t in item_target.columns}, index=demand.index)
    tu = engine.forward_sum(demand, tw)
    keys = list(pos)
    free = list(obj.tasks.loc[obj.tasks["kind"].isin(case.decides), "task_id"])
    lp = engine.decide(obj, free, tu.loc[keys], demand.loc[keys, list(range(1, H + 1))].mean(axis=1),
                       pd.Series({k: sku.at[k[0], "line_id"] for k in keys}), positions=pos, w_run=1e-6)
    make_ids = [k for k in free if k.startswith("make|")]
    builds = engine.round_runs(obj, lp.runs.loc[make_ids])
    moves = round_moves(obj, lp.runs.loc[[k for k in free if k.startswith("move|")]], builds)
    return _finish(case, m, obj, pool_def, pos, pd.concat([builds, moves]).astype(float), lp, demand, tw, tu)


# ---------- describing and scoring a case ----------

SITE_NAME = {"RENO": "Reno", "CMH": "the PDC (Columbus)"}
CUSTOMER_NAME = {"WEB": "web", "DEALERS": "dealer", "COMMERCIAL": "commercial"}
SHORT = {"RENO": "Reno", "CMH": "PDC"}


def rules(case: Case) -> pd.DataFrame:
    """The rules a case runs under, in words: what is physical, what is a planning prior, what is assumed."""
    pool_def = pools(case.ship_routes)
    routing = ("any order ships from Reno or the PDC" if len(pool_def) == 1 else
               "; ".join(f"{' + '.join(CUSTOMER_NAME[c] for c in p['customers'])} from {SHORT[p['stock'][0]]}"
                         for p in pool_def.values()))
    counted = ("all stock against all demand" if len(pool_def) == 1 else
               "; ".join(f"{SHORT[p['stock'][0]]} stock against {' + '.join(CUSTOMER_NAME[c] for c in p['customers'])} demand"
                         for p in pool_def.values()))
    wk = lambda n: "same week" if n == 0 else f"{n} week" + ("s" if n > 1 else "")
    return pd.DataFrame([
        ("Routing rule", routing, "planning prior"),
        ("Weeks of supply counted on", counted, "planning prior"),
        ("Targets (weeks of supply)", "road 8, 10 from 3 Jan 2028; MTB base 12; MTB carbon 15", "brief"),
        ("Build time", wk(case.build_weeks), "lead time"),
        ("Reno → PDC transfer", wk(case.transfer_weeks), "lead time"),
        ("The plan decides", " and ".join({"make": "builds", "move": "transfers to the PDC"}[k] for k in case.decides),
         "model"),
        ("Shipping", "orders ship as soon as stock exists, oldest first", "assumption"),
    ], columns=["Rule", "Setting", "Kind"])


def lead_weeks(case: Case, pool: dict) -> int:
    """Weeks from using line capacity to stock that can ship from this pool."""
    return case.build_weeks + (0 if "RENO" in pool["stock"] else case.transfer_weeks)


def held_from(ok: pd.DataFrame) -> pd.Series:
    """First week from which a condition holds to the end; NaN if it fails in the last week."""
    last_fail = ok.apply(lambda r: (~r)[~r].index.max() if (~r).any() else 0, axis=1)
    return (last_fail + 1).where(last_fail < ok.columns.max())


def on_time(flows: dict) -> pd.DataFrame:
    """Demand shipped in the week it arrives (oldest orders ship first)."""
    weeks = list(flows["shipped"].columns)
    prev_open = flows["open_orders"][[t - 1 for t in weeks]].set_axis(weeks, axis=1)
    return flows["shipped"] - np.minimum(flows["shipped"], prev_open)


def scorecard(R: dict) -> dict:
    obj, ok, f = R["obj"], R["at_target"], R["flows"]
    date = obj.weeks.set_index("t")["week_start"]
    held = held_from(ok)
    open_total = f["open_orders"].sum()
    cleared = held_from(pd.DataFrame([open_total[list(ok.columns)] < 0.5]))[0]
    return {
        "Bikes built": int(R["builds"].values.sum()),
        "Bikes transferred to the PDC": int(R["moves"].values.sum()),
        "Positions at target (share of position-weeks)": float(ok.values.mean()),
        "Position-weeks below target": int((~ok).values.sum()),
        "All targets held from": date[int(held.max())] if held.notna().all() else None,
        "Open orders cleared from": date[int(cleared)] if pd.notna(cleared) else None,
        "On-time fill rate": float(on_time(f).values.sum() / f["demand"].values.sum()),
        "Average bikes in transit": float(R["transit"].sum().mean()),
    }


def held_by_line(R: dict) -> pd.DataFrame:
    """Week each line's positions hold target from, per pool."""
    held = held_from(R["at_target"])
    date = R["obj"].weeks.set_index("t")["week_start"]
    out = held.groupby([R["line"], held.index.get_level_values("pool")]).max().map(lambda t: date[int(t)])
    return out.unstack()


def checks(R: dict) -> pd.DataFrame:
    """Checks on a case's plan, computed from the run."""
    case, obj, lp, X = R["case"], R["obj"], R["lp"], R["X"]
    weeks = list(R["target_units"].columns)
    f = R["flows"]
    pools_net = R["net"].groupby("item").sum()
    total = rtn.net_position(obj, X).loc[pools_net.index]
    rollup = np.abs((pools_net + R["transit"].reindex(pools_net.index).fillna(0)).values - total.values).max()
    cap = X[X.index.str.startswith("capacity|")].loc[:, weeks]
    full_to = (cap < 0.5).cumprod(axis=1).astype(bool)
    below = ~R["at_target"]
    unexplained = 0
    for key in below.index:
        lead = lead_weeks(case, R["pools"][key[1]])
        for t in below.columns[below.loc[key]]:
            if t - lead >= 1 and not full_to.at[f"capacity||RENO/{R['line'][key]}", t - lead]:
                unexplained += 1
    closure = np.abs(rtn.levels(obj, lp.runs).values - lp.levels.values).max()
    rows = [
        ("Whole bikes, none negative", "", bool((R["runs"].values == np.round(R["runs"].values)).all()
                                                and R["runs"].values.min() >= 0)),
        ("Capacity never exceeded; no stock level below zero", f"lowest level {X.values.min():.0f}", X.values.min() >= -1e-9),
        ("Closure: LP levels = the object's equation run with the LP's decisions", f"{closure:.1e}", closure < 1e-6),
        ("Rollup: pool positions + in transit = total net inventory", f"difference {rollup:.0f}", rollup < 1e-6),
        ("Shipping projection: nothing negative; on hand − open orders = net inventory", "",
         bool(min(f["on_hand"].values.min(), f["open_orders"].values.min(), f["shipped"].values.min()) >= -1e-9
              and np.abs((f["on_hand"] - f["open_orders"] - R["net"]).values).max() < 1e-9)),
        ("Below target only when the line ran full every week up to the lead time before",
         f"{int(below.values.sum())} position-weeks below, {unexplained} unexplained", unexplained == 0),
    ]
    return pd.DataFrame(rows, columns=["check", "value", "pass"])
