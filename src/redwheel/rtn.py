"""The RTN object: resources, tasks, arrows, and the numbers on them.

Generic. Nothing here knows about bikes or Redwheel; `aux_fns.build_object` maps Redwheel onto it.

    resource  (kind, item, location)      has a level each week
    task      (kind, item, name)          runs some number of times each week
    arrow     (task, resource, amount, delay)

    level[r, t] = carry[r] * level[r, t-1]
                + sum over arrows into r:  amount * runs[task, t - delay]
                + arrival[r, t]

    0 <= runs[task, t] <= run_max[task, t]          (no limit where run_max is blank)

Weeks t = 1..H. t = 0 is the opening level. A level is the quantity at the end of week t.
Arrivals may be known past the plan, for weeks H+1..T (the outlook). Nothing is decided there; a target that
looks ahead from late in the plan reads them.

The numbers on the object, six in all: on a resource its opening level, its arrivals and its carry; on an arrow its
amount and its delay; on a task its run limit, the most it can run in a week (e.g. none of a bike while its parts are
missing). Carry is fixed by the resource's kind; the others are data.

One more fact, which the equation does not use: when the opening orders are due (`due`). It splits an order
resource's opening level by date, as far as the data knows: the week each order is due, or, for an order that
carries no date, when it was placed. It changes no level. A plan that serves overdue orders first reads it
(`redwheel.walk`).
"""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import numpy as np
import pandas as pd

KINDS = ("inventory", "capacity", "order")
CARRY = {"inventory": True, "order": True, "capacity": False}   # unused capacity is lost

# Convention 1: which resource kinds a location class holds, and whether stock there is ours.
LOCATION_CLASSES = {
    "factory":             {"holds": {"inventory"},          "ours": True},
    "production_line":     {"holds": {"capacity"},           "ours": False},
    "distribution_center": {"holds": {"inventory"},          "ours": True},
    "in_transit":          {"holds": {"inventory"},          "ours": True},
    "customer":            {"holds": {"order"},              "ours": False},
    "dealer":              {"holds": {"order", "inventory"}, "ours": False},
}


@dataclass
class RTN:
    # descriptions: read for generating, selecting and reporting; never by the equation
    items: pd.DataFrame       # item, + attributes
    locations: pd.DataFrame   # location_id, location_class, parent, ours, + attributes
    weeks: pd.DataFrame       # t (1..H), week_start
    # the object
    resources: pd.DataFrame   # resource_id, kind, item, location, carry
    tasks: pd.DataFrame       # task_id, kind, item
    arrows: pd.DataFrame      # task_id, resource_id, amount, delay
    opening: pd.Series        # resource_id -> level at t = 0
    arrivals: pd.DataFrame    # resource_id x t (1..H): what comes from outside
    outlook: pd.DataFrame | None = None   # resource_id x t (H+1..T): arrivals known after the plan (orders only)
    run_max: pd.DataFrame | None = None   # task_id x t (1..H): the most a task can run that week; NaN = no limit
    due: pd.DataFrame | None = None       # when the opening orders are due: resource_id, qty, due, placed (DUE_COLUMNS)

# `due`: one row per group of opening orders on an order resource.
#   qty     how many
#   due     the plan week the order is due; 0 or less = before the plan (already due); blank = it carries no date
#   placed  when it was placed, in weeks from the start of week 1 (so never above 0; -1.5 = ten and a half days before)
# Orders in the opening level that the table does not list are due at once. None = no dates known: all are.
DUE_COLUMNS = ["resource_id", "qty", "due", "placed"]


def resource_id(kind: str, item: str | None, location: str) -> str:
    return f"{kind}|{item or ''}|{location}"


def task_id(kind: str, item: str, name: str) -> str:
    return f"{kind}|{item}|{name}"


def transit_location(origin: str, destination: str) -> str:
    return f"{origin}>{destination}"


# ---------- generation (conventions) ----------

def generate_resources(items: pd.DataFrame, locations: pd.DataFrame) -> pd.DataFrame:
    """Convention 1: every item x every location that holds inventory / orders;
    one capacity resource per location that holds capacity."""
    rows = []
    for loc in locations.itertuples():
        holds = LOCATION_CLASSES[loc.location_class]["holds"]
        if "capacity" in holds:
            rows.append(("capacity", None, loc.location_id))
        for kind in ("inventory", "order"):
            if kind in holds:
                rows += [(kind, i, loc.location_id) for i in items["item"]]
    r = pd.DataFrame(rows, columns=["kind", "item", "location"])
    r.insert(0, "resource_id", [resource_id(*row) for row in rows])
    r["carry"] = r["kind"].map(CARRY)
    return r


def generate_tasks(routing: pd.DataFrame, routes: pd.DataFrame,
                   items: pd.DataFrame, locations: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Convention 2: three task templates.

    routing: item, line, output, capacity_per_unit, delay       -> one make task per row
    routes:  origin, destination, delay                         -> per item: a fulfil task if the
             destination holds orders, otherwise a move task through the route's in-transit location
    """
    cls = locations.set_index("location_id")["location_class"]
    tasks, arrows = [], []

    def add(kind, item, name, arrow_list):
        tid = task_id(kind, item, name)
        tasks.append((tid, kind, item))
        arrows.extend((tid, rid, amount, delay) for rid, amount, delay in arrow_list)

    for r in routing.itertuples():
        add("make", r.item, r.line, [
            (resource_id("capacity", None, r.line), -r.capacity_per_unit, 0),
            (resource_id("inventory", r.item, r.output), +1, r.delay),
        ])

    for r in routes.itertuples():
        fulfil = "order" in LOCATION_CLASSES[cls[r.destination]]["holds"]
        name = transit_location(r.origin, r.destination)
        for item in items["item"]:
            if fulfil:
                add("fulfil", item, name, [
                    (resource_id("inventory", item, r.origin), -1, 0),
                    (resource_id("order", item, r.destination), -1, r.delay),
                ])
            else:
                add("move", item, name, [
                    (resource_id("inventory", item, r.origin), -1, 0),
                    (resource_id("inventory", item, name), +1, 0),
                    (resource_id("inventory", item, name), -1, r.delay),
                    (resource_id("inventory", item, r.destination), +1, r.delay),
                ])

    return (pd.DataFrame(tasks, columns=["task_id", "kind", "item"]),
            pd.DataFrame(arrows, columns=["task_id", "resource_id", "amount", "delay"]))


# ---------- integrity ----------

def validate(obj: RTN) -> None:
    """Raise if the object is not internally consistent. Says nothing about whether it is *right*."""
    res, tsk, arr = obj.resources, obj.tasks, obj.arrows
    loc = obj.locations.set_index("location_id")

    def need(ok, msg):
        if not ok:
            raise ValueError(msg)

    need(res["resource_id"].is_unique, "duplicate resource_id")
    need(tsk["task_id"].is_unique, "duplicate task_id")
    need(res["kind"].isin(KINDS).all(), "unknown resource kind")
    need((res["carry"] == res["kind"].map(CARRY)).all(), "carry does not match kind")
    need(res["location"].isin(loc.index).all(), "resource at unknown location")
    allowed = [k in LOCATION_CLASSES[loc.at[l, "location_class"]]["holds"]
               for k, l in zip(res["kind"], res["location"])]
    need(all(allowed), "resource kind not allowed at its location class")
    has_item = res["kind"] != "capacity"
    need(res.loc[has_item, "item"].isin(obj.items["item"]).all(), "resource with unknown item")
    need(res.loc[~has_item, "item"].isna().all(), "capacity resource with an item")

    need(arr["task_id"].isin(tsk["task_id"]).all(), "arrow from unknown task")
    need(arr["resource_id"].isin(res["resource_id"]).all(), "arrow to unknown resource")
    need((arr["amount"] != 0).all(), "arrow with zero amount")
    need((arr["delay"] >= 0).all() and (arr["delay"] % 1 == 0).all(), "delay must be a whole number >= 0")
    need(tsk["task_id"].isin(arr["task_id"]).all(), "task with no arrows")

    weeks = list(obj.weeks["t"])
    need(weeks == list(range(1, len(weeks) + 1)), "weeks must be numbered 1..H")
    need(obj.opening.index.equals(pd.Index(res["resource_id"])), "opening not indexed by resources")
    need((obj.opening >= 0).all(), "negative opening level")
    need((obj.opening[res.set_index("resource_id")["kind"] == "capacity"] == 0).all(),
         "capacity has no opening level")
    need(obj.arrivals.index.equals(pd.Index(res["resource_id"])), "arrivals not indexed by resources")
    need(list(obj.arrivals.columns) == weeks, "arrivals columns must be weeks 1..H")
    need((obj.arrivals.values >= 0).all(), "negative arrival")
    if obj.outlook is not None:
        H, out = len(weeks), obj.outlook
        need(out.index.equals(pd.Index(res["resource_id"])), "outlook not indexed by resources")
        need(len(out.columns) > 0 and list(out.columns) == list(range(H + 1, H + 1 + len(out.columns))),
             "outlook columns must be weeks H+1..T")
        need((out.values >= 0).all(), "negative arrival in the outlook")
        need((out[(res["kind"] != "order").to_numpy()].values == 0).all(),
             "outlook arrivals on a resource that is not an order")
    if obj.run_max is not None:
        lim = obj.run_max
        need(lim.index.equals(pd.Index(tsk["task_id"])), "run limits not indexed by tasks")
        need(list(lim.columns) == weeks, "run limit columns must be weeks 1..H")
        v = lim.to_numpy(float)
        need((np.isnan(v) | (v >= 0)).all(), "negative run limit")
    if obj.due is not None:
        d = obj.due
        need(list(d.columns) == DUE_COLUMNS, f"the due table's columns must be {DUE_COLUMNS}")
        orders = set(res.loc[res["kind"] == "order", "resource_id"])
        need(set(d["resource_id"]) <= orders, "the due table lists a resource that is not an order")
        qty, due, placed = (d[c].to_numpy(float) for c in ("qty", "due", "placed"))
        need((qty > 0).all(), "the due table has a row with no quantity")
        need((np.isnan(due) | (due % 1 == 0)).all(), "a due week must be a whole week, or blank")
        need((np.isfinite(placed) & (placed <= 0)).all(), "an opening order must have been placed before the plan starts")
        over = d.groupby("resource_id")["qty"].sum() - obj.opening
        over = over[over > 1e-9]
        need(over.empty, "the due table lists more orders than the opening level on " + ", ".join(over.index[:3]))


# ---------- the equation ----------

def levels(obj: RTN, runs: pd.DataFrame | None = None) -> pd.DataFrame:
    """Roll the equation forward. runs: task_id x t (1..H), missing = 0. Returns resource_id x t (0..H).

    A run whose arrow lands after week H has no effect inside the horizon."""
    H = len(obj.weeks)
    rid, tid = obj.resources["resource_id"], obj.tasks["task_id"]
    N = np.zeros((len(tid), H))
    if runs is not None:
        if not runs.index.isin(tid).all():
            raise ValueError("runs for unknown task")
        if not pd.Index(runs.columns).isin(range(1, H + 1)).all():
            raise ValueError("runs outside weeks 1..H")
        if (runs.values < 0).any():
            raise ValueError("negative runs")
        N = runs.reindex(index=tid, columns=range(1, H + 1)).fillna(0).to_numpy(float)

    # Each arrow as positions: which resource row, which task row, its amount and delay.
    r_pos = pd.Series(range(len(rid)), index=rid)[obj.arrows["resource_id"]].to_numpy()
    t_pos = pd.Series(range(len(tid)), index=tid)[obj.arrows["task_id"]].to_numpy()
    amount = obj.arrows["amount"].to_numpy(float)
    delay = obj.arrows["delay"].to_numpy(int)

    carry = obj.resources["carry"].to_numpy(float)
    A = obj.arrivals.to_numpy(float)
    X = np.zeros((len(rid), H + 1))
    X[:, 0] = obj.opening.to_numpy(float)
    for t in range(1, H + 1):
        X[:, t] = carry * X[:, t - 1] + A[:, t - 1]
        src = t - delay                                   # the week whose runs land in week t
        live = src >= 1
        np.add.at(X[:, t], r_pos[live], amount[live] * N[t_pos[live], src[live] - 1])
    return pd.DataFrame(X, index=rid, columns=range(0, H + 1))


def net_position(obj: RTN, X: pd.DataFrame) -> pd.DataFrame:
    """Per item: inventory at every location that is ours - orders at every location. item x t."""
    res = obj.resources.set_index("resource_id")
    ours = res["location"].map(obj.locations.set_index("location_id")["ours"])
    sign = np.where((res["kind"] == "inventory") & ours, 1.0, np.where(res["kind"] == "order", -1.0, 0.0))
    return X.mul(sign, axis=0).groupby(res["item"]).sum()


def run_limits(obj: RTN) -> pd.DataFrame:
    """The run limit of every task in every week, task_id x t (1..H); NaN where there is none."""
    if obj.run_max is not None:
        return obj.run_max
    return pd.DataFrame(np.nan, index=obj.tasks["task_id"].to_numpy(), columns=list(obj.weeks["t"]))


def over_limit(obj: RTN, runs: pd.DataFrame) -> pd.DataFrame:
    """How far runs go above their limits (0 where within, or where there is no limit). Same shape as runs."""
    lim = run_limits(obj).reindex(index=runs.index, columns=runs.columns)
    return (runs - lim).clip(lower=0).fillna(0)


def arrivals_all(obj: RTN) -> pd.DataFrame:
    """Arrivals for every week they are known: the plan (1..H) and the outlook (H+1..T). resource_id x t."""
    return obj.arrivals if obj.outlook is None else pd.concat([obj.arrivals, obj.outlook], axis=1)


def order_arrivals(obj: RTN, positions: dict) -> pd.DataFrame:
    """The demand each position faces: arrivals onto its order resources, weeks 1..T. position x t.
    positions: {key: {resource_id: sign}}, as the targets are set on (see engine.decide)."""
    A = arrivals_all(obj)
    orders = set(obj.resources.loc[obj.resources["kind"] == "order", "resource_id"])
    out = pd.DataFrame([A.loc[[r for r in members if r in orders]].sum() for members in positions.values()])
    out.index = (pd.MultiIndex.from_tuples(positions.keys()) if all(isinstance(k, tuple) for k in positions)
                 else pd.Index(positions.keys()))
    return out


def weeks_of_supply(net: pd.DataFrame, demand: pd.DataFrame) -> pd.DataFrame:
    """Forward cover: how many future weeks of demand the net position covers, at the end of week t.

    net:    item x t (0..H)            e.g. net_position(obj, X)
    demand: item x t (1..T), T >= H    forecast per week, may run past the plan horizon
    Walks forward from week t+1, whole weeks then a fraction of the next. A negative net position
    (backlog) gives a negative value: how many future weeks of demand the backlog equals.
    So for N >= 0:  weeks_of_supply >= N  exactly when  net >= demand[t+1] + ... + demand[t+N].
    Capped at the weeks of demand available after t.
    """
    T = demand.columns.max()
    out = pd.DataFrame(index=net.index, columns=net.columns, dtype=float)
    for item in net.index:
        cum = np.concatenate([[0.0], demand.loc[item, range(1, T + 1)].cumsum().to_numpy(float)])
        for t in net.columns:
            ahead = cum[t:] - cum[t]                      # demand from t+1 to t+k, k = 0..T-t
            n = net.at[item, t]
            out.at[item, t] = np.sign(n) * np.interp(abs(n), ahead, np.arange(len(ahead)))
    return out


def utilisation(obj: RTN, X: pd.DataFrame) -> pd.DataFrame:
    """Share of each capacity resource used per week: 1 - level left / capacity arrived. cap x t (1..H).
    A week with no capacity (e.g. a line down) has no share: NaN."""
    cap = obj.resources.loc[obj.resources["kind"] == "capacity", "resource_id"]
    arrived = obj.arrivals.loc[cap]
    return 1 - X.loc[cap, arrived.columns] / arrived.where(arrived > 0)


# ---------- graph view ----------

def to_networkx(obj: RTN) -> nx.MultiDiGraph:
    """Static graph: resource and task nodes, one edge per arrow. An arrow that takes from a
    resource points resource -> task; an arrow that adds to a resource points task -> resource."""
    g = nx.MultiDiGraph()
    for r in obj.resources.itertuples():
        g.add_node(r.resource_id, node="resource", kind=r.kind, item=r.item, location=r.location)
    for t in obj.tasks.itertuples():
        g.add_node(t.task_id, node="task", kind=t.kind, item=t.item)
    for a in obj.arrows.itertuples():
        u, v = (a.resource_id, a.task_id) if a.amount < 0 else (a.task_id, a.resource_id)
        g.add_edge(u, v, amount=a.amount, delay=a.delay)
    return g
