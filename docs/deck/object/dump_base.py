"""Base case (scenario A), MTB carbon line: builds and weeks short of target per SKU, in the solver's own measure.
Usage: PYTHONPATH=src python dump_base.py OUT.json"""
import json, sys
from redwheel import engine, scenarios as sc
R = sc.run_case(sc.CASE_A); S = ["RW-4418", "RW-6416", "RW-9304"]; T = list(range(1, 61))
net, tu, tw, b = R["net"], R["target_units"], R["target_wos"], R["builds"]
wd = engine.window_demand(tu, tw)                       # target units / target weeks, per week: what the solver divides by
ix = {k[0]: k for k in net.index if k[0] in S}
key = lambda s: [k for k in b.index if s in k][0]
out = {"weeks": {int(t): str(d.date()) for t, d in R["obj"].weeks.set_index("t")["week_start"].items() if t <= 60},
       "target_weeks": {s: float(tw.at[ix[s], 1]) for s in S},
       "rate": {s: [round(float(wd.at[ix[s], t]), 2) for t in range(1, 7)] for s in S},
       "short_weeks": {s: [round(max(float(tu.at[ix[s], t] - net.at[ix[s], t]), 0) / float(wd.at[ix[s], t]), 3) for t in T] for s in S},
       "builds": {s: [int(b.at[key(s), t]) for t in T] for s in S},
       "net": {s: [float(net.at[ix[s], t]) for t in range(0, 7)] for s in S},
       "target_units": {s: [float(tu.at[ix[s], t]) for t in range(1, 7)] for s in S}}
out["on_target_week"] = min(t for t in T if all(out["short_weeks"][s][t - 1] == 0 for s in S))
out["line_full_through"] = max(t for t in T if all(sum(out["builds"][s][u - 1] for s in S) == 375 for u in range(1, t + 1)))
out["short_units"] = {s: [round(max(float(tu.at[ix[s], t] - net.at[ix[s], t]), 0)) for t in T] for s in S}
dem = R["demand"]
out["demand_all"] = {s: [float(dem.at[ix[s], t]) for t in T] for s in S}
out["target_all"] = {s: [float(tu.at[ix[s], t]) for t in T] for s in S}
out["net_all"] = {s: [float(net.at[ix[s], t]) for t in [0] + T] for s in S}
sc_ = sc.scorecard(R)
out["scorecard"] = {k: str(sc_[k]) for k in ("Open orders cleared from", "On-time fill rate", "Position-weeks below target", "All targets held from")}
wk = list(range(1, len(R["obj"].weeks) + 1)); cleared = sc.held_from(R["flows"]["open_orders"][wk] < 0.5)
out["orders_cleared"] = {s: str(R["obj"].weeks.set_index("t")["week_start"][int(cleared[ix[s]])].date()) for s in S}
out["checks"] = [int(sc.checks(R)["pass"].sum()), len(sc.checks(R))]
json.dump(out, open(sys.argv[1], "w"), indent=1)
print(out["scorecard"], out["orders_cleared"], out["checks"])
for s in S: print(s, "short", [round(v, 1) for v in out["short_weeks"][s][:6]], "builds", out["builds"][s][:6], "rate", out["rate"][s][:2])
print("on target", out["on_target_week"], out["weeks"][out["on_target_week"]], "line full through", out["line_full_through"])
