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
    if A is not None and case.key != "A":
        d = by_sku(R).reindex(index=by_sku(A).index) - by_sku(A)
        out["against_A"] = {
            "bikes_built_diff": int(d.values.sum()),
            "sku_totals_diff": {k: int(v) for k, v in d.sum(axis=1).items() if v != 0},
            "cells_that_differ": int((d != 0).values.sum()),
            "mtb_carbon_line_weekly_diff": {int(t): int(v) for t, v in d.loc[MTB].sum().items() if v != 0},
            "other_lines_identical": bool((d.drop(index=MTB) == 0).all().all()),
        }
    return R, out


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
        print(f"{case.key:5s} checks {out['checks']['passed']}/{out['checks']['of']} | built {out['scorecard']['Bikes built']:,} "
              f"| all held {out['scorecard']['All targets held from']} | cleared {out['scorecard']['Open orders cleared from']} "
              f"| fill {out['scorecard']['On-time fill rate']:.4f} | MTB carbon {out['held_by_line']['mtb-carbon']}")
    failed = [k for k, v in doc.items() if v["checks"]["passed"] != v["checks"]["of"]]
    doc["_meta"] = {"weeks": weeks, "scenarios": [c.key for c in CASES], "all_checks_pass": not failed,
                    "tests": "run PYTHONPATH=src .venv/bin/python -m pytest -q to confirm the suite that pins these numbers"}
    json.dump(doc, open(OUT, "w"), indent=1, default=str)
    print("wrote", OUT, "| scenarios with a failing check:", failed or "none")
