"""Changes: edits to an object's numbers for one scenario.

Generic. Nothing here knows about bikes or Redwheel. A change edits one kind of number on the object, for a set
of resources or tasks: the opening level or the weekly arrivals of resources, or the weekly run limit of tasks.
`apply` returns a new object and leaves the one it was given untouched; everything after that (the equation, the
targets, the solver, the checks) reads the new object, so a scenario needs no other code.

    Change(field, select, op, value, from_t, to_t, reason)

    field         "opening"  a resource's level at week 0
                  "arrival"  what comes to a resource from outside each week
                  "run_max"  the most a task can run each week (no limit unless set)
    select        which resources or tasks: {column: value, or list of values}; every condition must hold.
                  `kind` is required, one kind per change: a resource kind (inventory, capacity, order) for
                  opening and arrival, a task kind (make, move, ...) for run_max. Other columns: for resources
                  item, location, resource_id and the columns of the item and location description tables (for
                  Redwheel: line_id, channel, ...); for tasks item, task_id and the item description columns.
    op            "set" replaces each selected number, "add" adds to each, "scale" multiplies each
    value         the number
    from_t, to_t  arrival and run_max: the first and last week, both included, both required
    reason        why, in words

Rules. `check` returns every rule a list of changes breaks; `apply` refuses a list that breaks any.

    1. field, op and value are well formed; a set or scale value is not negative.
    2. The selection names one kind, uses only known columns, none of them present in two tables, and matches
       at least one resource or task. The kind fits the field: resources for opening and arrival, tasks for run_max.
    3. opening: no weeks; not on capacity (unused capacity is lost, so it has no opening level).
    4. arrival: 1 <= from_t <= to_t <= T. Weeks after the plan (H+1..T) only on order resources: nothing is
       decided there, and only targets read them.
    5. run_max: set only (a limit is stated, not scaled or added to); 1 <= from_t <= to_t <= H (tasks run only in
       the plan).
    6. No number goes below zero.
    7. A change that alters no number is refused (it is almost always a wrong week or a wrong selection).
    8. Changes apply in the order listed: a later change sees the result of an earlier one.
    9. opening of orders: not below the orders the object's due table lists there (it says when each is due; which
       ones a cut removed would be unknown). Orders added are due at once.

Whole units. With whole=True (the default) the object counts whole units: a set or add value must be a whole
number, and a scaled number is rounded to the nearest whole unit, halves up. With whole=False nothing is rounded.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from redwheel import rtn

FIELDS = ("opening", "arrival", "run_max")
TASK_FIELDS = ("run_max",)                    # fields that sit on tasks; the others sit on resources
OPS = ("set", "add", "scale")


@dataclass(frozen=True)
class Change:
    field: str
    select: dict
    op: str
    value: float
    from_t: int | None = None
    to_t: int | None = None
    reason: str = ""


def describe(c: Change) -> str:
    """One change on one line, in the object's own terms."""
    sel = ", ".join(f"{k}={v}" for k, v in c.select.items()) if isinstance(c.select, dict) else str(c.select)
    value = f"{c.value:g}" if _number(c.value) else str(c.value)
    weeks = "" if c.from_t is None else f" · week {c.from_t}" if c.from_t == c.to_t else f" · weeks {c.from_t}–{c.to_t}"
    return f"{c.field} · {sel} · {c.op} {value}{weeks}"


FIELDS_OF_A_CHANGE = ("field", "select", "op", "value", "from_t", "to_t", "reason")


def to_records(changes) -> list[dict]:
    """Plain dicts, one per change, for saving (JSON)."""
    return [{f: getattr(c, f) for f in FIELDS_OF_A_CHANGE} for c in changes]


def from_records(records) -> tuple:
    """Changes from saved dicts. Refuses a record with missing or unknown keys; the rules are checked when the
    changes are applied, as for any other list."""
    out = []
    for n, r in enumerate(records or [], start=1):
        if not isinstance(r, dict) or set(r) - set(FIELDS_OF_A_CHANGE) or not {"field", "select", "op", "value"} <= set(r):
            raise ValueError(f"saved change {n} is not a change: {r!r}")
        out.append(Change(**r))
    return tuple(out)


# ---------- which resources a selection means ----------

def selection_columns(obj: rtn.RTN, table: str = "resources") -> tuple[dict, set]:
    """({column: value per resource, or per task}, {columns present in more than one table}). A resource can be
    selected on its own columns and on the description of its item and of its location; a task on its own columns
    and on the description of its item."""
    items, locs = obj.items.set_index("item"), obj.locations.set_index("location_id")
    if table == "tasks":
        tsk = obj.tasks.set_index("task_id", drop=False)
        tables = [{c: tsk[c] for c in ("task_id", "kind", "item")},
                  {c: tsk["item"].map(items[c]) for c in items.columns}]
    else:
        res = obj.resources.set_index("resource_id", drop=False)
        tables = [{c: res[c] for c in ("resource_id", "kind", "item", "location")},
                  {c: res["item"].map(items[c]) for c in items.columns},
                  {c: res["location"].map(locs[c]) for c in locs.columns}]
    seen, twice = set(), set()
    for t in tables:
        twice |= seen & set(t)
        seen |= set(t)
    cols = {}
    for t in tables:
        cols.update(t)
    return cols, twice


def task_kinds(obj: rtn.RTN) -> tuple:
    return tuple(dict.fromkeys(obj.tasks["kind"]))


def selected(obj: rtn.RTN, select: dict) -> tuple[list, list]:
    """(resource ids or task ids the selection means, problems with the selection). Its kind says which: a resource
    kind selects resources, a task kind tasks."""
    if not isinstance(select, dict) or not select:
        return [], ["the selection is empty"]
    kind = select.get("kind")
    table = "tasks" if kind in task_kinds(obj) else "resources"
    cols, twice = selection_columns(obj, table)
    errs = []
    if kind not in rtn.KINDS and kind not in task_kinds(obj):
        errs.append(f"the selection must name one kind (resources: {', '.join(rtn.KINDS)}; "
                    f"tasks: {', '.join(task_kinds(obj))})")
    unknown = sorted(k for k in select if k not in cols)
    if unknown:
        errs.append(f"unknown column(s) in the selection: {unknown}")
    both = sorted(k for k in select if k in twice)
    if both:
        errs.append(f"column(s) present in more than one table, so the selection is ambiguous: {both}")
    if errs:
        return [], errs
    index = (obj.tasks["task_id"] if table == "tasks" else obj.resources["resource_id"]).to_numpy()
    keep = pd.Series(True, index=index)
    for k, v in select.items():
        values = list(v) if isinstance(v, (list, tuple, set)) else [v]
        keep &= cols[k].isin(values).to_numpy()
    ids = list(keep.index[keep])
    return ids, ([] if ids else [f"the selection matches no {'task' if table == 'tasks' else 'resource'}"])


# ---------- applying ----------

def _number(v) -> bool:
    return isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool) and math.isfinite(v)


def _run(obj: rtn.RTN, changes: list, whole: bool):
    """Apply in order on copies. Returns (opening, arrivals 1..T, run limits 1..H, report rows, problems). A change
    with a problem is not applied; the ones after it are still checked."""
    H = len(obj.weeks)
    opening = obj.opening.astype(float).copy()
    A = rtn.arrivals_all(obj).astype(float).copy()
    L = rtn.run_limits(obj).astype(float).copy()
    T = int(A.columns.max())
    rows, problems = [], []

    for n, c in enumerate(changes, start=1):
        errs = []
        if c.field not in FIELDS:
            errs.append(f"field must be one of {FIELDS}")
        if c.op not in OPS:
            errs.append(f"op must be one of {OPS}")
        if not _number(c.value):
            errs.append("value must be a number")
        elif c.op in ("set", "scale") and c.value < 0:
            errs.append(f"a {c.op} value cannot be negative")
        elif whole and c.op in ("set", "add") and not float(c.value).is_integer():
            errs.append(f"a {c.op} value must be a whole number")
        ids, sel_errs = selected(obj, c.select)
        errs += sel_errs
        kind = c.select.get("kind") if isinstance(c.select, dict) else None
        on_tasks = kind in task_kinds(obj)
        if c.field in FIELDS and not sel_errs and on_tasks != (c.field in TASK_FIELDS):
            errs.append(f"{c.field} is a number on {'tasks' if c.field in TASK_FIELDS else 'resources'}; "
                        f"the selection names {'tasks' if on_tasks else 'resources'} (kind {kind})")

        if c.field == "opening":
            if c.from_t is not None or c.to_t is not None:
                errs.append("an opening level has no weeks")
            if kind == "capacity":
                errs.append("capacity has no opening level")
        elif c.field == "arrival":
            if not (isinstance(c.from_t, (int, np.integer)) and isinstance(c.to_t, (int, np.integer))):
                errs.append("an arrival change needs a first and a last week")
            elif not 1 <= c.from_t <= c.to_t <= T:
                errs.append(f"weeks must satisfy 1 <= first <= last <= {T}")
            elif kind in rtn.KINDS and kind != "order" and c.to_t > H:
                errs.append(f"weeks after the plan ({H + 1}–{T}) can change only on order resources")
        elif c.field == "run_max":
            if c.op != "set":
                errs.append("a run limit can only be set (not added to or scaled)")
            if not (isinstance(c.from_t, (int, np.integer)) and isinstance(c.to_t, (int, np.integer))):
                errs.append("a run limit needs a first and a last week")
            elif not 1 <= c.from_t <= c.to_t <= H:
                errs.append(f"weeks must satisfy 1 <= first <= last <= {H} (tasks run only in the plan)")

        if not errs:
            if c.field == "opening":
                old = opening.loc[ids].to_numpy()
            else:
                weeks = list(range(int(c.from_t), int(c.to_t) + 1))
                old = (L if c.field == "run_max" else A).loc[ids, weeks].to_numpy()
            new = np.full_like(old, float(c.value)) if c.op == "set" else old + c.value if c.op == "add" else old * c.value
            if whole and c.op == "scale":
                new = np.floor(new + 0.5 + 1e-9)      # halves up; the 1e-9 keeps 84.5 from landing at 84.4999...
            same = (new == old) | (np.isnan(new) & np.isnan(old))       # no limit stays no limit
            dated = (obj.due.groupby("resource_id")["qty"].sum().reindex(ids).fillna(0).to_numpy()
                     if c.field == "opening" and kind == "order" and obj.due is not None else None)
            if (new < 0).any():
                errs.append(f"{int((new < 0).sum())} number(s) would go below zero (lowest {new.min():g})")
            elif dated is not None and (new < dated - 1e-9).any():
                errs.append(f"{int((new < dated - 1e-9).sum())} order level(s) would go below the orders whose dates "
                            "the object knows")
            elif same.all():
                errs.append("changes no number")
            else:
                if c.field == "opening":
                    opening.loc[ids] = new
                elif c.field == "run_max":
                    L.loc[ids, weeks] = new
                else:
                    A.loc[ids, weeks] = new
                rows.append({"change": n, "field": c.field, "op": c.op, "value": c.value, "resources": len(ids),
                             "cells": int((~same).sum()), "before": float(old.sum()), "after": float(new.sum()),
                             "reason": c.reason})       # before is NaN where a run limit had none
        problems += [f"change {n} ({describe(c)}): {e}" for e in errs]
    report = pd.DataFrame(rows, columns=["change", "field", "op", "value", "resources", "cells", "before", "after",
                                         "reason"])
    return opening, A, L, report, problems


def check(obj: rtn.RTN, changes: list, whole: bool = True) -> list[str]:
    """Every reason this list of changes cannot be applied to this object; empty when it can."""
    return _run(obj, changes, whole)[4]


def apply(obj: rtn.RTN, changes: list, whole: bool = True) -> tuple[rtn.RTN, pd.DataFrame]:
    """(a new object with the changes applied, a report with one row per change). The object passed in is not
    modified. The report says how many resources (for a run limit: tasks) and numbers each change touched and their
    total before and after (NaN before where a run limit had none), so what a change did can be read off, not
    assumed."""
    opening, A, L, report, problems = _run(obj, changes, whole)
    if problems:
        raise ValueError("; ".join(problems))
    H = len(obj.weeks)

    def like(new, old):                       # keep whole numbers in the type they came in
        same = whole and np.issubdtype(np.asarray(old).dtype, np.integer)
        return new.astype(np.asarray(old).dtype) if same else new

    arrivals = like(A.loc[:, list(range(1, H + 1))], obj.arrivals.to_numpy())
    outlook = None if obj.outlook is None else like(A.loc[:, list(obj.outlook.columns)], obj.outlook.to_numpy())
    limited = any(c.field == "run_max" for c in changes)        # an object with no limits keeps run_max None
    out = replace(obj, opening=like(opening, obj.opening.to_numpy()).rename(obj.opening.name), arrivals=arrivals,
                  outlook=outlook, run_max=L if limited else obj.run_max)
    rtn.validate(out)
    return out, report
