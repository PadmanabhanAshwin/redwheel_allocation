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
CASES = [sc.CASE_A, sc.CASE_B, sc.CASE_E1, sc.CASE_E2, sc.CASE_E3, sc.CASE_E4, sc.CASE_E5, sc.CASE_P1,
         replace(sc.CASE_B, key="B+E3", name="Scenario B with E3's frames late", changes=sc.CASE_E3.changes, parent="B")]


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
    }
    return R, out


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
    A = doc["A"]
    built = lambda k: doc[k]["scorecard"]["Bikes built"]
    held = lambda k, ln="mtb-carbon": doc[k]["held_by_line"][ln]
    rules = [
        ("every scenario passes every plan check", all(v["checks"]["passed"] == v["checks"]["of"] for v in doc.values())),
        ("A builds 94,429 bikes and holds every target from 6 Sep 2027 (the frozen base)",
         built("A") == 94429 and doc["A"]["scorecard"]["All targets held from"] == "2027-09-06"),
        ("E1 takes 3 weeks of 375 off MTB carbon and makes all 1,125 back, nothing else",
         doc["E1"]["against_A"]["bikes_built_diff"] == 0 and all(doc["E1"]["against_A"]["mtb_carbon_line_weekly_diff"].get(t) == -375 for t in (26, 27, 28))
         and sum(v for t, v in doc["E1"]["against_A"]["mtb_carbon_line_weekly_diff"].items() if t > 28) == 1125
         and doc["E1"]["against_A"]["other_lines_identical"]),
        ("E2 builds exactly the orders it adds (636 -> 827: +191), all RW-4418, other lines identical",
         doc["E2"]["against_A"]["sku_totals_diff"] == {"RW-4418": 191} and doc["E2"]["against_A"]["other_lines_identical"]),
        ("E3 builds the same bikes at other times, other lines identical, no date moves",
         doc["E3"]["against_A"]["bikes_built_diff"] == 0 and doc["E3"]["against_A"]["other_lines_identical"]
         and doc["E3"]["held_by_line"] == A["held_by_line"]),
        ("E4 builds exactly the 300 it adds, all RW-4418, other lines identical",
         doc["E4"]["against_A"]["sku_totals_diff"] == {"RW-4418": 300} and doc["E4"]["against_A"]["other_lines_identical"]),
        ("E5 builds RW-9304 only in whole lots of 50, its total rounded up to a whole lot (A's 16,267 -> 16,300)",
         all(v % 50 == 0 for v in doc["E5"]["mtb_carbon_builds_by_week"]["RW-9304"])
         and doc["E5"]["builds_per_sku_total"]["RW-9304"] == 16300 and doc["A"]["builds_per_sku_total"]["RW-9304"] == 16267
         and doc["E5"]["against_A"]["sku_totals_diff"] == {"RW-9304": 33}),
        ("E5 moves no line's date and leaves the other lines identical",
         doc["E5"]["held_by_line"] == A["held_by_line"] and doc["E5"]["against_A"]["other_lines_identical"]),
        ("P1 builds the same bikes, holds every target on the same date, clears every order on the same date",
         doc["P1"]["against_A"]["bikes_built_diff"] == 0 and doc["P1"]["held_by_line"] == A["held_by_line"]
         and doc["P1"]["scorecard"]["Open orders cleared from"] == A["scorecard"]["Open orders cleared from"]),
        ("P1's ranking moves only MTB carbon; its 'orders past their date first' step also re-mixes road carbon "
         "(14 cells, weeks 3-7); base lines identical",
         doc["P1"]["against_A"]["cells_that_differ_by_line"] == {"mtb-base": 0, "mtb-carbon": 138, "road-base": 0, "road-carbon": 14}
         and all(3 <= t <= 7 for k in ("RW-1378", "RW-2984", "RW-3980") for t, v in
                 enumerate(np.array(res["P1"]["builds"].set_axis(res["P1"]["builds"].index.str.split("|").str[1]).loc[k])
                           - np.array(res["A"]["builds"].set_axis(res["A"]["builds"].index.str.split("|").str[1]).loc[k]), start=1) if v != 0)),
        ("P1 brings RW-9304 and RW-4418 to target sooner and RW-6416 on A's date",
         doc["P1"]["per_sku"]["RW-9304"]["at_target"] < A["per_sku"]["RW-9304"]["at_target"]
         and doc["P1"]["per_sku"]["RW-4418"]["at_target"] < A["per_sku"]["RW-4418"]["at_target"]
         and doc["P1"]["per_sku"]["RW-6416"]["at_target"] == A["per_sku"]["RW-6416"]["at_target"]),
        ("a change never brings a line's date earlier than its parent's, except by priority",
         all(held(k, ln) >= A["held_by_line"][ln] for k in ("E1", "E2", "E3", "E4", "E5") for ln in A["held_by_line"])),
        ("B+E3 builds B's bikes at other times; its MTB carbon date is no earlier than B's",
         doc["B+E3"]["against_parent"]["bikes_built_diff"] == 0 and held("B+E3") >= held("B")),
        ("the same 375 a week on MTB carbon in every full week of A, E2, E3, E4, E5 and P1 (weeks 1-52)",
         all(all(v == 375 for v in doc[k]["mtb_carbon_line_by_week"][:52]) for k in ("A", "E2", "E3", "E4", "E5", "P1"))),
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
                                  "every optimal plan is the solver's plan to within a bike (tests/test_engine.py, no ties)",
                    "tests": "run PYTHONPATH=src .venv/bin/python -m pytest -q to confirm the suite that pins these numbers"}
    json.dump(doc, open(OUT, "w"), indent=1, default=str)
    print("wrote", OUT, "| scenarios with a failing check:", failed or "none")
