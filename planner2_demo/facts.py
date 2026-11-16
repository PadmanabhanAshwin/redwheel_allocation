"""The facts sheet Ask answers from: the settings, changes, priority order and computed results of the scenarios on
screen, as plain text. Everything comes from computed plans and the scenarios' own definitions; no orders, customers
or stock records. The model is told to use nothing else, so a question the sheet cannot answer gets "the facts do
not say"."""
from __future__ import annotations

from planner2_demo.reading import LINE_WORDS, bike_dates, fdate, plan_reading
from redwheel import tunables as tu
from redwheel.config import PLAN_END, PLAN_START

MODEL = (f"How every plan is made: a linear programme plans weekly builds per bike on four Reno lines, "
         f"{fdate(PLAN_START)} to {fdate(PLAN_END)}, within each line's weekly capacity, so that each bike reaches its "
         "weeks-of-supply target (net inventory = stock minus open orders, against the coming weeks' forecast). On a "
         "full line it keeps every bike equally short of its target, unless a scenario has a priority order. Orders "
         "ship as soon as stock exists, oldest first (an assumption; shipping is not decided). A checked property of "
         "every plan: a bike is below target only while its line has run full (or the bike was at its build limit). "
         "Forecast, capacity, stock and open orders are the data as given, except where a scenario lists changes.")


def scenario_facts(label: str, case, V) -> str:
    c, r = V["card"], plan_reading(V)
    rep = tu.change_rows(case.changes, V["R"]["change_report"]) if case.changes else None
    out = [f"SCENARIO {label}: {case.name}" + (f" (made from {case.parent})" if case.parent else ""),
           "Rules: " + "; ".join(f"{k} {v}" for k, v in V["rules"].items()) + ".",
           "Changes to the data: " + ("; ".join(f"{w['What']}: {w['Change']} ({w['Numbers changed']} numbers, "
                                               f"{w['From']} -> {w['To']})" for w in rep.to_dict("records"))
                                      if rep is not None else "none") + ".",
           "Priority order: " + (" / ".join(tu.walk_lines(case)) if case.walk else "none; on a full line every bike "
                                 "is kept equally short of its target") + ".",
           f"Results: all targets held from {fdate(c['All targets held from'])}; open orders cleared from "
           f"{fdate(c['Open orders cleared from'])}; on-time fill {c['On-time fill rate']:.1%}; bikes built "
           f"{c['Bikes built']:,}; weeks below target, summed over bikes and stock sites, "
           f"{c['Position-weeks below target']:,}; bikes transferred to the PDC {c['Bikes transferred to the PDC']:,}."]
    for ln, d in r["lines"].items():
        out.append(f"Line {LINE_WORDS[ln]}: " + (f"full every week from the start to w/c {fdate(d['full_to'])}"
                                                 if d["full_to"] is not None else "spare capacity from the first week")
                   + (f" (no capacity at all in {d['no_capacity_weeks']} of those weeks)" if d["no_capacity_weeks"] else "")
                   + f"; at target from {fdate(d['held_from'])}; {d['used']:.0%} of its capacity used.")
    for s, (cleared, at) in bike_dates(V).items():
        out.append(f"Bike {s}: open orders cleared from {fdate(cleared)}; at target from {fdate(at)}; "
                   f"{int(V['built'].loc[s].sum()):,} built.")
    return "\n".join(out)


def facts(items: list) -> str:
    """items: [(label, case, V), ...]; the first is the reference the others are compared with."""
    parts = [MODEL] + [scenario_facts(lab, case, V) for lab, case, V in items]
    ref_lab, ref_case, _ = items[0]
    for lab, case, _ in items[1:]:
        d = tu.differences(ref_case, case)
        parts.append(f"WHAT {lab} SETS DIFFERENTLY FROM {ref_lab}: "
                     + ("; ".join(f"{r.Tunable} · {r.What}: {r.From} -> {r.To}" for r in d.itertuples()) or "nothing")
                     + ".")
    return "\n\n".join(parts)
