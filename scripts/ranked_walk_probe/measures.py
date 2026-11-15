# PROBE, NOT PRODUCT. Evidence for docs/RANKED_WALK.md section 4: the per-bike measures a priority order could use.
# Run from the repo root:  .venv/bin/python scripts/ranked_walk_probe/measures.py
"""What a priority order could be based on: per-SKU measures read from the object and the base plan's inputs."""
import sys
sys.path[:0] = ["src"]
import pandas as pd
pd.set_option("display.width", 220)
from redwheel import aux_fns, rtn, scenarios as sc
A = sc.run_case(sc.CASE_A)
o, sku = A["obj"], A["m"]["dim_sku"].set_index("sku")
rows = []
for s in sku.index:
    k = (s, "CMH+RENO")
    backlog = float(o.opening[[f"order|{s}|{c}" for c in ("WEB", "DEALERS", "COMMERCIAL")]].sum())
    stock = float(o.opening[[f"inventory|{s}|{x}" for x in ("RENO", "CMH")]].sum())
    dem = A["demand"].loc[k]
    by_ch = {c: float(o.arrivals.loc[f"order|{s}|{c}"].sum()) for c in ("WEB", "DEALERS", "COMMERCIAL")}
    rows.append({"sku": s, "line": sku.at[s, "line_id"], "size": sku.at[s, "size"],
                 "backlog": backlog, "stock": stock, "net0": stock - backlog,
                 "fc/wk (first 13)": round(float(dem.loc[1:13].mean()), 1),
                 "backlog weeks": round(backlog / float(dem.loc[1:13].mean()), 1),
                 "wos0": round(float(A["wos"].at[k, 0]), 1), "target": float(A["target_wos"].at[k, 1]),
                 "gap wk": round(float(A["target_wos"].at[k, 1] - A["wos"].at[k, 0]), 1),
                 "forecast total": int(dem.loc[1:121].sum()),
                 "dealer share": round(by_ch["DEALERS"] / sum(by_ch.values()), 2)})
t = pd.DataFrame(rows).sort_values(["line", "sku"]).set_index("sku")
print(t.to_string())
held = sc.held_from(A["at_target"])
date = o.weeks.set_index("t")["week_start"]
print("\nbase plan (even rule): week each SKU holds target from:", {k[0]: str(date[int(v)].date()) for k, v in held.items()})
