# PROBE, NOT PRODUCT. Evidence for docs/RANKED_WALK.md.
# It changes nothing in the repo: it captures the solver's own matrices from outside and re-solves them in stages.
# It depends on the solver's internal variable layout, so it will break when engine.decide changes; the real
# implementation (with tests) replaces it.   Run from the repo root:  .venv/bin/python scripts/ranked_walk_probe/walk.py
"""A walk over floors.

A FLOOR is a level a position's net inventory should not fall below, week by week. Three floors here:
    due    -(open orders not yet due that week)     below it: a customer is waiting past the date they asked for
    owed   0                                         below it: a customer is waiting
    cover  the weeks-of-supply target, in units      below it: short of cover   (today's only floor)
A STEP is (floor, which bikes, how they share): "even" keeps them equally short in weeks (the solver's own rule), or
"ranked" takes them one at a time in a stated order. The WALK is the steps in order: the solver makes step 1's
shortfall as small as it can, holds it, then step 2, ... and last trims stock above target, as today.
"""
import sys, time
sys.path[:0] = ["src", "tests", "scripts/ranked_walk_probe"]
import numpy as np, pandas as pd
from scipy import sparse
from redwheel import engine, scenarios as sc

REAL_DECIDE, REAL_LINPROG = engine.decide, engine.linprog
W_SHORT, W_WORST = 0.1, 1.0


def walk_decide(steps, floors=None, stats=None):
    """steps: [{"floor": name, "who": set of items or None (all), "share": "even" | "ranked", "order": [items]}].
    floors: {name: DataFrame position x week} for floors other than "owed" (0) and "cover" (the target)."""
    def decide(obj, free, target_units, weekly_demand, group, **kw):
        items = list(target_units.index); H = len(obj.weeks); nF, nR, nI = len(free), len(obj.resources), len(items)
        item_of = [s[0] if isinstance(s, tuple) else s for s in items]
        lines = sorted(set(group[s] for s in items)); line_ix = [lines.index(group[s]) for s in items]
        F = {"owed": np.zeros((nI, H)), "cover": target_units.to_numpy(float)}
        for k, v in (floors or {}).items():
            F[k] = v.loc[target_units.index, target_units.columns].to_numpy(float)
        flat = []                                           # ranked steps become one step per bike, in order
        for st in steps:
            members = [i for i in range(nI) if st.get("who") is None or item_of[i] in st["who"]]
            if st["share"] == "ranked":
                flat += [(st["floor"], [i for i in members if item_of[i] == it]) for it in st["order"]]
            else:
                flat.append((st["floor"], members))
        used = list(dict.fromkeys(f for f, _ in flat))
        o_short = nF * H + nR * H; o_exc = o_short + nI * H; o_worst = o_exc + nI * H

        def solve(c, A_ub, b_ub, A_eq, b_eq, bounds, method):
            t0 = time.time(); n0 = len(c); nS = len(flat)
            sh0 = {f: n0 + j * nI * H for j, f in enumerate(used)}                  # shortfall block of each floor
            w0 = n0 + len(used) * nI * H                                            # worst block: step x line x week
            n = w0 + nS * len(lines) * H
            A_ub = A_ub.tocsr(); net = A_ub[[3 * k for k in range(nI * H)], :].tolil()   # "-net - short <= -target" rows
            for k in range(nI * H): net[k, o_short + k] = 0
            net = sparse.hstack([net.tocsr(), sparse.csr_matrix((nI * H, n - n0))]).tolil()
            inv_d = c[o_short:o_exc] / W_SHORT                                       # 1 / weekly demand
            rows, rhs = [], []
            for f in used:                                                           # -net - shortfall_f <= -floor_f
                blk = net.copy()
                for k in range(nI * H): blk[k, sh0[f] + k] = -1.0
                rows.append(blk.tocsr()); rhs += list(-F[f].ravel())
            r, cc, v = [], [], []; k = 0
            for j, (f, members) in enumerate(flat):                                  # shortfall / d - worst <= 0
                for i in members:
                    for t in range(H):
                        r += [k, k]; cc += [sh0[f] + i * H + t, w0 + (j * len(lines) + line_ix[i]) * H + t]
                        v += [inv_d[i * H + t], -1.0]; k += 1
            rows.append(sparse.csr_matrix((v, (r, cc)), shape=(k, n))); rhs += [0.0] * k
            A = sparse.vstack([sparse.hstack([A_ub, sparse.csr_matrix((A_ub.shape[0], n - n0))])] + rows).tocsr()
            b = list(b_ub) + rhs
            Aeq = sparse.hstack([A_eq, sparse.csr_matrix((A_eq.shape[0], n - n0))]).tocsr()
            bnd = np.vstack([bounds, np.column_stack([np.zeros(n - n0), np.full(n - n0, np.inf)])])
            for j, (f, members) in enumerate(flat):
                cj = np.zeros(n)
                for i in members:
                    cj[sh0[f] + i * H:sh0[f] + (i + 1) * H] = W_SHORT * inv_d[i * H:(i + 1) * H]
                cj[w0 + j * len(lines) * H:w0 + (j + 1) * len(lines) * H] = W_WORST
                s_ = REAL_LINPROG(cj, A_ub=A, b_ub=b, A_eq=Aeq, b_eq=b_eq, bounds=bnd, method="highs")
                assert s_.status == 0, s_.message
                A = sparse.vstack([A, sparse.csr_matrix(cj)]).tocsr(); b = b + [s_.fun * (1 + 1e-9) + 1e-7]
            cf = np.zeros(n); cf[:nF * H] = c[:nF * H]; cf[o_exc:o_worst] = c[o_exc:o_worst]   # runs, stock above target
            sol = REAL_LINPROG(cf, A_ub=A, b_ub=b, A_eq=Aeq, b_eq=b_eq, bounds=bnd, method="highs")
            sol.x = sol.x[:n0]
            if stats is not None: stats.update(solves=nS + 1, seconds=round(time.time() - t0, 2))
            return sol
        engine.linprog = solve
        try:
            return REAL_DECIDE(obj, free, target_units, weekly_demand, group, **kw)
        finally:
            engine.linprog = REAL_LINPROG
    return decide


def run(case, steps, floors=None, **kw):
    engine.decide = walk_decide(steps, floors, **kw)
    try:
        return sc.run_case(case)
    finally:
        engine.decide = REAL_DECIDE


def not_yet_due(R):
    """Open orders at the snapshot not yet due in week t, per position x week: read from the order files' need-by
    dates (web orders carry none and count as due)."""
    fo = R["m"]["fact_orders"]; op = fo[fo["open_at_snapshot"]]
    start = R["obj"].weeks["week_start"].iloc[0]
    wk = ((pd.to_datetime(op["need_by_date"]) - start).dt.days // 7 + 1).fillna(0)
    H = len(R["obj"].weeks)
    out = pd.DataFrame(0.0, index=R["target_units"].index, columns=R["target_units"].columns)
    for key in out.index:
        mine = op["sku"] == key[0]
        out.loc[key] = [float(op.loc[mine & (wk > t), "qty"].sum()) for t in range(1, H + 1)]
    return out


def toy():
    """Two bikes, X and Y, on one line that builds 10 a week, four weeks, no new demand. X: 10 owed. Y: none owed.
    Both should hold 20. One week of demand is 10 bikes for both, so 'weeks short' = bikes short / 10."""
    from test_engine import two_skus_one_line
    obj = two_skus_one_line(capacity=10, H=4)
    obj.opening["order|A|C"] = 10                                   # X (item A): ten customers waiting
    tgt = pd.DataFrame([[20.0] * 4, [20.0] * 4], index=["A", "B"], columns=[1, 2, 3, 4])
    d, g = pd.Series({"A": 10.0, "B": 10.0}), pd.Series({"A": "L", "B": "L"})
    free = ["make|A|L", "make|B|L"]
    rules = {
        "today (one step: cover, shared evenly)": None,
        "walk: owed evenly, then cover evenly": [dict(floor="owed", share="even"), dict(floor="cover", share="even")],
        "walk: cover, Y before X": [dict(floor="cover", share="ranked", order=["B", "A"])],
        "walk: owed, then cover Y before X": [dict(floor="owed", share="even"), dict(floor="cover", share="ranked", order=["B", "A"])],
    }
    print("TOY: builds per week as X/Y, then net inventory at the end of each week as X/Y")
    for name, steps in rules.items():
        p = (REAL_DECIDE if steps is None else walk_decide(steps))(obj, free, tgt, d, g, w_run=1e-6)
        b = p.runs.round(2)
        netx = (-10 + b.loc["make|A|L"].cumsum()).tolist(); nety = b.loc["make|B|L"].cumsum().tolist()
        print(f"  {name:42s} builds {[f'{x:g}/{y:g}' for x, y in zip(b.loc['make|A|L'], b.loc['make|B|L'])]}"
              f"  net {[f'{x:g}/{y:g}' for x, y in zip(netx, nety)]}")


if __name__ == "__main__":
    from ranked_proto import facts
    toy()
    A = sc.run_case(sc.CASE_A); fa = facts(A)
    mtb = ["RW-9304", "RW-4418", "RW-6416"]; rest = set(A["m"]["dim_sku"]["sku"]) - set(mtb)
    nd = not_yet_due(A); due_floor = -nd
    H = len(A["obj"].weeks); wk = list(range(1, H + 1))
    def overdue_weeks(R):                                           # bike-weeks with a customer waiting past their date
        return int(((due_floor - R["net"][wk]) > 0.5).values.sum())
    def owed_units(R):                                              # open orders summed over weeks
        return int(R["flows"]["open_orders"][wk].values.sum())
    def show(name, R, st=None):
        f = facts(R); d = np.abs(R["builds"].values - A["builds"].values)
        print(f"\n{name}" + (f"  {st}" if st else ""))
        print(f"   orders cleared {f['open orders cleared']} | fill {f['fill']:.1%} | weeks below target {f['below']} | all held {f['all held']}"
              f" | bike-weeks past due {overdue_weeks(R)} | open orders x weeks {owed_units(R):,} | checks {f['checks']}")
        print(f"   MTB carbon orders cleared {[f['orders cleared'][k] for k in mtb]} | at target {[f['held'][k] for k in mtb]}")
        print(f"   builds differing from today's: {int((d > 0).sum())} cells, largest {int(d.max())}")
    show("TODAY", A)
    walks = {
      "1. cover evenly (today's rule, as a walk)": [dict(floor="cover", share="even")],
      "2. owed evenly, then cover evenly": [dict(floor="owed", share="even"), dict(floor="cover", share="even")],
      "3. due evenly, then owed evenly, then cover evenly": [dict(floor="due", share="even"), dict(floor="owed", share="even"), dict(floor="cover", share="even")],
      "4. owed evenly, then cover: MTB carbon by open orders, the rest evenly":
          [dict(floor="owed", share="even"), dict(floor="cover", who=set(mtb), share="ranked", order=mtb), dict(floor="cover", who=rest, share="even")],
      "5. owed: MTB carbon by open orders, the rest evenly; then cover the same way":
          [dict(floor="owed", who=set(mtb), share="ranked", order=mtb), dict(floor="owed", who=rest, share="even"),
           dict(floor="cover", who=set(mtb), share="ranked", order=mtb), dict(floor="cover", who=rest, share="even")],
      "6. THE TRAP. cover: MTB carbon by open orders, the rest evenly (no owed step)":
          [dict(floor="cover", who=set(mtb), share="ranked", order=mtb), dict(floor="cover", who=rest, share="even")],
    }
    for name, steps in walks.items():
        st = {}; show(name, run(sc.CASE_A, steps, {"due": due_floor}, stats=st), st)
