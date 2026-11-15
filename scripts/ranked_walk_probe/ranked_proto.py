# PROBE, NOT PRODUCT. Evidence for docs/RANKED_WALK.md.
# It changes nothing in the repo: it captures the solver's own matrices from outside and re-solves them in stages.
# It depends on the solver's internal variable layout, so it will break when engine.decide changes; the real
# implementation (with tests) replaces it.   Run from the repo root:  .venv/bin/python scripts/ranked_walk_probe/ranked_proto.py
"""Prototype of a ranked walk (scratch only; no repo change). The solver's own matrices are captured and solved in
stages: tier 1's shortfall first, held, then tier 2's, ...; last, stock above target and runs. Positions in the same
tier on the same line share shortage evenly, exactly as today. One tier = today's solve, untouched."""
import sys, time
sys.path[:0] = ["src", "scripts/ranked_walk_probe"]
import numpy as np, pandas as pd
from scipy import sparse
from redwheel import engine, scenarios as sc

REAL_DECIDE, REAL_LINPROG = engine.decide, engine.linprog

def ranked(tier_of_sku: dict, mode="staged", rho=1e-3, stats=None):
    def decide(obj, free, target_units, weekly_demand, group, **kw):
        items = list(target_units.index)
        tier = pd.Series([tier_of_sku.get(s[0], 1) for s in items], index=target_units.index)
        K = sorted(tier.unique())
        if len(K) == 1:
            return REAL_DECIDE(obj, free, target_units, weekly_demand, group, **kw)
        group2 = pd.Series([f"{group[s]}|{tier[s]:03d}" for s in items], index=target_units.index)
        H, nF, nR, nI = len(obj.weeks), len(free), len(obj.resources), len(items)
        groups = sorted(group2.unique())
        o_short = nF * H + nR * H; o_exc = o_short + nI * H; o_worst = o_exc + nI * H
        def part(c, k):                      # the objective's terms that belong to tier k
            ck = np.zeros_like(c)
            for si, s in enumerate(items):
                if tier[s] == k: ck[o_short + si * H:o_short + (si + 1) * H] = c[o_short + si * H:o_short + (si + 1) * H]
            for gi, g in enumerate(groups):
                if int(g.split("|")[1]) == k: ck[o_worst + gi * H:o_worst + (gi + 1) * H] = c[o_worst + gi * H:o_worst + (gi + 1) * H]
            return ck
        def solve(c, A_ub, b_ub, A_eq, b_eq, bounds, method):
            t0 = time.time(); n = 0
            if mode == "weights":            # one solve, tier k's terms scaled by rho^(k-1)
                cw = np.zeros_like(c); cw[:nF * H] = c[:nF * H]; cw[o_exc:o_worst] = c[o_exc:o_worst]
                for j, k in enumerate(K): cw += part(c, k) * rho ** j
                sol = REAL_LINPROG(cw, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs"); n = 1
            else:
                A, b = A_ub, list(b_ub)
                for k in K:
                    ck = part(c, k)
                    s_ = REAL_LINPROG(ck, A_ub=A, b_ub=b, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs"); n += 1
                    assert s_.status == 0, s_.message
                    A = sparse.vstack([A, sparse.csr_matrix(ck)]).tocsr(); b = b + [s_.fun * (1 + 1e-9) + 1e-7]
                cf = np.zeros_like(c); cf[:nF * H] = c[:nF * H]; cf[o_exc:o_worst] = c[o_exc:o_worst]
                sol = REAL_LINPROG(cf, A_ub=A, b_ub=b, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs"); n += 1
            if stats is not None: stats.update(solves=n, seconds=time.time() - t0)
            return sol
        engine.linprog = solve
        try:
            return REAL_DECIDE(obj, free, target_units, weekly_demand, group2, **kw)
        finally:
            engine.linprog = REAL_LINPROG
    return decide

def run(case, tiers, **kw):
    engine.decide = ranked(tiers, **kw)
    try:
        return sc.run_case(case)
    finally:
        engine.decide = REAL_DECIDE

def facts(R):
    o = R["obj"]; date = o.weeks.set_index("t")["week_start"]; H = len(o.weeks); wk = list(range(1, H + 1))
    held = sc.held_from(R["at_target"]); s = sc.scorecard(R); c = sc.checks(R)
    short_w = ((R["target_units"] - R["net"][wk]).clip(lower=0) / R["weekly_demand"])
    oo = R["flows"]["open_orders"]
    cleared = sc.held_from(oo[wk] < 0.5)
    return {"held": {k[0]: str(date[int(v)].date()) if pd.notna(v) else "never" for k, v in held.items()},
            "orders cleared": {k[0]: str(date[int(v)].date()) if pd.notna(v) else "never" for k, v in cleared.items()},
            "all held": str(s["All targets held from"])[:10], "open orders cleared": str(s["Open orders cleared from"])[:10],
            "below": s["Position-weeks below target"], "fill": round(s["On-time fill rate"], 4), "built": s["Bikes built"],
            "weeks short, sum": round(float(short_w.values.sum()), 1), "weeks short, worst": round(float(short_w.values.max()), 1),
            "checks": f"{int(c['pass'].sum())}/{len(c)}"}

def walk_respected(R, tiers):
    """The defining property: in a week a lower-ranked bike is built, every higher-ranked bike on its line is at target
    (to within one bike, for rounding). Returns the number of (line, week) cases that break it."""
    b = R["builds"].set_axis(R["builds"].index.str.split("|").str[1]); H = b.shape[1]
    net = R["net"].droplevel("pool"); tu = R["target_units"].droplevel("pool")
    line = R["m"]["dim_sku"].set_index("sku")["line_id"]; bad = 0
    for ln in line.unique():
        skus = [s for s in line.index if line[s] == ln]
        for t in range(1, H + 1):
            for lo in skus:
                if b.at[lo, t] > 1:
                    for hi in skus:
                        if tiers.get(hi, 1) < tiers.get(lo, 1) and net.at[hi, t] < tu.at[hi, t] - 1.5:
                            bad += 1
    return bad

if __name__ == "__main__":
    MTB = ["RW-4418", "RW-6416", "RW-9304"]
    show = lambda f: {k: v for k, v in f.items() if k not in ("held", "orders cleared")}
    A = sc.run_case(sc.CASE_A); fa = facts(A)
    print("EVEN (today)          :", show(fa)); print("   held   :", {k: fa["held"][k] for k in MTB}); print("   cleared:", {k: fa["orders cleared"][k] for k in MTB})
    one = run(sc.CASE_A, {})                                   # no ranking: must be today's plan exactly
    print("no ranking = today's plan exactly:", one["builds"].equals(A["builds"]))
    for name, order in (("by backlog (9304,4418,6416)", ["RW-9304", "RW-4418", "RW-6416"]),
                        ("reverse   (6416,4418,9304)", ["RW-6416", "RW-4418", "RW-9304"])):
        tiers = {s: i + 1 for i, s in enumerate(order)}; st = {}
        R = run(sc.CASE_A, tiers, stats=st); f = facts(R)
        print(f"\nRANKED MTB carbon {name}:", show(f), "|", st)
        print("   held   :", {k: f["held"][k] for k in order}); print("   cleared:", {k: f["orders cleared"][k] for k in order})
        print("   walk respected (violations):", walk_respected(R, tiers), "| other lines identical to today:",
              bool((R["builds"][~R["builds"].index.str.contains("mtb-carbon")] == A["builds"][~A["builds"].index.str.contains("mtb-carbon")]).all().all()))
        for rho in (1e-1, 1e-2, 1e-4):
            W = run(sc.CASE_A, tiers, mode="weights", rho=rho)
            d = np.abs(W["builds"].values - R["builds"].values)
            print(f"   one solve with weights 1, {rho:g}, {rho**2:g}: builds differ from the staged walk in {int((d > 0).sum())} cells, largest {int(d.max())} | walk violations {walk_respected(W, tiers)}")
