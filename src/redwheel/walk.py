"""A priority order for the plan: a walk over floors.

Generic. Nothing here knows about bikes or Redwheel. Design and a worked example: docs/RANKED_WALK.md.

The solver's standing rule holds every position to its target and, where a line cannot, keeps its items equally
short in weeks. A walk says what comes first in more detail, as ordered steps over floors:

    floor   a level a position's net inventory should not fall below, week by week
              "due"     minus the orders not yet due    below it, a customer waits past their date
              "owed"    zero                            below it, a customer waits
              "target"  the weeks-of-supply target      below it, the position is short of cover
            due <= owed <= target, always.
    step    (floor, which items, how they share). "even": the items stay equally short in weeks. "ranked": the
            items in `order` are served one at a time, then the step's other items, evenly.
    walk    the steps in order. The solver makes step 1's shortfall as small as it can and holds it there, then
            step 2, and so on (engine.decide_walk). A scenario with no walk runs the standing rule.

    Walk(steps, no_date_days)
    Step(floor, select, share, order)

    select  which items: {column of the item table: value, or list of values}; every condition must hold;
            {} is every item. An item with several positions (one per pool) keeps them together in its step.

When an order is due (the due floor reads this; nothing else does):
    an opening order with a date        in the week of its date                      (obj.due, a fact)
    an opening order with no date       `no_date_days` after it was placed           (a rule of the walk)
    an opening order obj.due leaves out at once
    an order arriving during the plan   in the week it arrives

Rules. `check` returns every rule a walk breaks; `solver_input` refuses a walk that breaks any.

    1. A step's floor is due, owed or target; its share is even or ranked.
    2. A selection uses columns of the item table and matches at least one item.
    3. A ranked step has an order: items of its selection, each once. An even step has none.
    4. On one floor an item is in at most one step.
    5. Every item is in a target step: nothing is left without its target.
    6. An item's steps climb: due before owed before target.
    7. A ranked target step comes after an owed step with the same items. Without it the first item is built up to
       its target while the customers of the others wait.
    8. no_date_days is a whole number of days, 0 to 365.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from redwheel import rtn

FLOORS = ("due", "owed", "target")                 # lowest first
SHARES = ("even", "ranked")
FLOOR_WORDS = {"due": "Orders past their date", "owed": "All open orders", "target": "Target"}
MAX_DAYS = 365


@dataclass(frozen=True)
class Step:
    floor: str
    select: dict = field(default_factory=dict)
    share: str = "even"
    order: tuple = ()

    def __post_init__(self):                       # one spelling, so a walk read back from a file equals itself
        object.__setattr__(self, "order", tuple(self.order))
        if isinstance(self.select, dict):
            object.__setattr__(self, "select", {c: sorted(v, key=str) if isinstance(v, (list, tuple, set)) else v
                                                for c, v in self.select.items()})


@dataclass(frozen=True)
class Walk:
    steps: tuple = ()
    no_date_days: int = 7                          # an order with no date is due this many days after it was placed

    def __post_init__(self):
        object.__setattr__(self, "steps", tuple(self.steps))

    def __bool__(self) -> bool:                    # a walk with no steps is no walk
        return bool(self.steps)


# ---------- which items a step names ----------

def items_of(obj: rtn.RTN, select) -> tuple[list, list[str]]:
    """(the items a selection names, in the item table's order; what is wrong with the selection)."""
    t = obj.items
    if not isinstance(select, dict):
        return [], ["the selection must be {column: value}"]
    unknown = sorted(c for c in select if c not in t.columns)
    if unknown:
        return [], [f"unknown column(s) {unknown}; the item table has {list(t.columns)}"]
    keep = pd.Series(True, index=t.index)
    for c, v in select.items():
        keep &= t[c].isin(v if isinstance(v, (list, tuple, set)) else [v])
    ids = list(t.loc[keep, "item"])
    return ids, ([] if ids else ["the selection matches no item"])


def _item(key):
    """The item a position belongs to: the key itself, or the first part of an (item, pool) key."""
    return key[0] if isinstance(key, tuple) else key


# ---------- the rules ----------

def check(walk: Walk, obj: rtn.RTN) -> list[str]:
    """Every rule this walk breaks on this object, in words; empty when it can run."""
    errs = []
    d = walk.no_date_days
    if isinstance(d, bool) or not isinstance(d, (int, np.integer)) or not 0 <= d <= MAX_DAYS:
        errs.append(f"no_date_days must be a whole number of days from 0 to {MAX_DAYS}")
    if not walk.steps:
        return errs + ["a walk needs at least one step"]
    members = []
    for n, st in enumerate(walk.steps, start=1):
        e = []
        if not isinstance(st, Step):
            errs.append(f"step {n}: not a step")
            members.append(None)
            continue
        if st.floor not in FLOORS:
            e.append(f"floor must be one of {FLOORS}")
        if st.share not in SHARES:
            e.append(f"share must be one of {SHARES}")
        ids, sel_errs = items_of(obj, st.select)
        e += sel_errs
        if st.share == "ranked":
            if not st.order:
                e.append("a ranked step needs an order")
            if len(set(st.order)) != len(st.order):
                e.append("an item is listed twice in the order")
            outside = [i for i in st.order if i not in ids]
            if outside and not sel_errs:
                e.append(f"{', '.join(map(str, outside))} not in the step's selection")
        elif st.order:
            e.append("an even step has no order")
        errs += [f"step {n} ({step_words(st)}): {x}" for x in e]
        members.append(None if e else ids)
    if errs:
        return errs

    seen = {f: {} for f in FLOORS}                                  # floor -> item -> the step it is in
    for n, (st, ids) in enumerate(zip(walk.steps, members), start=1):
        twice = [i for i in ids if i in seen[st.floor]]
        if twice:
            errs.append(f"step {n}: {', '.join(map(str, twice[:3]))} already in step {seen[st.floor][twice[0]]} "
                        f"on the {st.floor} floor")
        for i in ids:
            seen[st.floor].setdefault(i, n)
    every = list(obj.items["item"])
    missing = [i for i in every if i not in seen["target"]]
    if missing:
        errs.append(f"no target step for {', '.join(map(str, missing))}")
    unordered = [i for i in every if (ns := [seen[f][i] for f in FLOORS if i in seen[f]]) != sorted(ns)]
    if unordered:
        errs.append(f"the steps of {', '.join(map(str, unordered[:3]))} must go due, then owed, then target")
    for n, (st, ids) in enumerate(zip(walk.steps, members), start=1):
        if st.floor == "target" and st.share == "ranked":
            late = [i for i in ids if seen["owed"].get(i, n) >= n]
            if late:
                errs.append(f"step {n}: a ranked target step needs an owed step for the same items before it "
                            f"({', '.join(map(str, late[:3]))} have none)")
    return errs


# ---------- what the solver takes ----------

def resolve(walk: Walk, obj: rtn.RTN, positions) -> list:
    """The walk as the solver takes it: [(floor, [position keys]), ...] in order, every step even. A ranked step
    becomes one step per item in its order, then one for the step's other items."""
    keys_of = {}
    for k in positions:
        keys_of.setdefault(_item(k), []).append(k)
    out = []
    for st in walk.steps:
        ids, _ = items_of(obj, st.select)
        if st.share == "ranked":
            out += [(st.floor, list(keys_of.get(i, []))) for i in st.order]
            ids = [i for i in ids if i not in st.order]
        out.append((st.floor, [k for i in ids for k in keys_of.get(i, [])]))
    return [(f, keys) for f, keys in out if keys]


def not_due(obj: rtn.RTN, no_date_days: int = 7) -> pd.DataFrame:
    """order resource x t (1..H): the opening orders not yet due at the end of week t. A dated order is due in the
    week of its date; one with no date, `no_date_days` after it was placed. Orders that arrive during the plan are
    due the week they arrive, so they never count here."""
    H = len(obj.weeks)
    ids = list(obj.resources.loc[obj.resources["kind"] == "order", "resource_id"])
    out = pd.DataFrame(0.0, index=ids, columns=range(1, H + 1))
    if obj.due is None or obj.due.empty:
        return out
    d = obj.due
    undated = np.floor((d["placed"] * 7 + no_date_days) / 7 + 1e-9) + 1        # the week that day falls in
    week = d["due"].where(d["due"].notna(), undated)
    for (r, w), qty in d.groupby([d["resource_id"], week.rename("week")])["qty"].sum().items():
        if w > 1:                                                              # not yet due until the week before
            out.loc[r, 1:int(min(w - 1, H))] += qty
    return out


def floors(obj: rtn.RTN, positions: dict, target_units: pd.DataFrame, walk: Walk) -> dict:
    """{floor: position x t (1..H)} for the floors the walk uses, on target_units' rows and columns.

    due: a position's net inventory is its stock minus the orders it faces; the due floor leaves out the orders not
    yet due, so it is minus those (with the position's own sign on each order resource)."""
    used = {st.floor for st in walk.steps}
    keys, weeks = list(target_units.index), list(target_units.columns)
    frame = lambda v: pd.DataFrame(v, index=target_units.index, columns=target_units.columns)
    out = {}
    if "due" in used:
        nd = not_due(obj, walk.no_date_days)
        v = np.zeros((len(keys), len(weeks)))
        for n, k in enumerate(keys):
            for r, sign in positions[k].items():
                if r in nd.index:
                    v[n] += sign * nd.loc[r, weeks].to_numpy()
        out["due"] = frame(v)
    if "owed" in used:
        out["owed"] = frame(0.0)
    out["target"] = target_units
    low = out.get("due", out.get("owed", frame(0.0)))
    if (low.to_numpy() > 1e-9).any() or (target_units.to_numpy() < -1e-9).any():
        raise ValueError("the floors are not nested: due <= owed <= target must hold in every position and week")
    return out


def solver_input(case, obj: rtn.RTN, positions: dict, target_units: pd.DataFrame):
    """(floors, steps) for engine.decide_walk, or (None, None) for a scenario with no walk.
    Refuses a walk that breaks a rule. What it returns is guaranteed: the floors are nested, every position is in
    exactly one step on each floor it is in, every position is in a target step, and the keys are target_units'."""
    walk = getattr(case, "walk", None)
    if not walk:
        return None, None
    problems = check(walk, obj)
    if problems:
        raise ValueError(f"scenario {case.key}: the priority order cannot run: " + "; ".join(problems))
    steps = resolve(walk, obj, positions)
    fl = floors(obj, positions, target_units, walk)
    keys = set(target_units.index)
    for f in FLOORS:
        named = [k for g, ks in steps if g == f for k in ks]
        if len(named) != len(set(named)) or not set(named) <= keys or (f == "target" and set(named) != keys):
            raise RuntimeError(f"the resolved walk is wrong on the {f} floor")           # a fault here, not in the walk
    return fl, steps


# ---------- the usual walk ----------

def standard(obj: rtn.RTN, column: str | None = None, ranked: dict | None = None, no_date_days: int = 7) -> Walk:
    """The usual walk: orders past their date, then every open order, then the target, each shared evenly.

    ranked: {value of `column`: (order, orders_too)}. The items with that value reach the target in `order`, one
    at a time. With orders_too their orders are cleared in that order as well: the group is ranked on the due and
    owed floors too (ranking owed alone would do nothing: an even due step before it has already said who waits).
    Everything else stays even."""
    ranked = {g: (tuple(order), bool(too)) for g, (order, too) in (ranked or {}).items()}

    def on(floor, groups):
        steps = [Step(floor, {column: g}, "ranked", ranked[g][0]) for g in groups]
        rest = [g for g in obj.items[column].drop_duplicates() if g not in groups] if groups else []
        if not groups:
            steps.append(Step(floor))
        elif rest:
            steps.append(Step(floor, {column: rest}))
        return steps

    too = [g for g in ranked if ranked[g][1]]
    return Walk((*on("due", too), *on("owed", too), *on("target", list(ranked))), no_date_days)


def ranking(walk: Walk, obj: rtn.RTN, column: str) -> dict | None:
    """The `ranked` that `standard` would need to make this walk, or None if the walk is not of that form."""
    target = {st.select.get(column): st.order for st in walk.steps
              if st.floor == "target" and st.share == "ranked" and list(st.select) == [column]
              and not isinstance(st.select[column], list)}
    owed = {st.select.get(column): st.order for st in walk.steps
            if st.floor == "owed" and st.share == "ranked" and list(st.select) == [column]
            and not isinstance(st.select[column], list)}
    r = {g: (order, g in owed) for g, order in target.items()}
    return r if standard(obj, column, r, walk.no_date_days) == walk else None


# ---------- in words, and as a record ----------

def _who(select: dict) -> str:
    if not select:
        return "every item"
    return "; ".join(f"{c} {', '.join(map(str, v)) if isinstance(v, list) else v}" for c, v in select.items())


def step_words(st: Step, who=None, obj: rtn.RTN | None = None) -> str:
    """A step in words. `who` turns a selection into a name (default: its columns and values). With the object, a
    ranked step that leaves some of its items out of the order says they follow."""
    name = (who or _who)(st.select) if isinstance(st.select, dict) else str(st.select)
    how = "shared evenly"
    if st.share == "ranked":
        how = "in order: " + ", then ".join(map(str, st.order))
        if obj is not None and set(items_of(obj, st.select)[0]) - set(st.order):
            how += ", then the others evenly"
    return f"{FLOOR_WORDS.get(st.floor, st.floor)} · {name} · {how}"


def lines(walk: Walk | None, who=None, obj: rtn.RTN | None = None) -> list[str]:
    """The walk as numbered lines, first step first. No walk: the standing rule, as one line."""
    if not walk:
        return ["1. " + step_words(Step("target"), who)]
    return [f"{n}. {step_words(st, who, obj)}" for n, st in enumerate(walk.steps, start=1)]


def results(plan_steps: list) -> pd.DataFrame:
    """A walked plan's steps as solved (engine.Plan.steps), one row each: its floor, its positions, how short it was
    left (worst: the largest shortfall in weeks, summed over lines and weeks; total: every shortfall in weeks), and
    whether it was met (no shortfall at all)."""
    return pd.DataFrame([{"step": n, "floor": s["floor"], "positions": list(s["positions"]),
                          "worst": float(s["worst"]), "total": float(s["total"]), "met": bool(s["total"] < 1e-6)}
                         for n, s in enumerate(plan_steps, start=1)],
                        columns=["step", "floor", "positions", "worst", "total", "met"])


def to_record(walk: Walk | None) -> dict | None:
    if not walk:
        return None
    return {"no_date_days": int(walk.no_date_days),
            "steps": [{"floor": st.floor, "select": st.select, "share": st.share, "order": list(st.order)}
                      for st in walk.steps]}


def from_record(d: dict | None) -> Walk | None:
    if not d:
        return None
    return Walk(tuple(Step(s["floor"], s.get("select", {}), s.get("share", "even"), tuple(s.get("order", ())))
                      for s in d["steps"]), int(d.get("no_date_days", 7)))
