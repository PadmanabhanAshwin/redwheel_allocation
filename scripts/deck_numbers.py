"""The end-to-end run: every scenario through run_case, every plan check, and every number the deck and the UI quote,
written to one file. Usage: PYTHONPATH=src .venv/bin/python scripts/deck_numbers.py [docs/deck/deck_numbers.json]

The deck reads only this file. If a number is not here, it is not final."""
import json
import sys
from dataclasses import replace

import numpy as np
import pandas as pd

from redwheel import scenarios as sc

OUT = sys.argv[1] if len(sys.argv) > 1 else "docs/deck/deck_numbers.json"
MTB = ["RW-9304", "RW-4418", "RW-6416"]
CASES = [sc.CASE_A, *sc.R_CASES.values()]      # the final set (15 Nov): deck A, R, R+; live on R+ the rest
LIVE = ["R+C26", "R+E4", "R+E5", "R+P1"]
PROVED = [c.key for c in CASES]      # every scenario's deliveries checked against the most possible, every week
LOTS_GAP = {"R+E5": 3}               # lots cost bikes the flow LP could deliver: the most any plan delivers less this
LINES = ["road-base", "road-carbon", "mtb-base", "mtb-carbon"]
STORY = {"deck": ["A", "R", "R+"], "motivates": ["A", "R"], "hero": "R+", "live": LIVE,
         "mechanism": {"R+C26": "supply lost while customers wait", "R+E4": "demand added on a full line",
                       "R+E5": "a production rule", "R+P1": "a change to what the plan values"},
         "why": "A ships a bike the week it is built; no plant does. R is A with a week to build. R+ gives the carbon "
                "lines two weeks and the base lines one; it is the build plan. Neither build time is in the data.",
         "pruned": "B, B+E3, E1-E5 and P1 on A, a November line-down and a 2027 Christmas closure on R+: each showed "
                   "nothing the final set does not (docs/WORKING_NOTES.md D28). They stay in the code, not here."}

def by_sku(R):
    return R["builds"].set_axis(R["builds"].index.str.split("|").str[1])


def date_of(R, t):
    return str(R["obj"].weeks.set_index("t")["week_start"][int(t)].date()) if pd.notna(t) else None


def run(case, A):
    R = sc.run_case(case)
    H = len(R["obj"].weeks)
    w = list(range(1, H + 1))
    checks = sc.checks(R)
    s = sc.scorecard(R)
    held = sc.held_from(R["at_target"])
    cleared = sc.held_from(R["flows"]["open_orders"][w] < 0.5)
    b = by_sku(R)
    per_sku = {}
    for k in held.index:
        key = k[0] if k[1] == "CMH+RENO" else f"{k[0]}@{k[1]}"
        per_sku[key] = {"at_target": date_of(R, held[k]), "orders_cleared": date_of(R, cleared[k]),
                        "weeks_below_target": int((~R["at_target"].loc[[k]]).values.sum()),
                        "bike_weeks_above_target": int(round((R["net"].loc[[k], w] - R["target_units"].loc[[k]]).clip(lower=0).values.sum()))}
    out = {
        "name": case.name, "summary": case.summary, "parent": case.parent or None,
        "changes": [{"what": str(c.select), "field": c.field, "op": c.op, "value": c.value, "weeks": [c.from_t, c.to_t], "why": c.reason}
                    for c in case.changes],
        "walk": [{"floor": st["floor"], "positions": len(st["positions"]), "worst_weeks_short": round(st["worst"], 2),
                  "total_weeks_short": round(st["total"], 2)} for st in R["lp"].steps] or None,
        "checks": {"passed": int(checks["pass"].sum()), "of": len(checks),
                   "rows": [{"check": r["check"], "value": r["value"], "pass": bool(r["pass"])} for _, r in checks.iterrows()]},
        "scorecard": {k: (str(v.date()) if hasattr(v, "date") else (round(float(v), 4) if isinstance(v, float) else v))
                      for k, v in s.items()},
        "held_by_line": {ln: str(d.date()) for ln, d in sc.held_by_line(R).max(axis=1).items()},
        "per_sku": per_sku,
        "builds_per_sku_total": b.sum(axis=1).astype(int).to_dict(),
        "mtb_carbon_builds_by_week": {k: [int(v) for v in b.loc[k, w]] for k in MTB},
        "mtb_carbon_line_by_week": [int(v) for v in b.loc[MTB, w].sum()],
        "mtb_carbon_capacity_by_week": [int(v) for v in R["obj"].arrivals.loc["capacity||RENO/mtb-carbon", w]],
        "weeks_of_supply_mtb": {(k if p == "CMH+RENO" else f"{k}@{p}"): [round(float(R["wos"].loc[(k, p), t]), 2) for t in w]
                                for (k, p) in R["wos"].index if k in MTB},
        "target_weeks_mtb": {k: [float(R["target_wos"].loc[(k, p), t]) for t in w] for (k, p) in R["target_wos"].index if k in MTB and p != "CMH"},
        "build_weeks": dict(case.build_weeks),
        "builds_by_line_by_week": {ln: [int(v) for v in line_rows(R["builds"], ln)[w].sum()] for ln in LINES},
        "capacity_by_line_by_week": {ln: [int(v) for v in R["obj"].arrivals.loc[f"capacity||RENO/{ln}", w]] for ln in LINES},
        "stock_above_target_by_line_by_week": {ln: [int(round(v)) for v in (R["net"][w] - R["target_units"][w]).clip(lower=0)
                                                    .groupby(R["line"]).sum().loc[ln]] for ln in LINES},
        "owed_by_line_by_week": {ln: [int(round(v)) for v in R["flows"]["open_orders"][w].groupby(R["line"]).sum().loc[ln]]
                                 for ln in LINES},
    }
    if case.key in PROVED:
        d = sc.most_delivered(R)
        out["deliveries"] = {
            "claim": "no plan delivers more by any week on any line, with this scenario's object and rules",
            "weeks_checked": int(d["plan"].shape[1]), "lines_checked": int(d["plan"].shape[0]),
            "largest_gap_bikes": round(d["gap"], 6), "certificate_worst": {k: float(v) for k, v in d["certificate"].items()},
            "fewest_owed_by_line_by_week": {ln: [int(round(v)) for v in d["fewest"].loc[ln]] for ln in LINES}}
    return R, out


def line_rows(df, ln):
    return df[df.index.str.endswith("/" + ln)]


def against(R, P, line_of):
    """What a scenario's whole-bike plan does differently from another's."""
    d = by_sku(R).reindex(index=by_sku(P).index) - by_sku(P)
    return {
        "against": P["case"].key,
        "bikes_built_diff": int(d.values.sum()),
        "sku_totals_diff": {k: int(v) for k, v in d.sum(axis=1).items() if v != 0},
        "cells_that_differ": int((d != 0).values.sum()),
        "cells_that_differ_by_line": {ln: int((d.loc[[k for k in d.index if line_of[k] == ln]] != 0).values.sum())
                                      for ln in sorted(set(line_of.values))},
        "mtb_carbon_line_weekly_diff": {int(t): int(v) for t, v in d.loc[MTB].sum().items() if v != 0},
        "other_lines_identical": bool((d.drop(index=MTB) == 0).all().all()),
    }


def consistency(doc, res):
    """Relations the scenarios must keep with their changes and with each other. The file is not written if any fails."""
    sc_ = lambda k, f: doc[k]["scorecard"][f]
    held = lambda k: doc[k]["held_by_line"]
    at = lambda k, s: doc[k]["per_sku"][s]["at_target"]
    wk = lambda d: pd.Timestamp(d)
    shift = lambda k, p, ln="mtb-carbon": (wk(held(k)[ln]) - wk(held(p)[ln])).days // 7
    cleared = lambda k: wk(sc_(k, "Open orders cleared from"))
    lb = lambda k, ln: doc[k]["builds_by_line_by_week"][ln]
    owed = lambda k, ln: doc[k]["owed_by_line_by_week"][ln]
    cap = lambda k, ln: doc[k]["capacity_by_line_by_week"][ln]
    par = lambda k: doc[k]["against_parent"]
    rp, c26 = "R+", "R+C26"
    late = lambda k: [a - b for a, b in zip(owed(k, "mtb-carbon"), owed(rp, "mtb-carbon"))]
    others_owed_same = lambda k: all(owed(k, ln) == owed(rp, ln) for ln in LINES if ln != "mtb-carbon")
    rules = [
        ("every scenario passes every plan check", all(v["checks"]["passed"] == v["checks"]["of"] for v in doc.values())),
        ("A builds 94,429 bikes and holds every target from 6 Sep 2027 (the frozen base)",
         sc_("A", "Bikes built") == 94429 and sc_("A", "All targets held from") == "2027-09-06"),
        ("R and R+ build A's bikes, every SKU's total as A's",
         all(doc[k]["against_A"]["bikes_built_diff"] == 0 and doc[k]["against_A"]["sku_totals_diff"] == {} for k in ("R", rp))),
        ("a build time only delays: no line's date in R earlier than A's, none in R+ earlier than R's; "
         "orders cleared A < R < R+",
         all(held("R")[ln] >= held("A")[ln] and held(rp)[ln] >= held("R")[ln] for ln in LINES)
         and cleared("A") < cleared("R") < cleared(rp)),
        ("R takes a week from the line to stock on every line; R+ two on the carbon lines and one on the base lines",
         doc["R"]["build_weeks"] == {ln: 1 for ln in LINES}
         and doc[rp]["build_weeks"] == {ln: (2 if "carbon" in ln else 1) for ln in LINES}),
        ("R+C26: every line closed 21 and 28 Dec 2026; the same bikes on every SKU; only MTB carbon customers wait, "
         "none before 4 Jan 2027 (two weeks to build: December's deliveries were on the line before the closure), "
         "all delivered by 8 Feb 2027",
         all(lb(c26, ln)[15] == lb(c26, ln)[16] == 0 for ln in LINES) and par(c26)["sku_totals_diff"] == {}
         and others_owed_same(c26) and max(map(abs, late(c26)[:17])) == 0 and min(late(c26)[17:22]) > 0
         and max(map(abs, late(c26)[22:])) == 0 and sc_(c26, "Open orders cleared from") == "2027-02-08"),
        ("R+C26: lines full before the closure cannot build ahead; road base, the one with room, builds ahead exactly "
         "what R+ builds in the closed weeks",
         all(lb(rp, ln)[t] == cap(rp, ln)[t] for ln in ("road-carbon", "mtb-base", "mtb-carbon") for t in range(15))
         and max(np.cumsum(lb(c26, "road-base")) - np.cumsum(lb(rp, "road-base"))) == lb(rp, "road-base")[15] + lb(rp, "road-base")[16]),
        ("R+E4 builds exactly the 300 it adds, all RW-4418; other lines identical; only MTB carbon customers wait; "
         "MTB carbon at target 1 week later, orders cleared 2 weeks later",
         par("R+E4")["sku_totals_diff"] == {"RW-4418": 300} and par("R+E4")["other_lines_identical"]
         and others_owed_same("R+E4") and max(late("R+E4")) == 300
         and shift("R+E4", rp) == 1 and (cleared("R+E4") - cleared(rp)).days == 14),
        ("R+E5 builds RW-9304 only in whole lots of 50, its total rounded up to a whole lot (16,267 -> 16,300); other "
         "lines identical; no line's date moves; the line never short of capacity in a week R+ ran it full",
         all(v % 50 == 0 for v in doc["R+E5"]["mtb_carbon_builds_by_week"]["RW-9304"])
         and doc["R+E5"]["builds_per_sku_total"]["RW-9304"] == 16300 and doc[rp]["builds_per_sku_total"]["RW-9304"] == 16267
         and par("R+E5")["sku_totals_diff"] == {"RW-9304": 33} and par("R+E5")["other_lines_identical"]
         and held("R+E5") == held(rp)
         and all(lb("R+E5", "mtb-carbon")[t] == cap(rp, "mtb-carbon")[t] for t in range(121)
                 if lb(rp, "mtb-carbon")[t] == cap(rp, "mtb-carbon")[t] and cap(rp, "mtb-carbon")[t] > 0)),
        ("R+E5: the lots' cost to customers is 3 RW-9304 bikes a week late (11 Jan 2027), so orders clear 18 Jan",
         others_owed_same("R+E5") and [(t, v) for t, v in enumerate(late("R+E5"), 1) if v] == [(19, 3)]
         and sc_("R+E5", "Open orders cleared from") == "2027-01-18"),
        ("R+P1 builds R+'s bikes, holds every line's target on R+'s date, clears every order on R+'s date, the same fill",
         par("R+P1")["bikes_built_diff"] == 0 and par("R+P1")["sku_totals_diff"] == {} and held("R+P1") == held(rp)
         and sc_("R+P1", "Open orders cleared from") == sc_(rp, "Open orders cleared from")
         and sc_("R+P1", "On-time fill rate") == sc_(rp, "On-time fill rate")),
        ("R+P1 brings RW-9304 (31 May 2027) and RW-4418 (13 Sep) to target sooner, RW-6416 on R+'s date; it moves "
         "MTB carbon, and road carbon (its first step, orders past their date, covers every line); base lines identical",
         at("R+P1", "RW-9304") == "2027-05-31" and at("R+P1", "RW-4418") == "2027-09-13"
         and at("R+P1", "RW-6416") == at(rp, "RW-6416")
         and par("R+P1")["cells_that_differ_by_line"]["mtb-base"] == par("R+P1")["cells_that_differ_by_line"]["road-base"] == 0
         and par("R+P1")["cells_that_differ_by_line"]["road-carbon"] > 0
         and [st["floor"] for st in doc["R+P1"]["walk"]][0] == "due"),
        ("a change never brings a line's date earlier than R+'s",
         all(held(k)[ln] >= held(rp)[ln] for k in LIVE for ln in LINES)),
        ("every scenario delivers the most any plan could by every week, on every line, every solve certified; "
         "with lots, within the bikes the lots cost (R+E5: 3)",
         all(doc[k]["deliveries"]["largest_gap_bikes"] <= LOTS_GAP.get(k, 0) + 1e-6
             and max(doc[k]["deliveries"]["certificate_worst"].values()) <= 1e-7
             and doc[k]["deliveries"]["weeks_checked"] == 121 and doc[k]["deliveries"]["lines_checked"] == 4 for k in PROVED)),
    ]
    return [{"rule": r, "holds": bool(ok)} for r, ok in rules]


if __name__ == "__main__":
    weeks = None
    results, doc = {}, {}
    A = None
    for case in CASES:
        R, out = run(case, A)
        if case.key == "A":
            A = R
            weeks = {int(t): str(d.date()) for t, d in R["obj"].weeks.set_index("t")["week_start"].items()}
        results[case.key] = R
        doc[case.key] = out
    line_of = A["m"]["dim_sku"].set_index("sku")["line_id"]
    for case in CASES:
        if case.key != "A":
            doc[case.key]["against_A"] = against(results[case.key], A, line_of)
        if case.parent and case.parent in results:
            doc[case.key]["against_parent"] = against(results[case.key], results[case.parent], line_of)
    for case in CASES:
        out = doc[case.key]
        print(f"{case.key:5s} checks {out['checks']['passed']}/{out['checks']['of']} | built {out['scorecard']['Bikes built']:,} "
              f"| all held {out['scorecard']['All targets held from']} | cleared {out['scorecard']['Open orders cleared from']} "
              f"| fill {out['scorecard']['On-time fill rate']:.4f} | MTB carbon {out['held_by_line']['mtb-carbon']}")
    failed = [k for k, v in doc.items() if v["checks"]["passed"] != v["checks"]["of"]]
    rules = consistency(doc, results)
    for r in rules:
        print(("  ok   " if r["holds"] else "  FAIL ") + r["rule"])
    if not all(r["holds"] for r in rules):
        sys.exit("consistency failed: not written")
    import subprocess
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    doc["_meta"] = {"weeks": weeks, "scenarios": [c.key for c in CASES], "all_checks_pass": not failed,
                    "consistency": rules, "code_at_commit": commit + " (plus any uncommitted change)",
                    "optimality": "every solve certified from its duals and re-solved by interior point (tests/test_optimality.py); "
                                  "every optimal plan is the solver's plan to within what the solver's tolerance buys, under "
                                  "2 bikes (tests/test_engine.py, no ties)",
                    "deliveries": "every scenario: at every week and on every line, the fewest units any plan could "
                                  "leave owed, solved and certified, equals the plan's; R+E5 within 3 bikes in one week, "
                                  "the cost of lots (scenarios.most_delivered; tests/test_r_cases.py)",
                    "story": STORY,
                    "tests": "run PYTHONPATH=src .venv/bin/python -m pytest -q to confirm the suite that pins these numbers"}
    json.dump(doc, open(OUT, "w"), indent=1, default=str)
    print("wrote", OUT, "| scenarios with a failing check:", failed or "none")
