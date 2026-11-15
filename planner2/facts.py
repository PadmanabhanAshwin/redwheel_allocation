"""The facts sheet an LLM answers from: settings and computed results of one or more scenarios, as plain text.

Everything here comes from computed plans (ui.view_of) and scenario settings; no orders, customers or stock records.
The LLM is told to use nothing else, so a question the sheet cannot answer gets "the facts do not say"."""
from __future__ import annotations

from planner2 import charts, events
from planner2.components import CUSTOMERS, GROUPS, describe_changes, ship_from, target_text, targets, wk
from redwheel import priors
from redwheel.config import LINES, PLAN_END, PLAN_START
from ui import fmt_date

MODEL = (f"How every plan is made: a linear programme plans weekly builds per SKU on four Reno lines, "
         f"{fmt_date(PLAN_START)} to {fmt_date(PLAN_END)}, within each line's weekly capacity. It aims to hold each "
         "SKU's weeks-of-supply target (net inventory against the coming weeks' forecast), minimising first the worst "
         "shortfall per line and week, then total shortfall, then stock above target. Orders ship as soon as stock "
         "exists, oldest first (an assumption; shipping is not decided). A checked property of every plan: a SKU is "
         "below target only while its line has run full every week, allowing for lead time. Demand forecast, capacity "
         "and opening stock and orders are the same in every scenario, except where a scenario lists events (edits to those "
         "numbers, made before planning); otherwise only the settings differ.")


def scenario_facts(label: str, case, V) -> str:
    t = priors.normalise(case.priors)
    c = V["card"]
    move = "yes" in set(t[(t["prior"] == "decides") & (t["applies_to"] == "move")]["value"])
    lines = [f"SCENARIO {label}: {case.name}" + (f" (based on {case.parent})" if case.parent else ""),
             "Settings: " + "; ".join(f"{CUSTOMERS[k]} ship from {ship_from(t, k)}" for k in CUSTOMERS)
             + f"; transfers Reno to PDC {'planned' if move else 'not planned'}"
             + "; build time " + ", ".join(f"{charts.LINE_WORDS[ln]} {wk(t[(t['prior'] == 'build_weeks') & (t['applies_to'] == ln)]['value'].iloc[0])}" for ln in LINES)
             + f"; transfer time {wk(t[t['prior'] == 'transfer_weeks']['value'].iloc[0])}"
             + "; targets " + ", ".join(f"{GROUPS.get(g, g)} {target_text(s)}" for g, s in targets(t).items()) + ".",
             "Results: all targets held from " + (fmt_date(c["All targets held from"]) if c["All targets held from"] is not None else "never")
             + "; open orders cleared from " + (fmt_date(c["Open orders cleared from"]) if c["Open orders cleared from"] is not None else "never")
             + f"; on-time fill rate {c['On-time fill rate']:.1%}; weeks below target (summed over SKU-site positions) "
             f"{c['Position-weeks below target']:,}; bikes built {c['Bikes built']:,}; bikes transferred to the PDC "
             f"{c['Bikes transferred to the PDC']:,}; average bikes in transit {c['Average bikes in transit']:,.0f}."]
    lines.append(event_facts(case, V))
    r = charts.plan_reading(V)
    for ln, d in r["lines"].items():
        lines.append(f"Line {charts.LINE_WORDS[ln]}: "
                     + (f"all capacity used from the start to w/c {fmt_date(d['full_from_start_to'])}"
                        + (f" (no capacity at all in {d['no_capacity_weeks']} of those weeks)" if d["no_capacity_weeks"] else "")
                        if d["full_from_start_to"] is not None else "spare capacity from the first week")
                     + f"; full in {d['weeks_full']} weeks in total; SKUs hold target from "
                     + (fmt_date(d["held_from"]) if d["held_from"] is not None else "never")
                     + f"; {d['below']} SKU-site weeks below target; {d['used']:.0%} of capacity used.")
    return "\n".join(lines)


def event_facts(case, V) -> str:
    """A scenario's events, each with the numbers it changed, from the computed plan's change report."""
    if not case.changes:
        return "Events: none (the data is as given)."
    rep = V["R"]["change_report"]
    out = []
    for i, c in enumerate(case.changes):
        r = rep.iloc[i]
        out.append(f"{events.title(c)}: {int(r['cells'])} numbers changed, total {r['before']:,.0f} -> {r['after']:,.0f} bikes"
                   + (f" (reason: {c.reason})" if c.reason else ""))
    return "Events (edits to the data this scenario plans from): " + "; ".join(out) + "."


def facts(items: list) -> str:
    """items: [(label, case, V), ...]; the first is the reference the others are compared with."""
    parts = [MODEL] + [scenario_facts(lab, case, V) for lab, case, V in items]
    if len(items) > 1:
        ref_lab, ref_case, _ = items[0]
        for lab, case, _ in items[1:]:
            d = describe_changes(ref_case.priors, case.priors)
            parts.append(f"SETTINGS IN {lab} THAT DIFFER FROM {ref_lab}: "
                         + ("; ".join(f"{r.Setting}: {r.From} -> {r.To}" for r in d.itertuples()) or "none") + ".")
            e = events.differences(ref_case.changes, case.changes)
            parts.append(f"EVENTS IN {lab} THAT DIFFER FROM {ref_lab}: "
                         + ("; ".join(f"{r.Setting.removeprefix('Event · ')}: {r.From} -> {r.To}" for r in e.itertuples())
                            or "none") + ".")
    return "\n\n".join(parts)
