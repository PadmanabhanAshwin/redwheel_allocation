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
    fairness    worst[g,t] >= short[s,t] / weekly_demand[s,t]   for s in g

    minimise    w_worst * sum worst  +  w_short * sum short/weekly_demand  +  w_excess * sum excess/weekly_demand

weekly_demand turns units into weeks. The plans use `window_demand`: target units / target weeks, the average
demand over the weeks the target covers, so weeks short = target weeks x the share of the target missing.
See docs/SOLVER.md.
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


def window_demand(target_units: pd.DataFrame, target_weeks: pd.DataFrame, floor: float = 1.0) -> pd.DataFrame:
    """Average weekly demand over each target window: target units / target weeks. position x t (1..H).

    The divisor that turns units short into weeks short: weeks short = target weeks x the share of the target that
    is missing. It agrees with weeks of supply (rtn.weeks_of_supply) at both ends of the window: a position with
    nothing is N weeks short, one at target is 0. A window with less than `floor` units a week (e.g. demand cut to
    zero) is counted at `floor`, so a shortfall there is never divided by zero and weighs at least as much per unit
    as anywhere else."""
    n = target_weeks.loc[target_units.index, target_units.columns].astype(float)
    return (target_units / n.where(n > 0)).fillna(0.0).clip(lower=floor)


def _per_week(weekly_demand: pd.Series | pd.DataFrame, index: pd.Index, weeks: list) -> pd.DataFrame:
    """The divisor as position x week; a Series (one number per position) is the same every week. Must be > 0."""
    if isinstance(weekly_demand, pd.Series):
        d = weekly_demand.loc[index].to_numpy(float)
        out = pd.DataFrame(np.repeat(d[:, None], len(weeks), axis=1), index=index, columns=weeks)
    else:
        out = weekly_demand.loc[index, weeks].astype(float)
    if not (out.to_numpy() > 0).all():
        raise ValueError("weekly demand must be above zero for every position and week (see window_demand)")
    return out


def objective_value(obj: rtn.RTN, runs: pd.DataFrame, target_units: pd.DataFrame,
                    weekly_demand: pd.Series | pd.DataFrame, group: pd.Series, w_worst: float = 1.0,
                    w_short: float = 0.1, w_excess: float = 0.001) -> float:
    """Score any plan on the LP's own objective: run it through the object, then
    w_worst * sum over groups and weeks of the largest shortfall (in weeks) in the group
    + w_short * total shortfall in weeks + w_excess * total stock above target in weeks."""
    items = list(target_units.index)
    net = rtn.net_position(obj, rtn.levels(obj, runs)).loc[items, target_units.columns]
    d = _per_week(weekly_demand, target_units.index, list(target_units.columns))
    short = (target_units - net).clip(lower=0) / d
    excess = (net - target_units).clip(lower=0) / d
    worst = short.groupby(group[items]).max()
    return float(w_worst * worst.values.sum() + w_short * short.values.sum() + w_excess * excess.values.sum())


def lowest_cover_first(obj: rtn.RTN, free: list[str], target_units: pd.DataFrame,
                       weekly_demand: pd.Series | pd.DataFrame) -> pd.DataFrame:
    """The planner's rule (run-out-time priority), for comparison with the LP.

    Week by week, with no look-ahead: on each line, rank its SKUs by cover against target after this week's
    demand, in weeks ((net - target) / weekly demand, lowest first), and build each up to its target in that
    order until the line's capacity is used. Whole bikes. Needs make tasks with no build delay."""
    a = obj.arrows[obj.arrows["task_id"].isin(free)]
    if (a["delay"] != 0).any():
        raise ValueError("lowest_cover_first assumes builds land in the week they are made")
    cap_of = a[a["resource_id"].str.startswith("capacity|")].set_index("task_id")["resource_id"]
    item_of = obj.tasks.set_index("task_id")["item"]
    res = obj.resources.set_index("resource_id")
    orders = res.index[res["kind"] == "order"]
    demand = obj.arrivals.loc[orders].groupby(res.loc[orders, "item"]).sum()       # item x t
    net = rtn.net_position(obj, rtn.levels(obj))[0].astype(float).copy()          # opening net position
    runs = pd.DataFrame(0, index=free, columns=target_units.columns, dtype=int)
    d = _per_week(weekly_demand, target_units.index, list(target_units.columns))
    for t in target_units.columns:
        net = net - demand[t]                                                      # this week's demand first
        for cap_id, tasks in cap_of.groupby(cap_of).groups.items():
            left = int(round(obj.arrivals.at[cap_id, t]))
            cover = {k: (net[item_of[k]] - target_units.at[item_of[k], t]) / d.at[item_of[k], t] for k in tasks}
            for k in sorted(tasks, key=lambda k: cover[k]):
                need = int(np.ceil(max(0.0, target_units.at[item_of[k], t] - net[item_of[k]]) - 1e-9))
                b = min(need, left)
                runs.at[k, t] = b
                net[item_of[k]] += b
                left -= b
    return runs


def round_runs(obj: rtn.RTN, runs: pd.DataFrame) -> pd.DataFrame:
    """Whole-number runs for tasks that draw one unit of a capacity resource per run.

    Per task, cumulative runs are rounded up, so a rounded plan is never behind the LP. A task's run
    limit caps its week (the LP keeps to the limit, so this binds only when rounding up would pass
    it). Where the rest would exceed a capacity in some week, the excess is taken back one unit at a
    time from the tasks rounded up the most. Weeks are processed in order, so cumulative runs stay
    within one unit of the LP: ahead by less than 1, or (only in a week the capacity is used up or
    the task is at its limit) behind by less than 1."""
    a = obj.arrows[obj.arrows["task_id"].isin(runs.index)]
    cap_arrows = a[a["resource_id"].str.startswith("capacity|")]
    if not (cap_arrows["amount"] == -1).all() or cap_arrows["task_id"].duplicated().any():
        raise ValueError("round_runs needs every task to use exactly one unit of one capacity")
    if set(cap_arrows["task_id"]) != set(runs.index):
        raise ValueError("every task to round must draw on a capacity resource")

    lp_cum = runs.cumsum(axis=1)
    limit = rtn.run_limits(obj).reindex(index=runs.index, columns=runs.columns)
    out = pd.DataFrame(0, index=runs.index, columns=runs.columns, dtype=int)
    for cap_id, tasks in cap_arrows.groupby("resource_id")["task_id"]:
        tasks = list(tasks)
        done = pd.Series(0, index=tasks)                  # whole runs so far
        for t in runs.columns:
            k = int(round(obj.arrivals.at[cap_id, t]))
            want = np.ceil(lp_cum.loc[tasks, t] - 1e-9).astype(int)    # cumulative, rounded up
            build = (want - done).clip(lower=0)
            cap_t = np.floor(limit.loc[tasks, t].to_numpy(float) + 1e-9)       # a run limit, where there is one
            build = pd.Series(np.where(np.isnan(cap_t), build, np.minimum(build, cap_t)).astype(int), index=build.index)
            for _ in range(int(build.sum()) - k):          # take back one unit at a time
                ahead = (done + build - lp_cum.loc[tasks, t])[build > 0]
                build[ahead.idxmax()] -= 1
            out.loc[tasks, t] = build.to_numpy()
            done += build
    return out


def forward_sum(demand: pd.DataFrame, n: pd.DataFrame) -> pd.DataFrame:
    """Units of demand in the n[s,t] weeks after week t: weeks t+1 .. t+k in full, k = floor(n), then the fraction
    n - k of week t+k+1. demand: item x t (1..T); n: item x t (1..H), weeks >= 0, need not be whole.
    The same reading as rtn.weeks_of_supply, so weeks of supply >= n exactly when net >= forward_sum."""
    T = int(max(demand.columns))
    cum = demand.cumsum(axis=1)
    cum.insert(0, 0, 0.0)
    out = pd.DataFrame(index=n.index, columns=n.columns, dtype=float)
    for s in n.index:
        for t in n.columns:
            v = float(n.at[s, t])
            k = int(np.floor(v + 1e-9))
            frac = v - k
            if t + k + (frac > 1e-9) > T:
                raise ValueError(f"target of {v:g} weeks for {s} in week {t} reads demand to week {t + k + (frac > 1e-9)}, "
                                 f"but demand is known only to week {T}")
            out.at[s, t] = cum.at[s, t + k] - cum.at[s, t] + (frac * demand.at[s, t + k + 1] if frac > 1e-9 else 0.0)
    return out


def decide(obj: rtn.RTN, free: list[str], target_units: pd.DataFrame, weekly_demand: pd.Series | pd.DataFrame,
           group: pd.Series, w_worst: float = 1.0, w_short: float = 0.1, w_excess: float = 0.001,
           positions: dict | None = None, w_run: float = 0.0) -> Plan:
    """free: task ids the LP may run. target_units: position x t (1..H). group: position -> fairness group.
    weekly_demand: position x t (1..H), the units a week that turn units short into weeks short (`window_demand`);
    a Series is one number per position, the same every week.

    A position is what a target is set on. By default there is one per item: all our inventory of the item
    minus all its orders. `positions` replaces that with {key: {resource_id: sign}}, e.g. one per (item, pool);
    target_units, weekly_demand and group are then indexed by those keys.

    w_run: a small cost per task run. Needed when some stock is outside every position (e.g. a site that may
    not ship): without it, building or moving stock there is free and the LP may do it for no reason."""
    H = len(obj.weeks)
    res = obj.resources.reset_index(drop=True)
    items = list(target_units.index)
    dv = _per_week(weekly_demand, target_units.index, list(range(1, H + 1))).to_numpy()    # dv[s, t-1]
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
    if positions is None:
        members = {s: [(r, sign[r]) for r in range(nR) if res.at[r, "item"] == s and sign[r] != 0] for s in items}
    else:
        members = {s: [(int(r_pos[rid]), float(sg)) for rid, sg in positions[s].items()] for s in items}
    rows, cols, vals, b_ub = [], [], [], []
    k = 0
    for si, s in enumerate(items):
        g = groups.index(group[s])
        for t in range(1, H + 1):
            tgt = float(target_units.at[s, t])
            # -net - short <= -tgt
            for r, sg in members[s]:
                rows.append(k); cols.append(lvl(r, t)); vals.append(-sg)
            rows.append(k); cols.append(shrt(si, t)); vals.append(-1.0); b_ub.append(-tgt); k += 1
            # net - excess <= tgt
            for r, sg in members[s]:
                rows.append(k); cols.append(lvl(r, t)); vals.append(sg)
            rows.append(k); cols.append(exc(si, t)); vals.append(-1.0); b_ub.append(tgt); k += 1
            # short/d - worst <= 0
            rows.append(k); cols.append(shrt(si, t)); vals.append(1.0 / dv[si, t - 1])
            rows.append(k); cols.append(wst(g, t)); vals.append(-1.0); b_ub.append(0.0); k += 1
    A_ub = sparse.csr_matrix((vals, (rows, cols)), shape=(k, n_var))

    # ---- objective ----
    c = np.zeros(n_var)
    for si in range(nI):
        for t in range(1, H + 1):
            c[shrt(si, t)] = w_short / dv[si, t - 1]
            c[exc(si, t)] = w_excess / dv[si, t - 1]
    c[o_worst:] = w_worst
    c[o_run:o_lvl] = w_run

    # ---- bounds: every variable >= 0; a run at most its task's limit that week ----
    upper = np.full(n_var, np.inf)
    lim = rtn.run_limits(obj).reindex(index=free, columns=list(range(1, H + 1))).to_numpy(float)
    upper[o_run:o_lvl] = np.where(np.isnan(lim), np.inf, lim).ravel()      # run(i, t) = o_run + i*H + t-1
    bounds = np.column_stack([np.zeros(n_var), upper])

    sol = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if sol.status != 0:
        raise RuntimeError(f"LP not solved: {sol.message}")
    x = sol.x

    weeks = list(range(1, H + 1))
    runs = pd.DataFrame(x[o_run:o_lvl].reshape(nF, H), index=free, columns=weeks)
    levels = pd.DataFrame(x[o_lvl:o_short].reshape(nR, H), index=res["resource_id"], columns=weeks)
    levels.insert(0, 0, opening)
    short = pd.DataFrame(x[o_short:o_exc].reshape(nI, H), index=items, columns=weeks)
    return Plan(runs=runs, levels=levels, short=short, objective=float(sol.fun))
