"""LLM proposals: a planner's request in words -> checked edits to a scenario. And answers about computed plans.

The LLM never writes or runs the model. It fills one fixed schema; what it fills is checked in code; if the check
fails, the reasons go back to the LLM once. The result is a proposal for a person to review and apply; nothing here
changes a scenario or runs a plan.

    propose_edits  any tunable (redwheel/tunables.py): the data (stock, capacity, demand, one-off orders, build and
                   transfer limits) and the rules (lead times, routing, targets, transfers). Each edit is one tunable's
                   form, filled; `tunables.make` and `tunables.check` check them. What the LLM sees: the request, the
                   scenario's settings and changes in words, the tunables and their forms, and the catalogue (sites,
                   channels, lines, SKUs with their line and size). No orders, forecasts, stock or customer data.
    propose        the earlier, settings-only version: rows of the priors table, checked by `priors.validate`. Kept
                   while the planner UIs call it; `propose_edits` does all it does and the data too.
    explain        answers a question about computed plans from a facts sheet only.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field

import pandas as pd

from redwheel import priors, rtn, tunables as tu
from redwheel.config import PLAN_END, PLAN_START

MODEL = "claude-opus-5-5"
EFFORT = "medium"
MAX_ATTEMPTS = 2                                   # first answer + one correction after a failed check


# ---------------- what the LLM may write ----------------

def vocabulary(obj: rtn.RTN) -> dict:
    """Every value `applies_to` can take for each prior, read from the network."""
    routes = sorted(obj.tasks.loc[obj.tasks["kind"] == "fulfil", "task_id"].str.split("|").str[2].unique())
    lines = sorted(obj.resources.loc[obj.resources["kind"] == "capacity", "location"].str.split("/").str[1].unique())
    moves = sorted(obj.tasks.loc[obj.tasks["kind"] == "move", "task_id"].str.split("|").str[2].unique())
    return {"route": routes, "build_weeks": lines, "transfer_weeks": moves,
            "target_weeks": sorted(obj.items["target_group"].unique()), "decides": ["make", "move"]}


def schema(obj: rtn.RTN) -> dict:
    """The one shape the answer may take. Enums come from the network, so a name that does not exist cannot be
    written."""
    voc = vocabulary(obj)
    return {
        "type": "object",
        "properties": {
            "changes": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "prior": {"type": "string", "enum": list(voc)},
                    "applies_to": {"type": "string", "enum": sorted({a for v in voc.values() for a in v})},
                    "from_date": {"type": "string", "description": "YYYY-MM-DD for target_weeks rows, else empty"},
                    "action": {"type": "string", "enum": ["set", "remove"]},
                    "value": {"type": "string", "description": "new value; empty when action is remove"},
                    "reason": {"type": "string", "description": "which words of the request this change carries out"},
                },
                "required": ["prior", "applies_to", "from_date", "action", "value", "reason"],
                "additionalProperties": False}},
            "unsupported": {"type": "array", "items": {"type": "string"},
                            "description": "parts of the request these settings cannot express"},
            "question": {"type": "string", "description": "a clarifying question if the request is unclear, else empty"},
        },
        "required": ["changes", "unsupported", "question"],
        "additionalProperties": False,
    }


SYSTEM = f"""You turn a supply planner's request into changes to a planning-priors table. The table is the only input
a scenario's plan reads; a linear programme then plans weekly builds (and, if the table says so, transfers) from it.
You do not plan, solve or estimate results. You only propose table changes, which a person reviews.

THE NETWORK (fixed; you cannot change it)
- Sites holding stock: RENO (the factory, all four production lines) and CMH (the PDC, a distribution centre in
  Columbus). Stock reaches the PDC only by transfer from Reno.
- Customers (order types): WEB (direct-to-consumer web orders), DEALERS, COMMERCIAL.
- Lines (one per bike class and trim): road-base, road-carbon, mtb-base, mtb-carbon.
- Target groups: road, mtb_base, mtb_carbon.
- Plan horizon: weekly, {PLAN_START.date()} to {PLAN_END.date()}.

THE SETTINGS (rows of the table: prior, applies_to, from_date, value)
- route, SITE>CUSTOMER, yes/no: orders of that customer may ship from that site. Sites that serve a common customer
  pool their stock; each pool's stock is counted against the demand of the customers it serves.
- build_weeks, line, whole weeks 0-{priors.MAX_WEEKS}: weeks from using line capacity to a bike in Reno stock.
- transfer_weeks, RENO>CMH, whole weeks 0-{priors.MAX_WEEKS}: weeks from Reno to the PDC.
- target_weeks, target group, weeks (more than 0, at most 52), with from_date YYYY-MM-DD: the weeks-of-supply target
  from that date until the group's next target row. A group needs a row starting on or before {PLAN_START.date()}.
  To step a target on a date, add a row; to change an existing row, set it with its own from_date.
- decides, make or move, yes/no: whether the plan decides builds (must stay yes) and transfers Reno -> PDC.

A TABLE MUST ALSO SATISFY
- Every customer is served by at least one route.
- If transfers are decided, Reno and the PDC must not serve a common customer (moving stock between sites that serve
  the same orders gains nothing).
- If the PDC serves customers on its own, transfers must be decided (otherwise the PDC is never restocked).

HOW TO ANSWER
- Propose the smallest set of changes that does what the request says, and nothing it does not say.
- A change that leaves a value as it already is is not a change; leave it out.
- If part of the request cannot be expressed with these settings (for example: shipping from Reno only when the PDC
  is short, costs, capacity, demand, a new site), list it under unsupported. Do not approximate it with other
  settings.
- If the request is unclear about what to change, ask one question and propose no changes.
- Each change's reason names the words of the request it carries out."""


# ---------------- one proposal ----------------

@dataclass
class Proposal:
    request: str
    changes: list = field(default_factory=list)       # [{prior, applies_to, from_date, old, new, reason}]
    unsupported: list = field(default_factory=list)
    question: str = ""
    table: pd.DataFrame | None = None                  # the proposed table (None if nothing was proposed)
    errors: list = field(default_factory=list)         # validator errors left after the last attempt
    attempts: int = 0
    usage: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Changes that pass every check, ready for a person to review."""
        return bool(self.changes) and not self.errors


def _ask(client, messages, sch, system=SYSTEM, **extra):
    r = client.beta.messages.create(
        model=MODEL, max_tokens=extra.pop("max_tokens", 8000), system=system, messages=messages,
        output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": sch}},
        betas=["server-side-fallback-2026-07-01"], extra_body={"fallbacks": "default"}, **extra)
    if r.stop_reason == "refusal":
        raise RuntimeError("the model declined the request")
    if r.stop_reason == "max_tokens":
        raise RuntimeError("the answer was cut off")
    text = next(b.text for b in r.content if b.type == "text")
    return text, json.loads(text), r.usage


def _to_change_list(answer: dict) -> list:
    return [{"prior": c["prior"], "applies_to": c["applies_to"],
             "from_date": c["from_date"] if c["prior"] == "target_weeks" else "",
             "new": None if c["action"] == "remove" else c["value"]} for c in answer["changes"]]


def propose(request: str, table: pd.DataFrame, obj: rtn.RTN, client=None) -> Proposal:
    """Ask for the table changes that carry out `request`; check them; return a proposal (never applied here)."""
    if client is None:
        import anthropic
        client = anthropic.Anthropic()               # credentials from the environment or an `ant auth login` profile
    table = priors.normalise(table)
    sch = schema(obj)
    messages = [{"role": "user", "content": (
        "Current priors table (CSV):\n" + table.to_csv(index=False) + "\nRequest: " + request)}]
    out = Proposal(request=request)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        text, answer, usage = _ask(client, messages, sch)
        out.attempts = attempt
        for k in ("input_tokens", "output_tokens"):
            out.usage[k] = out.usage.get(k, 0) + getattr(usage, k)
        out.unsupported, out.question = answer["unsupported"], answer["question"]
        if not answer["changes"]:
            out.changes, out.table, out.errors = [], None, []
            return out
        new = priors.apply_changes(table, _to_change_list(answer))
        reasons = {(c["prior"], c["applies_to"], c["from_date"] if c["prior"] == "target_weeks" else ""): c["reason"]
                   for c in answer["changes"]}
        out.changes = [{**d, "reason": reasons.get((d["prior"], d["applies_to"], d["from_date"]), "")}
                       for d in priors.diff(table, new)]       # what actually changes, with old values
        out.table, out.errors = new, priors.validate(new, obj)
        if not out.errors:
            return out
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": "That table fails these checks:\n- " + "\n- ".join(out.errors)
                      + "\nCorrect the changes (answer with the full change list again), or, if the request cannot "
                        "be done within these rules, propose no changes and say why under unsupported."}]
    return out


# ---------------- any tunable: a request -> checked edits ----------------

def edits_schema() -> dict:
    """The one shape an answer may take: edits, each a tunable's name and its form's fields as name/value pairs, with
    the words of the request it carries out; what cannot be expressed; a question if the request is unclear. Tunable
    and field names are enums, so neither can be made up. The values are text: their choices and ranges are in the
    instructions, and `tunables.make` checks them. (One strict schema per form was refused by the API as too large.)"""
    names = sorted({f.key for t in tu.TUNABLES.values() for f in t.fields})
    field_ = {"type": "object", "properties": {"name": {"type": "string", "enum": names}, "value": {"type": "string"}},
              "required": ["name", "value"], "additionalProperties": False}
    edit = {"type": "object",
            "properties": {"tunable": {"type": "string", "enum": list(tu.TUNABLES)},
                           "fields": {"type": "array", "items": field_},
                           "reason": {"type": "string", "description": "which words of the request this edit carries out"}},
            "required": ["tunable", "fields", "reason"], "additionalProperties": False}
    return {
        "type": "object",
        "properties": {
            "edits": {"type": "array", "items": edit},
            "unsupported": {"type": "array", "items": {"type": "string"},
                            "description": "parts of the request no tunable can express"},
            "question": {"type": "string", "description": "one clarifying question if the request is unclear, else empty"},
        },
        "required": ["edits", "unsupported", "question"],
        "additionalProperties": False,
    }


def _field_text(f: tu.Field) -> str:
    """One field of a form, for the instructions: its name, what it takes, and what it means."""
    help_ = f" {f.help}" if f.help else ""
    if f.kind == "choice":
        skus = [v for v, _ in f.choices if v in tu.skus().index]
        others = [f"{v} ({lab})" for v, lab in f.choices if v not in tu.skus().index]
        what = ("one of " + ", ".join(others) + (", or a SKU id from the catalogue" if skus else "")) if others \
            else "a SKU id from the catalogue"
    elif f.kind == "date":
        what = f"a date YYYY-MM-DD, {f.min.isoformat()} to {(f.max + dt.timedelta(days=6)).isoformat()}"
    elif f.kind in ("int", "number"):
        what = f"{'a whole number' if f.kind == 'int' else 'a number'} from {f.min:g} to {f.max:g}" + \
               (f", not {', '.join(f'{x:g}' for x in f.exclude)}" if f.exclude else "")
    else:
        what = "text, may be empty"
    return f"    {f.key}: {what}.{help_}"


def _tunables_text() -> str:
    out = []
    for t in tu.TUNABLES.values():
        where = "a number in the data" if t.changes == "data" else "a setting of the plan's rules"
        out.append(f"- {t.key} ({t.name}; {where}: {t.number}). {t.question} Unit: {t.unit}.\n"
                   + "\n".join(_field_text(f) for f in t.fields))
    return "\n".join(out)


def _catalogue_text() -> str:
    k = tu.skus()
    return "; ".join(f"{s} ({tu.LINE_NAME[r['line_id']]}, size {r['size']})" for s, r in k.iterrows())


def _typed(f: tu.Field, value: str):
    """A field's value from the text the LLM wrote: a number for a number field (left as text if it is not one, so the
    form check names it), text otherwise."""
    if f.kind in ("int", "number"):
        try:
            x = float(value)
        except ValueError:
            return value
        return int(x) if f.kind == "int" and x.is_integer() else x
    return value


def _edit_of(item: dict):
    """An answer's edit -> tunables.Edit. Every field must be given (a default must never stand in for something the
    request did not say), except `why`. Raises ValueError naming what is wrong."""
    t = tu.TUNABLES[item["tunable"]]
    given = {}
    for pair in item["fields"]:
        if pair["name"] in given:
            raise ValueError(f"{t.name}: field {pair['name']} given twice")
        given[pair["name"]] = pair["value"]
    unknown = sorted(set(given) - {f.key for f in t.fields})
    if unknown:
        raise ValueError(f"{t.name}: no field(s) {unknown}; its fields are {[f.key for f in t.fields]}")
    missing = [f.key for f in t.fields if f.key not in given and f.key != "why"]
    if missing:
        raise ValueError(f"{t.name}: missing field(s) {missing}")
    return tu.make(t.key, **{k: _typed(t.field(k), v) for k, v in given.items()})


EDITS_SYSTEM = f"""You turn a supply planner's request into edits to a scenario. A scenario is the data (stock, line
capacity, demand, limits on builds and transfers) and the plan's rules (lead times, which site serves which channel,
targets, whether the plan decides transfers). A linear programme then plans weekly builds from it. You do not plan,
solve or estimate results. You only fill forms, one per edit, which are checked and which a person reviews.

THE NETWORK (fixed; you cannot change it)
- Sites holding stock: RENO (the factory, all four production lines) and CMH (the PDC, a distribution centre in
  Columbus). Stock reaches the PDC only by transfer from Reno.
- Channels (order types): WEB (direct-to-consumer web orders), DEALERS, COMMERCIAL.
- Lines (one per bike class and trim): road-base, road-carbon, mtb-base, mtb-carbon. Each SKU is built on one line.
- Target groups: road, mtb_base, mtb_carbon.
- Time: weekly plan weeks starting Mondays, {PLAN_START.date()} (week 1) to {PLAN_END.date()}; the forecast runs to
  {tu.week_start(tu.last_week())}. "Now" is the snapshot: the week of {PLAN_START.date()}.

THE CATALOGUE (SKU ids)
{_catalogue_text()}

THE TUNABLES (each edit is one tunable with all of its fields; `why` may be empty)
{_tunables_text()}

HOW TO ANSWER
- Propose the smallest set of edits that does what the request says, and nothing it does not say.
- Dates: a date picks the plan week that contains it, and "weeks" counts whole weeks from there. "The next two
  weeks" means the two weeks starting now ({PLAN_START.date()}). A month starts at its first Monday (the week that
  contains the 1st may begin in the month before); "to the end of March" ends with the last week that starts in
  March.
- Line capacity is a percentage of normal: 0 when a line is down, 50 at half speed, above 100 for overtime.
  Demand is a change in percent (+30 = 30% more than forecast). A build or transfer limit of 0 means none.
- Data edits are added to the scenario's existing changes, after them. Rules edits set a value.
- If the request does not say which line, SKU, channel, site or weeks it means, and the scenario does not make it
  clear, ask one question and propose no edits. Do not guess.
- If part of the request cannot be expressed with these tunables (for example costs, a new site or line, removing a
  change the scenario already has, or a rule that depends on conditions), list it under unsupported. Never
  approximate it with another tunable (a line outage is line capacity, never a lead time).
- `why`: the cause the planner gives (e.g. "planned maintenance", "frames late"), in a few words; empty if none.
- Each edit's reason names the words of the request it carries out."""


def scenario_text(case) -> str:
    """The scenario as the LLM sees it: its name, its settings and its changes, in words. No numbers from the data."""
    t = priors.normalise(case.priors)
    targets = []
    for g, name in tu.GROUP_NAME.items():
        rows = t[(t["prior"] == "target_weeks") & (t["applies_to"] == g)].sort_values("from_date")
        targets.append(f"{name} " + ", then ".join(
            f"{float(r.value):g} weeks" + ("" if pd.Timestamp(r.from_date) <= PLAN_START else
                                          f" from {pd.Timestamp(r.from_date).date()}") for r in rows.itertuples()))
    lines = [f"Scenario: {case.name}",
             "Settings: " + "; ".join(f"{tu.CHANNEL_NAME[c]} orders ship from {tu.now('ship_from', case, channel=c)}"
                                      for c in tu.CHANNEL_NAME)
             + f"; plan transfers: {tu.now('plan_transfers', case)}"
             + "; build time: " + ", ".join(f"{tu.LINE_NAME[ln]} {tu.now('build_time', case, line=ln)}" for ln in tu.LINE_NAME)
             + f"; transfer time Reno to the PDC: {tu.now('transfer_time', case)}"
             + "; targets: " + "; ".join(targets) + ".",
             "Changes already in this scenario: " + ("; ".join(f"({i}) {tu.describe(c)}" for i, c in
                                                             enumerate(case.changes, 1)) or "none") + "."]
    return "\n".join(lines)


@dataclass
class EditProposal:
    request: str
    case: object                                       # the scenario the request is about
    edits: list = field(default_factory=list)          # tunables.Edit, in order
    reasons: list = field(default_factory=list)        # the words of the request each edit carries out
    unsupported: list = field(default_factory=list)
    question: str = ""
    errors: list = field(default_factory=list)         # what failed the checks after the last attempt
    attempts: int = 0
    usage: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Edits that pass every check, ready for a person to review."""
        return bool(self.edits) and not self.errors

    @property
    def words(self) -> list:
        return [tu.describe(e) for e in self.edits]

    def scenario(self, **fields):
        """The scenario with the edits (only when ok)."""
        if not self.ok:
            raise ValueError("no checked edits to apply")
        return tu.apply(self.case, self.edits, **fields)


def propose_edits(request: str, case, client=None) -> EditProposal:
    """Ask for the edits that carry out `request` on scenario `case`; check them; return a proposal (never applied)."""
    if client is None:
        import anthropic
        client = anthropic.Anthropic()               # credentials from the environment or an `ant auth login` profile
    sch = edits_schema()
    messages = [{"role": "user", "content": scenario_text(case) + "\n\nRequest: " + request}]
    out = EditProposal(request=request, case=case)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        text, answer, usage = _ask(client, messages, sch, system=EDITS_SYSTEM, max_tokens=16000,
                                   thinking={"type": "adaptive"})
        out.attempts = attempt
        for k in ("input_tokens", "output_tokens"):
            out.usage[k] = out.usage.get(k, 0) + getattr(usage, k)
        out.unsupported, out.question = answer["unsupported"], answer["question"]
        edits, reasons, errors = [], [], []
        for i, item in enumerate(answer["edits"], start=1):
            try:
                edits.append(_edit_of(item))
                reasons.append(item["reason"])
            except ValueError as e:
                errors.append(f"edit {i}: {e}")
        if not errors and edits:
            errors = tu.check(case, edits)
        out.edits, out.reasons, out.errors = edits, reasons, errors
        if not errors or attempt == MAX_ATTEMPTS:
            return out
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": "Those edits fail the checks:\n- " + "\n- ".join(errors)
                      + "\nCorrect them (answer with the full list of edits again), or, if the request cannot be done "
                        "with these tunables, propose no edits and say why under unsupported, or ask a question."}]
    return out


# ---------------- answers about results (read-only) ----------------

EXPLAIN_SYSTEM = """You answer a supply planner's question about plans already computed by a linear programme. The
facts below the question are everything you know: settings, dates and numbers taken from the computed plans.

- Use only those facts. Do not estimate, forecast, or compute new figures beyond simple differences between given
  numbers. Never invent a number, date, SKU or reason.
- When several facts bear on the answer, connect them (for example a setting that differs and a date that moved), but
  say "likely" when the facts show a link without proving it.
- If the facts do not answer the question, say so in one sentence and name what is missing.
- At most 120 words. Plain sentences, no headings, no bullet lists unless comparing three or more items."""


def explain(question: str, facts: str, client=None) -> dict:
    """Answer a question about computed plans from a facts sheet only. Returns {"answer", "usage"}; never changes
    anything. The facts sheet is built by the caller from computed results (no orders or customer data)."""
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    r = client.beta.messages.create(
        model=MODEL, max_tokens=4000, system=EXPLAIN_SYSTEM,
        messages=[{"role": "user", "content": f"FACTS\n{facts}\n\nQUESTION\n{question}"}],
        output_config={"effort": EFFORT},
        betas=["server-side-fallback-2026-07-01"], extra_body={"fallbacks": "default"})
    if r.stop_reason == "refusal":
        raise RuntimeError("the model declined the question")
    text = "".join(b.text for b in r.content if b.type == "text").strip()
    return {"answer": text, "usage": {"input_tokens": r.usage.input_tokens, "output_tokens": r.usage.output_tokens}}
