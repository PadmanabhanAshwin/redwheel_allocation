"""Events in plain words, and the three forms that make them.

An event is a `Change` (redwheel.changes): an edit to a few of the object's numbers, for one scenario. Nothing here
plans, checks a plan or edits the object; `changes.check` and `changes.apply` do that. This module only
  - builds a Change from what a planner enters (a line, a date, a number of weeks, a percentage),
  - says a Change in words and dates,
  - finds which lines a Change touches, and what differs between two lists of changes.

A date picks the plan week that contains it (week 1 starts on the plan's first Monday, 7 Sep 2026), and "n weeks"
means n whole plan weeks from there."""
from __future__ import annotations

import datetime as dt
import difflib
import json

import pandas as pd

from planner2.charts import LINE_WORDS
from planner2.components import CUSTOMERS, SITES
from redwheel import changes as ch
from redwheel.changes import Change
from redwheel.config import LINES, PLAN_START
from ui import SKU, obj as BASE_OBJECT

START = PLAN_START.date()
CHANNELS = {"dtc": "Web orders", "dealer": "Dealer orders", "commercial": "Commercial orders"}   # the `channel` column
PLAIN = {"changes no number": "it would change nothing (the numbers it selects already have that value)"}


# ---------------- plan weeks and dates ----------------

def week_start(t: int) -> dt.date:
    """The Monday of plan week t (also for the forecast weeks after the plan)."""
    return START + dt.timedelta(weeks=int(t) - 1)


def week_of(day: dt.date) -> int:
    """The plan week a date falls in."""
    return (day - START).days // 7 + 1


def when(c: Change) -> str:
    """When a change applies: 'weeks of 1 Mar to 15 Mar 2027', 'week of 1 Mar 2027', or 'at the snapshot'."""
    if c.from_t is None:
        return "at the snapshot"
    a, b = week_start(c.from_t), week_start(c.to_t)
    if a == b:
        return f"week of {a:%-d %b %Y}"
    return f"weeks of {a:%-d %b}{f' {a:%Y}' if a.year != b.year else ''} to {b:%-d %b %Y}"


# ---------------- a change in words ----------------

def _list(v) -> list:
    return list(v) if isinstance(v, (list, tuple, set)) else [v]


def _and(names: list) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def subject(c: Change) -> str:
    """What a change is about, in a planner's words ('MTB carbon line capacity', 'Dealer orders for RW-4418')."""
    s = c.select if isinstance(c.select, dict) else {}
    kind, rest = s.get("kind"), {k: v for k, v in s.items() if k != "kind"}
    if kind == "capacity" and set(rest) <= {"location"}:
        lines = [str(x).split("/")[-1] for x in _list(rest["location"])] if rest else []
        names = [LINE_WORDS.get(x, x) for x in lines]
        return ("All lines' capacity" if not names else f"{names[0]} line capacity" if len(names) == 1
                else f"{_and(names)} lines' capacity")
    if kind == "order" and set(rest) <= {"item", "location", "line_id", "channel"}:
        chans = ([CUSTOMERS.get(x, str(x)) for x in _list(rest["location"])] if "location" in rest else []) + \
                ([CHANNELS.get(x, str(x)) for x in _list(rest["channel"])] if "channel" in rest else [])
        extra = ([f"for {_and([str(x) for x in _list(rest['item'])])}"] if "item" in rest else []) + \
                ([f"for {_and([LINE_WORDS.get(x, x) for x in _list(rest['line_id'])])} SKUs"] if "line_id" in rest else [])
        return " ".join([_and(chans) if chans else ("Orders" if extra else "All orders")] + extra)
    if kind == "inventory" and set(rest) <= {"item", "location"}:
        items = _and([str(x) for x in _list(rest["item"])]) if "item" in rest else "all SKUs"
        sites = _and([SITES.get(x, str(x)) for x in _list(rest["location"])]) if "location" in rest else "all sites"
        return f"Stock of {items} at {sites}"
    return " ".join([str(kind)] + [f"{k} {_and([str(x) for x in _list(v)])}" for k, v in rest.items()])


def effect(c: Change) -> str:
    """What a change does to each number: 'set to 0', '+30%', '-200'."""
    v = float(c.value)
    if c.op == "set":
        return f"set to {v:,g}"
    if c.op == "add":
        return f"{v:+,g}"
    pct = f"{(v - 1) * 100:+.2f}".rstrip("0").rstrip(".")
    return f"{pct}%"


def title(c: Change) -> str:
    """One line: subject · when · effect."""
    return f"{subject(c)} · {when(c)} · {effect(c)}"


def name_hint(c: Change) -> str:
    """A short name for a scenario that is made of this change."""
    s = c.select if isinstance(c.select, dict) else {}
    if c.field == "arrival" and s.get("kind") == "capacity" and c.op == "set" and c.value == 0:
        return f"{subject(c).removesuffix(' capacity')} down from {week_start(c.from_t):%-d %b %Y}"
    return f"{subject(c)} {effect(c)}"


def lines_of(c: Change, obj) -> list:
    """The lines (in plan order) whose capacity, orders or stock a change touches, read off the resources it selects."""
    ids, _ = ch.selected(obj, c.select)
    res = obj.resources.set_index("resource_id")
    found = set()
    for r in ids:
        item, loc = res.at[r, "item"], res.at[r, "location"]
        if item is not None and item in SKU.index:
            found.add(SKU.at[item, "line_id"])
        elif isinstance(loc, str) and loc.split("/")[-1] in LINES:
            found.add(loc.split("/")[-1])
    return [ln for ln in LINES if ln in found]


# ---------------- a list of changes ----------------

def table(changes, report: pd.DataFrame | None = None) -> pd.DataFrame:
    """Event | Change | Numbers changed | From | To | Why, one row per change. With the change report from
    `changes.apply`, the numbers changed and their totals before and after are filled in."""
    rows = []
    for i, c in enumerate(changes):
        r = report.iloc[i] if report is not None and i < len(report) else None
        rows.append({"Event": f"{subject(c)} · {when(c)}", "Change": effect(c),
                     "Numbers changed": int(r["cells"]) if r is not None else None,
                     "From": f"{r['before']:,.0f} bikes" if r is not None else "",
                     "To": f"{r['after']:,.0f} bikes" if r is not None else "", "Why": c.reason})
    return pd.DataFrame(rows, columns=["Event", "Change", "Numbers changed", "From", "To", "Why"])


def _key(c: Change) -> str:
    """What makes two changes the same event: the same edit to the same resources (how the selection was spelled, and
    the reason, do not count)."""
    ids, _ = ch.selected(BASE_OBJECT, c.select)
    return json.dumps([c.field, ids or c.select, c.op, c.value, c.from_t, c.to_t], sort_keys=True, default=str)


def same(old, new) -> bool:
    """Whether two lists of changes make the same edits, in the same order."""
    return differences(old, new).empty


def moves(old, new) -> list:
    """[("removed", change), ("added", change), ...]: the events only in `old` and only in `new`, in list order. The
    order of changes counts: a later change sees the result of an earlier one."""
    old, new = list(old), list(new)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, [_key(c) for c in old], [_key(c) for c in new],
                                                      autojunk=False).get_opcodes():
        out += [("removed", c) for c in (old[i1:i2] if op in ("delete", "replace") else [])]
        out += [("added", c) for c in (new[j1:j2] if op in ("insert", "replace") else [])]
    return out


def differences(old, new) -> pd.DataFrame:
    """Setting | From | To | Why, one row per event only in `old` (removed) or only in `new` (added), in the same
    shape as the settings changes, so both read as one list."""
    rows = [(f"Event · {subject(c)} · {when(c)}", effect(c), "removed", c.reason) if what == "removed" else
            (f"Event · {subject(c)} · {when(c)}", "none", effect(c), c.reason) for what, c in moves(old, new)]
    return pd.DataFrame(rows, columns=["Setting", "From", "To", "Why"])


def problem(obj, changes) -> str | None:
    """The first rule this list of changes breaks, in words, or None. The list is checked as a whole, in order."""
    errs = ch.check(obj, list(changes))
    if not errs:
        return None
    first = errs[0]
    first = first.split("): ", 1)[-1] if "): " in first else first
    return PLAIN.get(first, first)


# ---------------- the forms ----------------

def line_down(line: str, first_day: dt.date, n_weeks: int, percent: int = 0, note: str = "") -> Change:
    """A line's capacity at `percent` % of normal (0 = down) for n whole plan weeks from the week of first_day."""
    a = week_of(first_day)
    op, value = ("set", 0) if percent == 0 else ("scale", round(percent / 100, 9))
    return Change("arrival", {"kind": "capacity", "location": f"RENO/{line}"}, op, value, a, a + int(n_weeks) - 1,
                  note.strip())


def demand_change(scope: str, channel: str | None, percent: float, first_day: dt.date, n_weeks: int,
                  note: str = "") -> Change:
    """Orders arriving up or down by `percent` % for n whole weeks. scope: 'all', a line id, or a SKU; channel: a
    customer location (WEB, DEALERS, COMMERCIAL) or None for all."""
    sel = {"kind": "order"}
    if scope in LINES:
        sel["line_id"] = scope
    elif scope != "all":
        sel["item"] = scope
    if channel:
        sel["location"] = channel
    a = week_of(first_day)
    return Change("arrival", sel, "scale", round(1 + percent / 100, 9), a, a + int(n_weeks) - 1, note.strip())


def stock_correction(sku: str, site: str, bikes: int, note: str = "") -> Change:
    """The stock counted at the snapshot is off by `bikes` (negative: fewer than the books say)."""
    return Change("opening", {"kind": "inventory", "item": sku, "location": site}, "add", int(bikes), None, None,
                  note.strip())
