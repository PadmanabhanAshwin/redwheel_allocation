"""The RTN object: resources, tasks, arrows, and the numbers on them.

Generic. Nothing here knows about bikes or Redwheel; `aux_fns.build_object` maps Redwheel onto it.

    resource  (kind, item, location)      has a level each week
    task      (kind, item, name)          runs some number of times each week
    arrow     (task, resource, amount, delay)

    level[r, t] = carry[r] * level[r, t-1]
                + sum over arrows into r:  amount * runs[task, t - delay]
                + arrival[r, t]

Weeks t = 1..H. t = 0 is the opening level. A level is the quantity at the end of week t.
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
    """Share of each capacity resource used per week: 1 - level left / capacity arrived. cap x t (1..H)."""
    cap = obj.resources.loc[obj.resources["kind"] == "capacity", "resource_id"]
    arrived = obj.arrivals.loc[cap]
    if (arrived.values <= 0).any():
        raise ValueError("utilisation needs capacity > 0 every week")
    return 1 - X.loc[cap, arrived.columns] / arrived


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
