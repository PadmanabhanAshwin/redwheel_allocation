"""Per-bike weekly detail for the scenario slides (A, R, R+ and the four scenarios on R+): builds, forecast and open orders, with each bike's line
and size. Every series is checked against docs/deck/deck_numbers.json (line totals, open orders by line, the scorecard
dates); the script stops if any differs, so the charts can only show the file's plan.
Usage: PYTHONPATH=src python dump_scenarios.py OUT.json"""
import json, sys, pathlib
import pandas as pd
from redwheel import scenarios as sc

DN = json.load(open(pathlib.Path(__file__).parent.parent / "deck_numbers.json"))
CASES = {"A": sc.CASE_A, "R": sc.CASE_R, "R+": sc.CASE_RP, "R+C26": sc.CASE_RP_C26, "R+E4": sc.CASE_RP_E4, "R+E5": sc.CASE_RP_E5, "R+P1": sc.CASE_RP_P1}
out = {"weeks": DN["_meta"]["weeks"]}
for key, case in CASES.items():
    R = sc.run_case(case)
    sku = R["m"]["dim_sku"].set_index("sku")
    builds = R["builds"]
    built = builds.groupby(builds.index.str.split("|").str[1]).sum()                    # sku x week
    weeks = list(range(1, 122))
    dem = R["demand"]; dem = dem.groupby(dem.index.get_level_values(0)).sum()
    opn = R["flows"]["open_orders"]; opn = opn.groupby(opn.index.get_level_values(0)).sum()
    d = {"sku": {}}
    for s in built.index:
        d["sku"][s] = {"line": sku.at[s, "line_id"], "size": sku.at[s, "size"],
                       "built": [int(round(built.at[s, t])) for t in weeks],
                       "forecast": [float(dem.at[s, t]) for t in weeks],
                       "open_orders": [float(opn.at[s, t]) for t in weeks]}
    for ln, series in DN[key]["builds_by_line_by_week"].items():                         # checks against the file
        mine = [sum(v["built"][i] for v in d["sku"].values() if v["line"] == ln) for i in range(121)]
        assert mine == [int(x) for x in series], (key, ln, "builds")
    for ln, series in DN[key]["owed_by_line_by_week"].items():
        mine = [sum(v["open_orders"][i] for v in d["sku"].values() if v["line"] == ln) for i in range(121)]
        assert max(abs(a - b) for a, b in zip(mine, series)) < 1.0, (key, ln, "open orders")
    card = sc.scorecard(R)
    for k in ("Open orders cleared from", "All targets held from"):
        assert str(card[k])[:10] == DN[key]["scorecard"][k][:10], (key, k)
    out[key] = d
json.dump(out, open(sys.argv[1], "w"))
print("ok:", {k: len(out[k]["sku"]) for k in CASES})
