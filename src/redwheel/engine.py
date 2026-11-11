"""Decide: choose task runs on the RTN object with an LP (HiGHS via scipy).

Generic. The equation rows come from the object's arrows, exactly as in `rtn.levels`.

    variables   runs[i, t]   for the free tasks (all other runs are zero)
                level[r, t]  for every resource, t = 1..H              (>= 0)
                short[s, t]  units net position is below target         (>= 0)
                excess[s, t] units net position is above target         (>= 0)
                worst[g, t]  largest shortfall in weeks within group g  (>= 0)

    equation    level[r,t] - carry[r]*level[r,t-1] - sum amount*runs[i,t-delay] = arrival[r,t]
                (level[r,0] is the opening level, moved to the right-hand side)
    target      net[s,t] + short[s,t] >= target_units[s,t]
                net[s,t] - excess[s,t] <= target_units[s,t]
    fairness    worst[g,t] >= short[s,t] / weekly_demand[s]   for s in g

    minimise    w_worst * sum worst  +  w_short * sum short/weekly_demand  +  w_excess * sum excess/weekly_demand
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import linprog

from redwheel import rtn


@dataclass
class Plan:
    runs: pd.DataFrame      # task_id x t (1..H), free tasks only
    levels: pd.DataFrame    # resource_id x t (0..H), as the LP sees them
    short: pd.DataFrame     # item x t (1..H), units below target
    objective: float


def round_runs(obj: rtn.RTN, runs: pd.DataFrame) -> pd.DataFrame:
    """Whole-number runs for tasks that draw one unit of a capacity resource per run.

    Per task, cumulative runs are rounded up, so a rounded plan is never behind the LP. Where that
    would exceed a capacity in some week, the excess is taken back one unit at a time from the
    tasks rounded up the most. Weeks are processed in order, so cumulative runs stay within one
    unit of the LP: ahead by less than 1, or (only in a week the capacity is used up) behind by
    less than 1."""
    a = obj.arrows[obj.arrows["task_id"].isin(runs.index)]
    cap_arrows = a[a["resource_id"].str.startswith("capacity|")]
    if not (cap_arrows["amount"] == -1).all() or cap_arrows["task_id"].duplicated().any():
        raise ValueError("round_runs needs every task to use exactly one unit of one capacity")
    if set(cap_arrows["task_id"]) != set(runs.index):
        raise ValueError("every task to round must draw on a capacity resource")

    lp_cum = runs.cumsum(axis=1)
    out = pd.DataFrame(0, index=runs.index, columns=runs.columns, dtype=int)
    for cap_id, tasks in cap_arrows.groupby("resource_id")["task_id"]:
        tasks = list(tasks)
        done = pd.Series(0, index=tasks)                  # whole runs so far
        for t in runs.columns:
            k = int(round(obj.arrivals.at[cap_id, t]))
            want = np.ceil(lp_cum.loc[tasks, t] - 1e-9).astype(int)    # cumulative, rounded up
            build = (want - done).clip(lower=0)
            for _ in range(int(build.sum()) - k):          # take back one unit at a time
                ahead = (done + build - lp_cum.loc[tasks, t])[build > 0]
                build[ahead.idxmax()] -= 1
            out.loc[tasks, t] = build.to_numpy()
            done += build
    return out


def forward_sum(demand: pd.DataFrame, n: pd.DataFrame) -> pd.DataFrame:
    """Units of demand in weeks t+1 .. t+n[s,t]. demand: item x t (1..T); n: item x t (1..H), whole weeks."""
    cum = demand.cumsum(axis=1)
    cum.insert(0, 0, 0.0)
    out = pd.DataFrame(index=n.index, columns=n.columns, dtype=float)
    for s in n.index:
        for t in n.columns:
            out.at[s, t] = cum.at[s, t + int(n.at[s, t])] - cum.at[s, t]
    return out


def decide(obj: rtn.RTN, free: list[str], target_units: pd.DataFrame, weekly_demand: pd.Series,
           group: pd.Series, w_worst: float = 1.0, w_short: float = 0.1, w_excess: float = 0.001) -> Plan:
    """free: task ids the LP may run. target_units: item x t (1..H). group: item -> fairness group."""
    H = len(obj.weeks)
    res = obj.resources.reset_index(drop=True)
    items = list(target_units.index)
    groups = sorted(group[items].unique())
    nF, nR, nI, nG = len(free), len(res), len(items), len(groups)

    # variable positions
    o_run, o_lvl = 0, nF * H
    o_short = o_lvl + nR * H
    o_exc = o_short + nI * H
    o_worst = o_exc + nI * H
    n_var = o_worst + nG * H

    def run(i, t): return o_run + i * H + (t - 1)
    def lvl(r, t): return o_lvl + r * H + (t - 1)
    def shrt(s, t): return o_short + s * H + (t - 1)
    def exc(s, t): return o_exc + s * H + (t - 1)
    def wst(g, t): return o_worst + g * H + (t - 1)

    r_pos = pd.Series(range(nR), index=res["resource_id"])
    f_pos = pd.Series(range(nF), index=free)
    carry = res["carry"].to_numpy(float)
    arr = obj.arrivals.to_numpy(float)
    opening = obj.opening.to_numpy(float)

    # ---- equation rows: one per (resource, week) ----
    rows, cols, vals, b_eq = [], [], [], []
    for r in range(nR):
        for t in range(1, H + 1):
            row = r * H + (t - 1)
            rows.append(row); cols.append(lvl(r, t)); vals.append(1.0)
            if t > 1 and carry[r]:
                rows.append(row); cols.append(lvl(r, t - 1)); vals.append(-carry[r])
            b_eq.append(arr[r, t - 1] + (carry[r] * opening[r] if t == 1 else 0.0))
    a = obj.arrows[obj.arrows["task_id"].isin(free)]
    for i_task, rid, amount, delay in a[["task_id", "resource_id", "amount", "delay"]].itertuples(index=False):
        r, i = r_pos[rid], f_pos[i_task]
        for t in range(1, H + 1 - int(delay)):       # a run in week t lands in week t + delay
            rows.append(r * H + (t + int(delay) - 1)); cols.append(run(i, t)); vals.append(-float(amount))
    A_eq = sparse.csr_matrix((vals, (rows, cols)), shape=(nR * H, n_var))

    # ---- net position, target and fairness rows (<= form) ----
    ours = res["location"].map(obj.locations.set_index("location_id")["ours"]).to_numpy(bool)
    sign = np.where((res["kind"] == "inventory") & ours, 1.0, np.where(res["kind"] == "order", -1.0, 0.0))
    members = {s: [r for r in range(nR) if res.at[r, "item"] == s and sign[r] != 0] for s in items}
    rows, cols, vals, b_ub = [], [], [], []
    k = 0
    for si, s in enumerate(items):
        d = float(weekly_demand[s])
        g = groups.index(group[s])
        for t in range(1, H + 1):
            tgt = float(target_units.at[s, t])
            # -net - short <= -tgt
            for r in members[s]:
                rows.append(k); cols.append(lvl(r, t)); vals.append(-sign[r])
            rows.append(k); cols.append(shrt(si, t)); vals.append(-1.0); b_ub.append(-tgt); k += 1
            # net - excess <= tgt
            for r in members[s]:
                rows.append(k); cols.append(lvl(r, t)); vals.append(sign[r])
            rows.append(k); cols.append(exc(si, t)); vals.append(-1.0); b_ub.append(tgt); k += 1
            # short/d - worst <= 0
            rows.append(k); cols.append(shrt(si, t)); vals.append(1.0 / d)
            rows.append(k); cols.append(wst(g, t)); vals.append(-1.0); b_ub.append(0.0); k += 1
    A_ub = sparse.csr_matrix((vals, (rows, cols)), shape=(k, n_var))

    # ---- objective ----
    c = np.zeros(n_var)
    for si, s in enumerate(items):
        d = float(weekly_demand[s])
        for t in range(1, H + 1):
            c[shrt(si, t)] = w_short / d
            c[exc(si, t)] = w_excess / d
    c[o_worst:] = w_worst

    sol = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=(0, None), method="highs")
    if sol.status != 0:
        raise RuntimeError(f"LP not solved: {sol.message}")
    x = sol.x

    weeks = list(range(1, H + 1))
    runs = pd.DataFrame(x[o_run:o_lvl].reshape(nF, H), index=free, columns=weeks)
    levels = pd.DataFrame(x[o_lvl:o_short].reshape(nR, H), index=res["resource_id"], columns=weeks)
    levels.insert(0, 0, opening)
    short = pd.DataFrame(x[o_short:o_exc].reshape(nI, H), index=items, columns=weeks)
    return Plan(runs=runs, levels=levels, short=short, objective=float(sol.fun))
