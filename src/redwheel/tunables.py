"""Every tunable of a Redwheel scenario, in one list, each with its form.

A scenario is the data, its settings and its changes (`scenarios.Case`). A tunable is one thing a planner can say is
different, in a planner's words, with where it sits in the model:

    changes the data: one of the object's numbers (changes.py)
        Stock count        the opening level of a SKU's stock at a site
        Line capacity      the arrivals onto a line's capacity: down, slowed, or extra (overtime)
        Demand             the arrivals onto orders: up or down, for a SKU, a line or all, one channel or all
        One-off order      the arrivals onto one SKU's orders from one channel, in one week
        Build limit        the run limit of make tasks: parts late (none) or short (at most n a week)
        Transfer limit     the run limit of move tasks, Reno to the PDC
    changes the plan's rules: a row of the settings table (priors.py)
        Build time         the delay on make edges (weeks from using line capacity to a bike in stock)
        Transfer time      the delay on move edges (Reno to the PDC)
        Ship from          which sites a channel's orders may ship from
        Plan transfers     whether the plan decides transfers to the PDC
        Target             a group's weeks-of-supply target, from a date

Each has a form: the fields to fill in, with their choices, ranges and defaults. Where a built-in event exists, the
defaults are that event (E1, E2, E3). `make` turns a filled form into an Edit; `apply` puts edits on a scenario;
`check` says in words why a scenario with edits cannot run (without planning it); `describe` says any edit or change
in words; `differences` lists what differs between two scenarios; `change_rows` turns a run's change report into
words. Nothing here plans or solves.

Dates: a date picks the plan week that contains it (week 1 starts on 7 Sep 2026); "n weeks" means n whole plan weeks
from there."""
from __future__ import annotations

import datetime as dt
import difflib
import functools
import json
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from redwheel import aux_fns, changes as ch, priors, rtn
from redwheel.changes import Change
from redwheel.config import LINES, PLAN_START

LINE_NAME = {"road-base": "Road base", "road-carbon": "Road carbon", "mtb-base": "MTB base", "mtb-carbon": "MTB carbon"}
CHANNEL_NAME = {"WEB": "Web", "DEALERS": "Dealer", "COMMERCIAL": "Commercial"}
CHANNEL_OF_CODE = {"dtc": "WEB", "dealer": "DEALERS", "commercial": "COMMERCIAL"}    # the `channel` description column
SITE_NAME = {"RENO": "Reno", "CMH": "the PDC"}
GROUP_NAME = {"road": "Road", "mtb_base": "MTB base", "mtb_carbon": "MTB carbon"}
SHIP = {"Reno": ("RENO",), "PDC": ("CMH",), "Either site": ("RENO", "CMH")}
START = PLAN_START.date()


# ---------------- plan weeks and dates ----------------

def week_start(t: int) -> dt.date:
    """The Monday of plan week t (also for the forecast weeks after the plan)."""
    return START + dt.timedelta(weeks=int(t) - 1)


def week_of(day) -> int:
    """The plan week a date falls in."""
    return (pd.Timestamp(day).date() - START).days // 7 + 1


@functools.lru_cache(maxsize=1)
def _master() -> dict:
    return aux_fns.build_master()


@functools.lru_cache(maxsize=1)
def _base() -> rtn.RTN:
    """The base object (default delays). Its resources, tasks and numbers do not depend on the settings."""
    return aux_fns.build_object(_master())


def plan_weeks() -> int:
    return len(_base().weeks)


def last_week() -> int:
    """The last week anything is known: the end of the forecast outlook."""
    return int(rtn.arrivals_all(_base()).columns.max())


def skus() -> pd.DataFrame:
    return _master()["dim_sku"].set_index("sku")


def sku_label(s: str) -> str:
    r = skus().loc[s]
    return f"{s} · {LINE_NAME[r['line_id']]}, size {r['size']}"


# ---------------- forms ----------------

@dataclass(frozen=True)
class Field:
    key: str
    label: str
    kind: str                        # "choice", "date", "int", "number" or "text"
    choices: tuple = ()              # ((value, label), ...) for a choice
    default: object = None
    min: object = None               # a number, or a date for a date field
    max: object = None
    exclude: tuple = ()              # values that would change nothing (e.g. 100% of capacity)
    help: str = ""


@dataclass(frozen=True)
class Tunable:
    key: str
    name: str
    changes: str                     # "data" (one of the object's numbers) or "rules" (a settings row)
    number: str                      # where it sits: opening, arrival, run limit, delay, routing, decides, target
    sits_on: str                     # resource, task, edge or setting
    question: str                    # what it answers, in a planner's words
    unit: str
    dated: bool
    fields: tuple
    example: str | None = None       # the built-in scenario its defaults reproduce

    def field(self, key: str) -> Field:
        return next(f for f in self.fields if f.key == key)


@dataclass(frozen=True)
class Edit:
    """A filled form: the values entered, and what they do to the scenario: a change to the object's numbers, or rows
    of the settings table ({prior, applies_to, from_date, new}, as `priors.apply_changes` takes)."""
    tunable: str
    values: dict
    change: Change | None = None
    settings: tuple = ()


def _sku_choices():
    return tuple((s, sku_label(s)) for s in skus().index)


def _line_choices():
    return tuple((ln, f"{LINE_NAME[ln]} line") for ln in LINES)


def _channels(with_all: bool):
    return ((("all", "All channels"),) if with_all else ()) + tuple(CHANNEL_NAME.items())


def _date(key, label, default_week, last, help=""):
    return Field(key, label, "date", default=week_start(default_week), min=week_start(1), max=week_start(last),
                 help=help or "The week that contains this date is the first.")


def _why():
    return Field("why", "Why (optional)", "text", default="", help="Kept with the change, e.g. planned maintenance.")


def _weeks(last):
    return Field("weeks", "Weeks", "int", default=1, min=1, max=last, help="Whole plan weeks from the first.")


def _tunables() -> dict:
    H, T = plan_weeks(), last_week()
    sku, line = _sku_choices(), _line_choices()
    scope = (("all", "All SKUs"),) + tuple((ln, f"{LINE_NAME[ln]} line (each SKU)") for ln in LINES) + sku
    t = [
        Tunable("stock", "Stock count", "data", "opening", "resource",
                "How many bikes are really in stock at the snapshot?", "bikes", False,
                (Field("sku", "SKU", "choice", sku, default="RW-9324"),
                 Field("site", "Site", "choice", (("RENO", "Reno"), ("CMH", "PDC")), default="RENO"),
                 Field("bikes", "Correction (bikes)", "int", default=-200, min=-20000, max=20000, exclude=(0,),
                       help="Negative: fewer than the books say."), _why())),
        Tunable("line_capacity", "Line capacity", "data", "arrival", "resource",
                "How much of a line's normal weekly capacity is there, for a stretch of weeks?", "% of normal", True,
                (Field("line", "Line", "choice", line, default="mtb-carbon"), _date("first", "From", 26, H),
                 replace(_weeks(H), default=3),
                 Field("percent", "Capacity (% of normal)", "int", default=0, min=0, max=200, exclude=(100,),
                       help="0 = the line is down; 50 = half speed; 120 = overtime."), _why()),
                example="E1"),
        Tunable("demand", "Demand", "data", "arrival", "resource",
                "How much more (or less) is ordered than forecast, for a stretch of weeks?", "% of forecast", True,
                (Field("skus", "SKUs", "choice", scope, default="RW-4418"),
                 Field("channel", "Channel", "choice", _channels(True), default="DEALERS"),
                 _date("first", "From", 18, T), replace(_weeks(T), default=13),
                 Field("percent", "Change (%)", "int", default=30, min=-100, max=500, exclude=(0,),
                       help="Each week's orders up (+) or down (-), rounded to whole bikes."), _why()),
                example="E2"),
        Tunable("extra_order", "One-off order", "data", "arrival", "resource",
                "Is there an order on top of the forecast, in one week?", "bikes", True,
                (Field("sku", "SKU", "choice", sku, default="RW-4418"),
                 Field("channel", "Channel", "choice", _channels(False), default="COMMERCIAL"),
                 _date("week", "Week", 26, T, help="The order arrives in the week that contains this date."),
                 Field("bikes", "Bikes", "int", default=300, min=1, max=20000), _why())),
        Tunable("build_limit", "Build limit", "data", "run limit", "task",
                "How many of a bike can be built at most each week, for a stretch of weeks (parts late or short)?",
                "bikes a week", True,
                (Field("skus", "SKUs", "choice", tuple(x for x in scope if x[0] != "all"), default="RW-4418",
                       help="A line means each of its SKUs, not their total."),
                 _date("first", "From", 60, H), replace(_weeks(H), default=8),
                 Field("most", "At most (bikes a week)", "int", default=0, min=0, max=20000,
                       help="0 = none can be built."), _why()),
                example="E3"),
        Tunable("transfer_limit", "Transfer limit", "data", "run limit", "task",
                "How many of a bike can go from Reno to the PDC at most each week? (Only where the plan decides "
                "transfers.)", "bikes a week", True,
                (Field("skus", "SKUs", "choice", (("all", "All SKUs (each SKU)"),) + sku, default="all"),
                 _date("first", "From", 10, H), replace(_weeks(H), default=4),
                 Field("most", "At most (bikes a week)", "int", default=20, min=0, max=20000), _why())),
        Tunable("build_time", "Build time", "rules", "delay", "edge",
                "How many weeks from using a line's capacity to a bike in Reno stock?", "weeks", False,
                (Field("line", "Line", "choice", line, default="mtb-carbon"),
                 Field("weeks", "Weeks", "int", default=2, min=0, max=priors.MAX_WEEKS, help="0 = the same week."))),
        Tunable("transfer_time", "Transfer time", "rules", "delay", "edge",
                "How many weeks does a transfer from Reno to the PDC take?", "weeks", False,
                (Field("weeks", "Weeks", "int", default=2, min=0, max=priors.MAX_WEEKS),)),
        Tunable("ship_from", "Ship from", "rules", "routing", "setting",
                "Which site may a channel's orders ship from?", "site", False,
                (Field("channel", "Channel", "choice", _channels(False), default="WEB"),
                 Field("site", "Ships from", "choice", tuple((k, k) for k in SHIP), default="PDC"))),
        Tunable("plan_transfers", "Plan transfers", "rules", "decides", "setting",
                "Does the plan decide transfers from Reno to the PDC?", "yes or no", False,
                (Field("decide", "Plan transfers", "choice", (("yes", "yes"), ("no", "no")), default="yes"),)),
        Tunable("target", "Target", "rules", "target", "setting",
                "How many weeks of supply should a group hold, from a date?", "weeks of supply", True,
                (Field("group", "Group", "choice", tuple(GROUP_NAME.items()), default="mtb_carbon"),
                 Field("weeks", "Weeks of supply", "number", default=18.0, min=0.5, max=52),
                 _date("from", "From", 53, H, help="The plan's first week sets the target from the start."))),
    ]
    return {x.key: x for x in t}


TUNABLES = _tunables()


def table() -> pd.DataFrame:
    """One row per tunable: what it is, where it sits in the model, and its form."""
    return pd.DataFrame([{"Tunable": t.name, "key": t.key, "Changes": t.changes, "In the model": t.number,
                          "Sits on": t.sits_on, "Unit": t.unit, "Dated": t.dated,
                          "Fields": ", ".join(f.label for f in t.fields), "Example": t.example or "",
                          "Question": t.question} for t in TUNABLES.values()])


# ---------------- a filled form -> an edit ----------------

def _field_problem(f: Field, v) -> str | None:
    if f.kind == "choice":
        return None if v in [c[0] for c in f.choices] else f"{f.label}: {v!r} is not one of the choices"
    if f.kind == "date":
        if not isinstance(v, dt.date):
            return f"{f.label}: a date is needed"
        return None if f.min <= v <= f.max + dt.timedelta(days=6) else \
            f"{f.label}: must be between {f.min:%-d %b %Y} and {f.max + dt.timedelta(days=6):%-d %b %Y}"
    if f.kind in ("int", "number"):
        if isinstance(v, bool) or not isinstance(v, (int, float, np.integer, np.floating)) or not np.isfinite(v):
            return f"{f.label}: a number is needed"
        if f.kind == "int" and not float(v).is_integer():
            return f"{f.label}: a whole number is needed"
        if (f.min is not None and v < f.min) or (f.max is not None and v > f.max):
            return f"{f.label}: must be between {f.min:g} and {f.max:g}"
        return f"{f.label}: {v:g} would change nothing" if v in f.exclude else None
    return None if isinstance(v, str) else f"{f.label}: text is needed"


def _scope(values, sel):
    s = values["skus"]
    if s in LINES:
        sel["line_id"] = s
    elif s != "all":
        sel["item"] = s
    return sel


def _span(values, key="first"):
    a = week_of(values[key])
    return a, a + int(values["weeks"]) - 1


def _build(key: str, v: dict):
    """The change, or the settings rows, a filled form means."""
    why = v.get("why", "").strip()
    if key == "stock":
        return Change("opening", {"kind": "inventory", "item": v["sku"], "location": v["site"]}, "add", int(v["bikes"]),
                      None, None, why)
    if key == "line_capacity":
        p = int(v["percent"])
        op, value = ("set", 0) if p == 0 else ("scale", round(p / 100, 9))
        return Change("arrival", {"kind": "capacity", "location": f"RENO/{v['line']}"}, op, value, *_span(v), why)
    if key == "demand":
        sel = _scope(v, {"kind": "order"})
        if v["channel"] != "all":
            sel["location"] = v["channel"]
        return Change("arrival", sel, "scale", round(1 + int(v["percent"]) / 100, 9), *_span(v), why)
    if key == "extra_order":
        t = week_of(v["week"])
        return Change("arrival", {"kind": "order", "item": v["sku"], "location": v["channel"]}, "add", int(v["bikes"]),
                      t, t, why)
    if key == "build_limit":
        return Change("run_max", _scope(v, {"kind": "make"}), "set", int(v["most"]), *_span(v), why)
    if key == "transfer_limit":
        return Change("run_max", _scope(v, {"kind": "move"}), "set", int(v["most"]), *_span(v), why)
    row = lambda prior, applies_to, new, from_date="": {"prior": prior, "applies_to": applies_to,
                                                        "from_date": from_date, "new": new}
    if key == "build_time":
        return (row("build_weeks", v["line"], str(int(v["weeks"]))),)
    if key == "transfer_time":
        return (row("transfer_weeks", "RENO>CMH", str(int(v["weeks"]))),)
    if key == "ship_from":
        return tuple(row("route", f"{site}>{v['channel']}", "yes" if site in SHIP[v["site"]] else "no")
                     for site in ("RENO", "CMH"))
    if key == "plan_transfers":
        return (row("decides", "move", v["decide"]),)
    if key == "target":
        monday = week_start(week_of(v["from"]))                  # targets start on a Monday, like plan weeks
        return (row("target_weeks", v["group"], f"{float(v['weeks']):g}", monday.isoformat()),)
    raise KeyError(key)


def make(key: str, **values) -> Edit:
    """A filled form -> an Edit. Missing fields take their defaults; a date may be given as 'YYYY-MM-DD'. Raises
    ValueError naming every field that is wrong."""
    if key not in TUNABLES:
        raise ValueError(f"unknown tunable {key!r}; the tunables are {', '.join(TUNABLES)}")
    t = TUNABLES[key]
    unknown = sorted(set(values) - {f.key for f in t.fields})
    if unknown:
        raise ValueError(f"{t.name}: unknown field(s) {unknown}; the fields are {[f.key for f in t.fields]}")
    filled = {}
    for f in t.fields:
        v = values.get(f.key, f.default)
        if f.kind == "date" and isinstance(v, str):
            try:
                v = dt.date.fromisoformat(v)
            except ValueError:
                pass
        if isinstance(v, pd.Timestamp):
            v = v.date()
        filled[f.key] = v
    errs = [p for f in t.fields if (p := _field_problem(f, filled[f.key]))]
    if errs:
        raise ValueError(f"{t.name}: " + "; ".join(errs))
    built = _build(key, filled)
    if isinstance(built, Change):
        return Edit(key, filled, change=built)
    return Edit(key, filled, settings=tuple(built))


# ---------------- edits on a scenario ----------------

def apply(case, edits, **fields):
    """The scenario with these edits: settings rows applied to its table, changes added after its own, in the order
    given. `fields` may set key, name, summary or parent of the result."""
    rows = [r for e in edits for r in e.settings]
    table_ = priors.apply_changes(case.priors, rows) if rows else case.priors
    return replace(case, priors=table_, changes=tuple(case.changes) + tuple(e.change for e in edits if e.change), **fields)


PLAIN = {"changes no number": "it would change nothing (the numbers it selects already have that value)"}


def check(case, edits=()) -> list[str]:
    """Every reason the scenario, with these edits, cannot run, in words. Empty when it can. Does not plan: it checks
    the settings table against the network, each change against the object (in order), that a run limit sits on runs
    the plan decides, and that no edit changes nothing."""
    errs = []
    t0 = priors.normalise(case.priors)
    for e in edits:                                           # a settings edit that leaves every row as it was
        if e.settings and not priors.diff(t0, priors.apply_changes(t0, list(e.settings))):
            errs.append(f"{describe(e)}: it would change nothing (that is already the setting)")
    new = apply(case, edits)
    p_errs = priors.validate(new.priors, _base())
    if p_errs:
        return errs + p_errs
    st = new.settings
    obj = aux_fns.build_object(_master(), st["build_weeks"], st["transfer_weeks"])
    changes = list(new.changes)
    for problem in ch.check(obj, changes):
        n = int(problem.split(" ", 2)[1])
        rule = problem.split("): ", 1)[-1]
        errs.append(f"{describe(changes[n - 1])}: {PLAIN.get(rule, rule)}")
    if not errs:                                              # as run_case refuses it: a limit on a run not decided
        decided = set(obj.tasks.loc[obj.tasks["kind"].isin(st["decides"]), "task_id"])
        for c in changes:
            ids, _ = ch.selected(obj, c.select)
            if c.field == "run_max" and set(ids) - decided:
                errs.append(f"{describe(c)}: the plan does not decide these runs in this scenario, so a limit would "
                            "change nothing" + (" (it plans no transfers)" if c.select.get("kind") == "move" else ""))
    return errs


# ---------------- in words ----------------

def _list(v) -> list:
    return list(v) if isinstance(v, (list, tuple, set)) else [v]


def _and(names: list) -> str:
    names = [str(n) for n in names]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def tunable_of(c: Change) -> str | None:
    """Which tunable a change is (None for a change no form makes)."""
    kind = c.select.get("kind") if isinstance(c.select, dict) else None
    if c.field == "opening" and kind == "inventory":
        return "stock"
    if c.field == "arrival" and kind == "capacity":
        return "line_capacity"
    if c.field == "arrival" and kind == "order":
        return "extra_order" if c.op == "add" and c.from_t == c.to_t else "demand"
    if c.field == "run_max":
        return {"make": "build_limit", "move": "transfer_limit"}.get(kind)
    return None


def subject(c: Change) -> str:
    """What a change is about ('MTB carbon line capacity', 'Dealer orders for RW-4418', 'RW-4418 builds')."""
    s = c.select if isinstance(c.select, dict) else {}
    kind, rest = s.get("kind"), {k: v for k, v in s.items() if k != "kind"}
    items = _and(_list(rest["item"])) if "item" in rest else None
    lines = _and([LINE_NAME.get(x, x) for x in _list(rest["line_id"])]) if "line_id" in rest else None
    if kind == "capacity" and set(rest) <= {"location"}:
        names = [LINE_NAME.get(str(x).split("/")[-1], x) for x in _list(rest["location"])] if rest else []
        return ("All lines' capacity" if not names else f"{names[0]} line capacity" if len(names) == 1
                else f"{_and(names)} lines' capacity")
    if kind == "order" and set(rest) <= {"item", "location", "line_id", "channel"}:
        chans = [CHANNEL_NAME.get(x, x) for x in _list(rest.get("location", []))] + \
                [CHANNEL_NAME[CHANNEL_OF_CODE[x]] if x in CHANNEL_OF_CODE else x for x in _list(rest.get("channel", []))]
        what = f"{_and(chans)} orders" if chans else "Orders" if items or lines else "All orders"
        return what + (f" for {items}" if items else "") + (f" for {lines} SKUs" if lines else "")
    if kind == "inventory" and set(rest) <= {"item", "location"}:
        sites = _and([SITE_NAME.get(x, x) for x in _list(rest["location"])]) if "location" in rest else "every site"
        return f"Stock of {items or 'every SKU'} at {sites}"
    if kind == "make" and set(rest) <= {"item", "line_id"}:
        return f"{items} builds" if items else f"{lines} builds (each SKU)" if lines else "All builds (each SKU)"
    if kind == "move" and set(rest) <= {"item", "line_id"}:
        return (f"{items} transfers to the PDC" if items else f"{lines} transfers to the PDC (each SKU)" if lines
                else "Transfers to the PDC (each SKU)")
    return " ".join([str(kind)] + [f"{k} {_and(_list(v))}" for k, v in rest.items()])


def when(c: Change) -> str:
    """'weeks of 1 Mar to 15 Mar 2027', 'week of 1 Mar 2027', or 'at the snapshot'."""
    if c.from_t is None:
        return "at the snapshot"
    a, b = week_start(c.from_t), week_start(c.to_t)
    if a == b:
        return f"week of {a:%-d %b %Y}"
    return f"weeks of {a:%-d %b}{f' {a:%Y}' if a.year != b.year else ''} to {b:%-d %b %Y}"


def effect(c: Change) -> str:
    """What a change does to each number it selects, in words."""
    v = float(c.value)
    tun = tunable_of(c)
    if c.field == "run_max":
        return "none" if v == 0 else f"at most {v:,g} a week"
    if tun == "line_capacity":
        return "down (none)" if c.op == "set" and v == 0 else f"{v * 100:g}% of normal" if c.op == "scale" else \
            f"set to {v:,g} a week" if c.op == "set" else f"{v:+,g} a week"
    if c.op == "set":
        return f"set to {v:,g}"
    if c.op == "add":
        return f"{v:+,g} bikes"
    return f"{(v - 1) * 100:+.2f}".rstrip("0").rstrip(".") + "%"


def _wk(n) -> str:
    n = float(n)
    return "same week" if n == 0 else f"{n:g} week" + ("" if n == 1 else "s")


def _ship_from(table, channel) -> str:
    t = priors.normalise(table)
    sites = tuple(s for s in ("RENO", "CMH")
                  if (t[(t["prior"] == "route") & (t["applies_to"] == f"{s}>{channel}")]["value"] == "yes").any())
    return next((k for k, v in SHIP.items() if v == sites), "nowhere")


def describe(x) -> str:
    """An Edit or a Change in words."""
    if isinstance(x, Change):
        return f"{subject(x)} · {when(x)} · {effect(x)}"
    v = x.values
    if x.change is not None:
        return describe(x.change)
    if x.tunable == "build_time":
        return f"Build time · {LINE_NAME[v['line']]} · {_wk(v['weeks'])}"
    if x.tunable == "transfer_time":
        return f"Transfer time · Reno to the PDC · {_wk(v['weeks'])}"
    if x.tunable == "ship_from":
        return f"Ship from · {CHANNEL_NAME[v['channel']]} orders · {v['site']}"
    if x.tunable == "plan_transfers":
        return f"Plan transfers · Reno to the PDC · {v['decide']}"
    if x.tunable == "target":
        monday = week_start(week_of(v["from"]))
        return (f"Target · {GROUP_NAME[v['group']]} · {float(v['weeks']):g} weeks"
                + ("" if monday <= START else f" from {monday:%-d %b %Y}"))
    return f"{x.tunable} {x.values}"


def name_hint(c: Change) -> str:
    """A short name for a scenario made of this change."""
    if tunable_of(c) == "line_capacity" and c.op == "set" and c.value == 0:
        return f"{subject(c).removesuffix(' capacity')} down from {week_start(c.from_t):%-d %b %Y}"
    if c.field == "run_max" and c.value == 0:
        return f"No {subject(c).removesuffix(' (each SKU)').removesuffix(' builds')} built from {week_start(c.from_t):%-d %b %Y}" \
            if c.select.get("kind") == "make" else f"{subject(c)}: none from {week_start(c.from_t):%-d %b %Y}"
    return f"{subject(c)} {effect(c)}"


# ---------------- what differs between two scenarios ----------------

def _key(c: Change) -> str:
    """Two changes are the same edit when they edit the same numbers the same way (the reason, and how the selection is
    spelled, do not count)."""
    ids, _ = ch.selected(_base(), c.select)
    return json.dumps([c.field, ids or c.select, c.op, c.value, c.from_t, c.to_t], sort_keys=True, default=str)


def moves(old, new) -> list:
    """[("removed", change) ... ("added", change) ...]: changes only in `old`, only in `new`, in list order. Order counts:
    a later change sees the result of an earlier one."""
    old, new = list(old), list(new)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, [_key(c) for c in old], [_key(c) for c in new],
                                                      autojunk=False).get_opcodes():
        out += [("removed", c) for c in (old[i1:i2] if op in ("delete", "replace") else [])]
        out += [("added", c) for c in (new[j1:j2] if op in ("insert", "replace") else [])]
    return out


def same_changes(old, new) -> bool:
    return not moves(old, new)


def differences(a, b) -> pd.DataFrame:
    """Tunable | What | From | To | Why: everything scenario b sets differently from scenario a, settings first (a
    channel's routes as one row), then changes to the data (removed, then added, in order)."""
    rows = []
    ta, tb = priors.normalise(a.priors), priors.normalise(b.priors)
    d = priors.diff(ta, tb)
    for chan in [c for c in CHANNEL_NAME if any(x["prior"] == "route" and x["applies_to"].endswith(">" + c) for x in d)]:
        rows.append(("Ship from", f"{CHANNEL_NAME[chan]} orders", _ship_from(ta, chan), _ship_from(tb, chan), ""))
    for x in d:
        p, at, o, n = x["prior"], x["applies_to"], x["old"], x["new"]
        if p == "build_weeks":
            rows.append(("Build time", LINE_NAME.get(at, at), _wk(o) if o else "—", _wk(n) if n else "—", ""))
        elif p == "transfer_weeks":
            rows.append(("Transfer time", "Reno to the PDC", _wk(o) if o else "—", _wk(n) if n else "—", ""))
        elif p == "decides":
            rows.append(("Plan transfers" if at == "move" else "Plan builds", "Reno to the PDC" if at == "move" else "",
                         o or "—", n or "—", ""))
        elif p == "target_weeks":
            when_ = "" if x["from_date"] and pd.Timestamp(x["from_date"]) <= PLAN_START else \
                f" from {pd.Timestamp(x['from_date']):%-d %b %Y}"
            rows.append(("Target", GROUP_NAME.get(at, at) + when_, f"{float(o):g} weeks" if o else "—",
                         f"{float(n):g} weeks" if n else "removed", ""))
    for what, c in moves(a.changes, b.changes):
        name = TUNABLES[tunable_of(c)].name if tunable_of(c) else "Change"
        rows.append((name, f"{subject(c)} · {when(c)}", effect(c) if what == "removed" else "as in the data",
                     "as in the data" if what == "removed" else effect(c), c.reason))
    return pd.DataFrame(rows, columns=["Tunable", "What", "From", "To", "Why"])


def change_rows(changes, report: pd.DataFrame) -> pd.DataFrame:
    """A run's changes in words, with the numbers each changed (the report from `changes.apply`, one row per change):
    Tunable | What | Change | Numbers changed | From | To | Why. From and To add up the numbers changed: bikes (of
    stock, orders or capacity), or for a run limit, none before ("no limit") and the limit after."""
    rows = []
    for c, (_, r) in zip(changes, report.iterrows()):
        if c.field == "run_max":
            frm = "no limit" if np.isnan(r["before"]) else f"{r['before']:,.0f} in all"
            to = effect(c)
        else:
            frm, to = f"{r['before']:,.0f} bikes", f"{r['after']:,.0f} bikes"
        rows.append({"Tunable": TUNABLES[tunable_of(c)].name if tunable_of(c) else "Change",
                     "What": f"{subject(c)} · {when(c)}", "Change": effect(c), "Numbers changed": int(r["cells"]),
                     "From": frm, "To": to, "Why": c.reason})
    return pd.DataFrame(rows, columns=["Tunable", "What", "Change", "Numbers changed", "From", "To", "Why"])


# ---------------- what is there now ----------------

def now(key: str, case, **values) -> str:
    """What the scenario has now where a filled form would edit, in words (for showing next to the form)."""
    e = make(key, **values)
    if e.change is not None:
        st = case.settings
        obj = ch.apply(aux_fns.build_object(_master(), st["build_weeks"], st["transfer_weeks"]), list(case.changes))[0]
        c = e.change
        ids, _ = ch.selected(obj, c.select)
        if c.field == "opening":
            return f"{float(obj.opening[ids].sum()):,.0f} bikes in stock at the snapshot"
        weeks = list(range(c.from_t, c.to_t + 1))
        if c.field == "run_max":
            lim = rtn.run_limits(obj).loc[ids, weeks]
            return "no limit" if lim.isna().all().all() else f"limits from {lim.min().min():,.0f} to {lim.max().max():,.0f} a week"
        A = rtn.arrivals_all(obj).loc[ids, weeks]
        if tunable_of(c) == "line_capacity":
            lo, hi = A.min().min(), A.max().max()
            return f"{lo:,.0f} a week" if lo == hi else f"{lo:,.0f} to {hi:,.0f} a week"
        return f"{A.values.sum():,.0f} bikes forecast in {'that week' if len(weeks) == 1 else 'those weeks'}"
    t = priors.normalise(case.priors)
    v = e.values
    val = lambda prior, at: t[(t["prior"] == prior) & (t["applies_to"] == at)]["value"]
    if key == "build_time":
        return _wk(val("build_weeks", v["line"]).iloc[0])
    if key == "transfer_time":
        return _wk(val("transfer_weeks", "RENO>CMH").iloc[0])
    if key == "ship_from":
        return _ship_from(t, v["channel"])
    if key == "plan_transfers":
        return val("decides", "move").iloc[0]
    rows = t[(t["prior"] == "target_weeks") & (t["applies_to"] == v["group"])].sort_values("from_date")
    day = week_start(week_of(v["from"])).isoformat()
    current = rows[rows["from_date"] <= day]["value"]
    return f"{float(current.iloc[-1]):g} weeks" if len(current) else "no target"
