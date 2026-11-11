"""LLM proposals: a planner's request in words -> a change list for the planning-priors table.

The LLM never writes or runs the model. It fills one fixed schema (changes, reasons, what it cannot express, a
question if the request is unclear); the changes are applied to a copy of the table and checked by
`priors.validate`. If the check fails, the errors go back to the LLM once. The result is a proposal for a person to
review and apply; nothing here changes a scenario or runs a plan.

What the LLM sees: the request, the current priors table, and the network's structure (sites, customers, lines,
target groups, the rules a table must satisfy). No orders, forecasts, stock or customer data.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import pandas as pd

from redwheel import priors, rtn
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


def _ask(client, messages, sch):
    r = client.beta.messages.create(
        model=MODEL, max_tokens=8000, system=SYSTEM, messages=messages,
        output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": sch}},
        betas=["server-side-fallback-2026-07-01"], extra_body={"fallbacks": "default"})
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
