"""Scenarios: a case is a name, a planning-priors table and a list of changes; the same object and solver run each.

`run_case` builds the base object, applies the case's changes to it (a line down, a forecast revised: see
`redwheel.changes`), and from then on reads only that object and the table: lead times go into the network's
delays, the routing rule defines which stock faces which demand (pools), targets are read from the object's order
arrivals, and the LP decides what the table says it decides. Scenario A, the base case, has no changes, runs the
same way and reproduces the frozen base plan exactly (tests/test_base_case.py).
"""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import numpy as np
import pandas as pd

from redwheel import aux_fns, engine, priors, rtn
from redwheel import changes as ch
from redwheel import walk as wk
from redwheel.changes import Change
from redwheel.config import LINES

SITES = ("RENO", "CMH")
CUSTOMERS = ("WEB", "DEALERS", "COMMERCIAL")
ALL_ROUTES = tuple((s, c) for s in SITES for c in CUSTOMERS)


@dataclass(frozen=True, eq=False)
class Case:
    key: str
    name: str
    priors: pd.DataFrame             # every setting the run uses (see redwheel.priors)
    summary: str = ""                # the scenario in one or two sentences
    parent: str = ""                 # the scenario this one was copied from
    changes: tuple = ()              # changes to the object's numbers, applied in order (see redwheel.changes)
    walk: wk.Walk | None = None      # what comes first when a line is short (see redwheel.walk); None: the standing rule

    @property
    def is_base(self) -> bool:
        return self.key == "A"

    @property
    def settings(self) -> dict:
        return priors.settings(self.priors)

    @property
    def ship_routes(self) -> tuple:  # allowed (stock site, customer) pairs
        return self.settings["ship_routes"]

    @property
    def decides(self) -> tuple:      # task kinds the LP decides
        return self.settings["decides"]

    @property
    def build_weeks(self) -> dict:   # {line: weeks from using line capacity to stock at Reno}
        return self.settings["build_weeks"]

    @property
    def transfer_weeks(self) -> int:
        return self.settings["transfer_weeks"]


CASE_A = Case("A", "Scenario A · base case",
              priors.table(ALL_ROUTES, build_weeks=0, transfer_weeks=1, decides=("make",), lines=LINES),
              summary="Stock at Reno and the PDC is pooled against every order, a bike can ship the week it is "
                      "built, and the plan decides builds only.")
CASE_B = Case("B", "Scenario B · web via PDC, others direct",
              priors.table((("RENO", "DEALERS"), ("RENO", "COMMERCIAL"), ("CMH", "WEB")), build_weeks=1,
                           transfer_weeks=1, decides=("make", "move"), lines=LINES),
              summary="Web orders ship from the PDC, which Reno restocks in a week; dealer and commercial orders ship "
                      "direct from Reno. A bike takes a week to build. The plan decides builds and transfers.")
CASES = {c.key: c for c in (CASE_A, CASE_B)}

# Events: scenario A's settings, with the world changed. Weeks are plan weeks (week 1 starts 7 Sep 2026).
# Built in to the planner (planner2) beside A and B. Not in CASES, so the older UIs do not list them.
CASE_E1 = Case("E1", "Scenario E1 · MTB carbon line down three weeks", CASE_A.priors,
               summary="Scenario A, with the MTB carbon line down for the three weeks starting 1, 8 and 15 Mar 2027.",
               parent="A",
               changes=(Change("arrival", {"kind": "capacity", "location": "RENO/mtb-carbon"}, "set", 0, 26, 28,
                               "MTB carbon line down for maintenance, weeks of 1-15 Mar 2027"),))
CASE_E2 = Case("E2", "Scenario E2 · RW-4418 dealer demand up 30%", CASE_A.priors,
               summary="Scenario A, with the dealer forecast for RW-4418 (MTB carbon, size M) up 30% for the weeks "
                       "of 4 Jan to 29 Mar 2027.",
               parent="A",
               changes=(Change("arrival", {"kind": "order", "item": "RW-4418", "channel": "dealer"}, "scale", 1.3,
                               18, 30, "dealer forecast for RW-4418 revised up 30%, weeks of 4 Jan-29 Mar 2027"),))
CASE_E3 = Case("E3", "Scenario E3 · RW-4418 frames late eight weeks", CASE_A.priors,
               summary="Scenario A, with no RW-4418 (MTB carbon, size M) built for the eight weeks starting 25 Oct "
                       "2027: its frames arrive late. The plan knows in advance.",
               parent="A",
               changes=(Change("run_max", {"kind": "make", "item": "RW-4418"}, "set", 0, 60, 67,
                               "frames for RW-4418 late: none for the weeks of 25 Oct to 13 Dec 2027"),))
EVENTS = {c.key: c for c in (CASE_E1, CASE_E2)}
# E3 is kept out of EVENTS (which planner2 lists as built-in) until the planner can show a run limit in words.

# A priority order: scenario A's data and settings, with what comes first stated as a walk (see redwheel.walk).
CASE_P1 = Case("P1", "Scenario P1 · MTB carbon in priority order", CASE_A.priors,
               summary="Scenario A, with a priority order. Orders past their date come first, then every open order, "
                       "then the target. The MTB carbon bikes reach their target one at a time: RW-9304, then "
                       "RW-4418, then RW-6416. An order with no date is due seven days after it was placed.",
               parent="A",
               walk=wk.Walk((wk.Step("due"), wk.Step("owed"),
                             wk.Step("target", {"line_id": "mtb-carbon"}, "ranked", ("RW-9304", "RW-4418", "RW-6416")),
                             wk.Step("target", {"line_id": ["road-base", "road-carbon", "mtb-base"]})), 7))
PRIORITY = {c.key: c for c in (CASE_P1,)}
# Kept out of EVENTS, like E3, until the planner shows a walk.


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


# ---------- whole-bike transfers ----------

def round_moves(obj: rtn.RTN, lp_moves: pd.DataFrame, builds: pd.DataFrame) -> pd.DataFrame:
    """Whole-bike transfers: cumulative LP transfers rounded down, never more than the origin holds once the
    whole-bike builds have landed, and never more than the task's run limit. Week by week, per move task."""
    out = pd.DataFrame(0, index=lp_moves.index, columns=lp_moves.columns, dtype=int)
    limit = rtn.run_limits(obj).reindex(index=lp_moves.index, columns=lp_moves.columns)
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
            if not np.isnan(limit.at[task, t]):
                q = min(q, int(np.floor(limit.at[task, t] + 1e-9)))
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
    """Run one scenario from its priors table. Refuses a table that does not fit the network."""
    m = aux_fns.build_master()
    st = case.settings
    obj = aux_fns.build_object(m, st["build_weeks"], st["transfer_weeks"])
    obj, change_report = ch.apply(obj, list(case.changes))      # the scenario's object; nothing below reads the base
    errs = priors.validate(case.priors, obj)
    if errs:
        raise ValueError(f"scenario {case.key}: " + "; ".join(errs))
    H = len(obj.weeks)
    pool_def = pools(st["ship_routes"])
    sku = m["dim_sku"].set_index("sku")
    pos = positions(obj, pool_def)
    demand = rtn.order_arrivals(obj, pos).rename_axis(["item", "pool"])      # read from the object, outlook included
    item_target = aux_fns.target_wos(m | {"dim_policy": st["dim_policy"]}, obj.weeks)
    tw = pd.DataFrame({t: [item_target.at[k[0], t] for k in pos] for t in item_target.columns}, index=demand.index)
    tu = engine.forward_sum(demand, tw)
    wd = engine.window_demand(tu, tw)               # units short -> weeks short, over the target's own window
    keys = list(pos)
    free = list(obj.tasks.loc[obj.tasks["kind"].isin(st["decides"]), "task_id"])
    limited = rtn.run_limits(obj).notna().any(axis=1)
    inert = sorted(set(limited[limited].index) - set(free))
    if inert:                                   # e.g. a limit on transfers in a scenario where the plan decides none
        raise ValueError(f"scenario {case.key}: a run limit on tasks the plan does not decide would change nothing: "
                         + ", ".join(inert))
    grp = pd.Series({k: sku.at[k[0], "line_id"] for k in keys})
    floors, steps = wk.solver_input(case, obj, pos, tu)      # the scenario's walk, as floors and steps; None without one
    if steps:
        lp = engine.decide_walk(obj, free, tu.loc[keys], wd.loc[keys], grp, floors, steps, positions=pos, w_run=1e-6)
    else:
        lp = engine.decide(obj, free, tu.loc[keys], wd.loc[keys], grp, positions=pos, w_run=1e-6)
    make_ids = [k for k in free if k.startswith("make|")]
    builds = engine.round_runs(obj, lp.runs.loc[make_ids])
    moves = round_moves(obj, lp.runs.loc[[k for k in free if k.startswith("move|")]], builds)
    R = _finish(case, m, obj, pool_def, pos, pd.concat([builds, moves]).astype(float), lp, demand, tw, tu)
    R["weekly_demand"] = wd                         # the divisor the plan used: weeks short = units short / this
    R["walk"] = {"floors": floors, "steps": steps} if steps else None
    R["change_report"] = change_report
    return R


# ---------- describing and scoring a case ----------

SITE_NAME = {"RENO": "Reno", "CMH": "the PDC (Columbus)"}
CUSTOMER_NAME = {"WEB": "web", "DEALERS": "dealer", "COMMERCIAL": "commercial"}
SHORT = {"RENO": "Reno", "CMH": "PDC"}
TARGET_NAME = {"road": "road", "mtb_base": "MTB base", "mtb_carbon": "MTB carbon"}


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
    bw = case.build_weeks
    build = (wk(next(iter(bw.values()))) if len(set(bw.values())) == 1 else
             "; ".join(f"{ln} {wk(n)}" for ln, n in bw.items()))
    pol = case.settings["dim_policy"].sort_values("effective_from", kind="stable")
    targets = "; ".join(
        TARGET_NAME.get(g, g) + " " + ", ".join(f"{w:g}" + ("" if d <= pd.Timestamp(aux_fns.PLAN_START) else
                                                          f" from {d.strftime('%-d %b %Y')}")
                                                for d, w in zip(rows["effective_from"], rows["target_wos"]))
        for g, rows in pol.groupby("target_group", sort=False))
    return pd.DataFrame([
        ("Routing rule", routing, "planning prior"),
        ("Weeks of supply counted on", counted, "planning prior"),
        ("Targets (weeks of supply)", targets, "brief"),
        ("Build time", build, "lead time"),
        ("Reno → PDC transfer", wk(case.transfer_weeks), "lead time"),
        ("The plan decides", " and ".join({"make": "builds", "move": "transfers to the PDC"}[k] for k in case.decides),
         "model"),
        ("Shipping", "orders ship as soon as stock exists, oldest first", "assumption"),
    ], columns=["Rule", "Setting", "Kind"])


def lead_weeks(case: Case, pool: dict, line: str) -> int:
    """Weeks from using a line's capacity to stock that can ship from this pool."""
    return case.build_weeks[line] + (0 if "RENO" in pool["stock"] else case.transfer_weeks)


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


def _feeds(R: dict, key) -> list:
    """The decided tasks that add to a position: its make, and its move when the pool's stock is not at Reno."""
    sku, pool = key
    return [k for k in R["lp"].runs.index if k.split("|")[1] == sku
            and (k.startswith("make|") or ("RENO" not in R["pools"][pool]["stock"] and k.startswith("move|")))]


def walk_served_out_of_order(R: dict) -> int:
    """How often the plan served a later step while an earlier one could still have used the line.

    On the LP's own runs and levels. For each step i, a position s in it below the step's floor in week t, whose
    feeding tasks were not at their run limit in week u = t - lead: every make task that ran in week u on the same
    capacity must have served a position of step i or earlier, i.e. a position it feeds that is at or below that
    step's floor in the week the run lands for it. Counts (task, week) pairs that served no such position. A task
    may feed several positions (in B a bike built at Reno is moved to the PDC), so the test is on what the capacity
    was used for, not on which position the task is named after."""
    walk = R["walk"]
    if not walk:
        return 0
    lp, pos, obj = R["lp"], R["positions"], R["obj"]
    weeks = list(R["target_units"].columns)
    net = position_levels(lp.levels, pos)[weeks]
    limit = rtn.run_limits(obj).reindex(index=lp.runs.index, columns=weeks)
    at_limit = (lp.runs[weeks] >= limit - 1e-6) & limit.notna()
    ran = lp.runs[weeks] > 0.01               # a hundredth of a bike, like the gap below: a held step's slack lets
    lead = {k: lead_weeks(R["case"], R["pools"][k[1]], R["line"][k]) for k in pos}     # the solver leave runs of
    feeds = {k: _feeds(R, k) for k in pos}                                              # a few millionths of a bike
    fed_by = {}                                                           # make task -> positions it feeds
    for k, tasks in feeds.items():
        for task in tasks:
            if task.startswith("make|"):
                fed_by.setdefault(task, []).append(k)
    a = obj.arrows[obj.arrows["resource_id"].str.startswith("capacity|") & obj.arrows["task_id"].isin(lp.runs.index)]
    cap_of = a.set_index("task_id")["resource_id"]
    steps = walk["steps"]
    gap = {}                                                              # (step, position) -> net - floor, by week
    for i, (f_i, members) in enumerate(steps):
        floor = walk["floors"][f_i]
        for s in members:
            gap[(i, s)] = net.loc[[s]].iloc[0] - floor.loc[[s], weeks].iloc[0]

    def served(task, u, i):
        """Did this run in week u serve a position of step i or earlier?"""
        for p in fed_by[task]:
            t_p = u + lead[p]
            if t_p in weeks and any((i2, p) in gap and gap[(i2, p)][t_p] < 0.5 for i2 in range(i + 1)):
                return True
        return False

    bad = set()
    for (i, s), g in gap.items():
        makes = [k for k in feeds[s] if k.startswith("make|")]
        if not makes:
            continue
        rivals = [k for k in cap_of.index if cap_of[k] == cap_of[makes[0]] and k not in makes]
        for t in g.index[g < -0.01]:                                      # a hundredth of a bike: the held step's slack
            u = t - lead[s]
            if u < 1 or at_limit.loc[feeds[s], u].any():
                continue                                                  # could not have been helped that week
            for k in rivals:
                if ran.at[k, u] and not served(k, u, i):
                    bad.add((k, u))
    return len(bad)


def checks(R: dict) -> pd.DataFrame:
    """Checks on a case's plan, computed from the run."""
    case, obj, lp, X = R["case"], R["obj"], R["lp"], R["X"]
    weeks = list(R["target_units"].columns)
    f = R["flows"]
    pools_net = R["net"].groupby("item").sum()
    total = rtn.net_position(obj, X).loc[pools_net.index]
    pooled = {site for p in R["pools"].values() for site in p["stock"]}
    unpooled = pd.DataFrame(0.0, index=pools_net.index, columns=pools_net.columns)
    for site in [s for s in SITES if s not in pooled]:            # a site that serves no orders: stock waits there
        unpooled += X.loc[[rtn.resource_id("inventory", i, site) for i in pools_net.index]].set_axis(pools_net.index)
    rollup = np.abs((pools_net + R["transit"].reindex(pools_net.index).fillna(0) + unpooled).values
                    - total.values).max()
    cap = X[X.index.str.startswith("capacity|")].loc[:, weeks]
    runs, limit = R["runs"], rtn.run_limits(obj).reindex(index=R["runs"].index, columns=weeks)
    at_limit = (runs[weeks] >= limit - 0.5) & limit.notna()          # a task that ran all its limit allowed
    below = ~R["at_target"]
    unexplained = 0
    for key in below.index:
        sku, pool = key
        lead = lead_weeks(case, R["pools"][pool], R["line"][key])
        # A week u could not have added to this position if the line was full, or if the tasks that feed the
        # position (its make, and its move when the pool's stock is not at Reno) were at their limits.
        feed = [k for k in runs.index if k.split("|")[1] == sku
                and (k.startswith("make|") or ("RENO" not in R["pools"][pool]["stock"] and k.startswith("move|")))]
        held_back = (cap.loc[f"capacity||RENO/{R['line'][key]}"] < 0.5) | at_limit.loc[feed].any(axis=0)
        explained_to = held_back.cumprod().astype(bool)                # every week from 1 to u held back
        for t in below.columns[below.loc[key]]:
            if t - lead >= 1 and not explained_to[t - lead]:
                unexplained += 1
    closure = np.abs(rtn.levels(obj, lp.runs).values - lp.levels.values).max()
    whole = R["runs"]
    gap = whole.cumsum(axis=1) - lp.runs.loc[whole.index, whole.columns].cumsum(axis=1)
    below_lp = position_levels(lp.levels, R["positions"])[weeks] < R["target_units"] - 1e-6
    rows = [
        ("Whole bikes, none negative", "", bool((R["runs"].values == np.round(R["runs"].values)).all()
                                                and R["runs"].values.min() >= 0)),
        ("Capacity never exceeded; no stock level below zero", f"lowest level {X.values.min():.0f}", X.values.min() >= -1e-9),
        ("No task runs above its run limit", f"most above {rtn.over_limit(obj, R['runs']).values.max():.0f}",
         rtn.over_limit(obj, R["runs"]).values.max() <= 1e-9),
        ("Whole-bike plan within 1 bike of the LP, cumulative, every task", f"{gap.values.min():.3f} to {gap.values.max():.3f}",
         gap.values.min() > -1 and gap.values.max() < 1),
        ("Rounding to whole bikes adds no missed targets", "", not (below & ~below_lp).values.any()),
        ("Closure: LP levels = the object's equation run with the LP's decisions", f"{closure:.1e}", closure < 1e-6),
        ("Rollup: pool positions + in transit (+ stock at sites serving no orders) = total net inventory",
         f"difference {rollup:.0f}", rollup < 1e-6),
        ("Shipping projection: nothing negative; on hand − open orders = net inventory", "",
         bool(min(f["on_hand"].values.min(), f["open_orders"].values.min(), f["shipped"].values.min()) >= -1e-9
              and np.abs((f["on_hand"] - f["open_orders"] - R["net"]).values).max() < 1e-9)),
        ("Below target only when the line ran full (or the SKU was at its run limit) every week up to the lead time before",
         f"{int(below.values.sum())} position-weeks below, {unexplained} unexplained", unexplained == 0),
    ]
    if R.get("walk"):
        out_of_order = walk_served_out_of_order(R)
        rows.append(("Walk: a later step is served only when every earlier step on the line was met or held back",
                     f"{len(R['walk']['steps'])} steps, {out_of_order} served out of order", out_of_order == 0))
    return pd.DataFrame(rows, columns=["check", "value", "pass"])
