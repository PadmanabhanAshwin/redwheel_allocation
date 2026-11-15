"""What the Plan view says about one plan, computed from that plan (ui.view_of) and nothing else.

No Streamlit here, so each function is tested against the engine's own numbers (tests/test_planner3.py). Definitions
shared with the other planner (per-line facts, capacity) are imported, not copied, so both UIs say the same thing
about the same plan.

    lines, verdict, kpi_cards      the answer: when every target is held, and what sets that date
    grid                           the planning grid: per line, capacity used each month; per SKU, weeks of supply
                                   at month end against target
    build_table                    Build Plans: bikes to start per SKU, by week or month, against line capacity
    summarized_plan                Summarized Plan: the balance period by period, for all SKUs, a line or a SKU
    sku_table                      Plan by SKU: start, built, forecast, end, target, when at target"""
from __future__ import annotations

import numpy as np
import pandas as pd

from planner2 import charts as p2
from planner2.charts import LINE_WORDS
from redwheel import aux_fns, changes as ch, scenarios as sc
from ui import H, LINES, ORDER, SKU, SKUS_BY_LINE, WEEKS, pool_label
from ui import periods as ui_periods

BELOW_CHECK = "Below target only when the line ran full"
WIP = "Work in progress"
MONTH = WEEKS.dt.to_period("M")
MONTHS = list(dict.fromkeys(MONTH))                       # Sep 2026 .. Dec 2028
MONTH_END = {p: int(MONTH.index[MONTH == p].max()) for p in MONTHS}
MONTH_WEEKS = {p: [int(t) for t in MONTH.index[MONTH == p]] for p in MONTHS}


def fdate(d) -> str:
    return pd.Timestamp(d).strftime("%-d %b %Y")


# ---------------- events ----------------

def has_run_limits(V) -> bool:
    """True if the scenario limits how much a task may run in some weeks (e.g. no frames for a SKU)."""
    return any(c.field == "run_max" for c in V["case"].changes)


def lines_touched(c, obj) -> list:
    """The lines (in plan order) whose capacity, orders, stock or tasks a change selects."""
    ids, _ = ch.selected(obj, c.select)
    res = obj.resources.set_index("resource_id")
    tsk = obj.tasks.set_index("task_id")
    found = set()
    for i in ids:
        item, loc = (res.at[i, "item"], res.at[i, "location"]) if i in res.index else (tsk.at[i, "item"], None)
        if isinstance(item, str) and item in SKU.index:
            found.add(SKU.at[item, "line_id"])
        elif isinstance(loc, str) and loc.split("/")[-1] in LINES:
            found.add(loc.split("/")[-1])
    return [ln for ln in LINES if ln in found]


def event_spans(V, ln) -> list:
    """(first week, last week) of each dated event that touches this line, cut to the plan."""
    obj = V["R"]["obj"]
    return [(c.from_t, min(c.to_t, H)) for c in V["case"].changes
            if c.from_t is not None and c.from_t <= H and ln in lines_touched(c, obj)]


# ---------------- lines: the date, and what sets it ----------------

def full_weeks(V, ln) -> np.ndarray:
    """Weeks 1..H in which the line builds at full capacity: its unused capacity (the capacity resource's level) is
    below half a bike. The same test as the plan check and the per-line facts."""
    return (V["R"]["X"].loc[f"capacity||RENO/{ln}", 1:H] < 0.5).to_numpy()


def lead_weeks(V, ln=None) -> int:
    """The longest time from using a line's capacity to stock that can ship, over the line's (or every) position."""
    R, case = V["R"], V["case"]
    return max(sc.lead_weeks(case, R["pools"][p], line) for (_, p), line in R["line"].items() if ln in (None, line))


def lines(V) -> tuple:
    """({line: facts}, the line that sets the date). Facts: planner2's per-line reading, plus the run of full weeks
    from the start and, if capacity rises the week after that run, the rise (from, to, date)."""
    rd = p2.plan_reading(V)
    out = {}
    for ln in LINES:
        cap = p2.capacity(V, ln)
        streak = int(np.cumprod(full_weeks(V, ln)).sum())
        rise = None
        if 0 < streak < H and cap[streak] > cap[streak - 1]:
            rise = (int(cap[streak - 1]), int(cap[streak]), WEEKS[streak + 1])
        out[ln] = {**rd["lines"][ln], "streak": streak, "rise": rise}
    return out, rd["limit"]


def verdict(V) -> str:
    """When every target is held, and what sets that date. HTML (bold only)."""
    held = V["card"]["All targets held from"]
    facts, limit = lines(V)
    if held is None:
        missing = [LINE_WORDS[ln] for ln, d in facts.items() if d["held_from"] is None]
        return ("Not every SKU holds its weeks-of-supply target by the end of the plan. Not at target by "
                f"{fdate(WEEKS[H])}: <b>{', '.join(missing)}</b>.")
    s = f"Every SKU holds its weeks-of-supply target from <b>{fdate(held)}</b>."
    if limit is None:
        return s
    d = facts[limit]
    if not d["streak"]:
        return s + f" The last line there is <b>{LINE_WORDS[limit]}</b>; it has spare capacity from the first week."
    s += (f" The last line there is <b>{LINE_WORDS[limit]}</b>: it builds at full capacity every week from the start "
          f"to w/c {fdate(WEEKS[d['streak']])}")
    if d["no_capacity_weeks"]:
        s += f", with no capacity at all in {d['no_capacity_weeks']} of those weeks"
    if d["rise"]:
        a, b, when = d["rise"]
        s += f", and its capacity rises from {a:,} to {b:,} a week on {fdate(when)}"
    s += "."
    lead = lead_weeks(V, limit)
    if lead:
        s += (f" A bike built on it takes up to {lead} week{'s' if lead != 1 else ''} to reach stock that can ship "
              "(build and transfer time).")
    return s


def kpi_cards(V) -> list:
    """[(label, value, sub-line, bad)] for the four headline numbers."""
    card, chk = V["card"], V["checks"]
    held, cleared = card["All targets held from"], card["Open orders cleared from"]
    built = card["Bikes built"]
    capacity = sum(float(p2.capacity(V, ln).sum()) for ln in LINES)
    unit = "SKU-site weeks" if V["multi"] else "SKU-weeks"
    below_row = chk[chk["check"].str.startswith(BELOW_CHECK)]
    failed = chk[~chk["pass"]]
    below = card["Position-weeks below target"]
    if not failed.empty:
        sub, bad = f"Fails: {failed['check'].iloc[0]}", True
    elif below_row.empty:
        sub, bad = "", False
    elif below:
        sub, bad = (f"{below:,} {unit} below target, all while the line was full"
                    + (" or the SKU at its run limit" if has_run_limits(V) else "")), False
    else:
        sub, bad = "never below target", False
    backlog0 = float(V["open_orders"][0].sum())
    return [
        ("All targets held from", fdate(held) if held is not None else "never",
         "every SKU" + (" at every stock site" if V["multi"] else "") + ", to the end of the plan", held is None),
        ("Open orders cleared", fdate(cleared) if cleared is not None else "never",
         f"{backlog0:,.0f} open at the start; orders assumed to ship as soon as stock exists", cleared is None),
        ("Bikes built", f"{built:,}", f"{built / capacity:.0%} of capacity over the plan", False),
        ("Plan checks", f"{int(chk['pass'].sum())} of {len(chk)} pass", sub, bad),
    ]


# ---------------- the planning grid ----------------

def positions(V, ln) -> list:
    """The line's stock positions, (sku, pool), in SKU order, Reno before the PDC."""
    R = V["R"]
    keys = [k for k in R["wos"].index if R["line"][k] == ln]
    return sorted(keys, key=lambda k: (ORDER.index(k[0]), k[1] == "CMH"))


def targets_text(V) -> str:
    """'Road 8 weeks (10 from 3 Jan 2028) · MTB base 12 · MTB carbon 15', from the plan's own targets."""
    R = V["R"]
    out = []
    for name, lns in (("Road", ["road-base", "road-carbon"]), ("MTB base", ["mtb-base"]),
                      ("MTB carbon", ["mtb-carbon"])):
        k = positions(V, lns[0])[0]
        tw = R["target_wos"].loc[k, 1:H]
        steps = [(int(t), float(v)) for t, v in tw.items() if t == 1 or v != tw[t - 1]]
        txt = f"{name} {steps[0][1]:g} weeks"
        txt += "".join(f" ({v:g} from {fdate(WEEKS[t])})" for t, v in steps[1:])
        out.append(txt)
    return " · ".join(out)


def grid(V) -> dict:
    """The planning grid, month by month (a week counts in the month of its Monday).

    Per line: bikes built and capacity in the month, the share used, and whether the line was full (built to within
    half a bike of capacity; a month with no capacity at all is 'down').
    Per stock position: weeks of supply at the month's last week, the target then, and the plan's own at-target flag;
    a 'Start' column holds the opening position against week 1's target.
    Returns {"months", "lines": {line: {...}}, "limit"}."""
    R = V["R"]
    facts, limit = lines(V)
    out = {}
    for ln in LINES:
        cap = p2.capacity(V, ln)
        built = V["built"].loc[SKUS_BY_LINE[ln]].sum()
        b = [float(built[MONTH_WEEKS[p]].sum()) for p in MONTHS]
        c = [float(cap[[t - 1 for t in MONTH_WEEKS[p]]].sum()) for p in MONTHS]
        use = [x / y if y else np.nan for x, y in zip(b, c)]
        full = [y > 0 and x >= y - 0.5 for x, y in zip(b, c)]
        rows = []
        for k in positions(V, ln):
            ends = [MONTH_END[p] for p in MONTHS]
            w = [float(R["wos"].at[k, 0])] + [float(R["wos"].at[k, t]) for t in ends]
            tg = [float(R["target_wos"].at[k, 1])] + [float(R["target_wos"].at[k, t]) for t in ends]
            ok = [bool(R["wos"].at[k, 0] >= R["target_wos"].at[k, 1])] + [bool(R["at_target"].at[k, t]) for t in ends]
            net = [float(R["net"].at[k, 0])] + [float(R["net"].at[k, t]) for t in ends]
            mb = [None] + [float(V["built"].loc[k[0], MONTH_WEEKS[p]].sum()) for p in MONTHS]
            rows.append({"sku": k[0], "pool": k[1], "label": k[0] if not V["multi"] else f"{k[0]} · {pool_label(k[1])}",
                         "size": SKU.at[k[0], "size"], "wos": w, "target": tg, "ok": ok, "net": net, "built": mb})
        ev_months = sorted({MONTHS.index(MONTH[t]) for a, b2 in event_spans(V, ln) for t in range(a, b2 + 1)})
        out[ln] = {"built": b, "capacity": c, "use": use, "full": full, "rows": rows,
                   "held": facts[ln]["held_from"], "events": ev_months}
    return {"months": MONTHS, "lines": out, "limit": limit}


# ---------------- Build Plans ----------------

def periods(kind: str) -> list:
    """[(column label, [weeks])]: each of the next 12 weeks, or each month of the plan."""
    if kind == "weeks":
        return [(f"{WEEKS[t]:%-d %b}", [t]) for t in range(1, 13)]
    return [(p.strftime("%b %y"), MONTH_WEEKS[p]) for p in MONTHS]


def _n(x) -> str:
    return "–" if abs(x) < 0.5 else f"{x:,.0f}"


def build_table(V, kind: str = "weeks"):
    """Bikes to start building per SKU per period. Per line: a capacity row, its SKUs, and the line's total. Columns:
    the periods, then (weeks only) the 12 weeks' total, then the whole plan's.
    Returns (table of text, a class per cell, a class per row). Cell classes: 'full' on a total that reaches the
    line's capacity, 'muted' on capacity, 'sub' on SKU names. Row classes: 'cap', 'total'."""
    per = periods(kind)
    cols = [lab for lab, _ in per]
    whole = list(range(1, H + 1))
    shown = kind == "weeks"

    def tail(v_shown, v_whole):
        return ({"12 weeks": v_shown} if shown else {}) | {"Whole plan": v_whole}

    rows, cells, kinds = [], [], []
    for ln in LINES:
        cap = p2.capacity(V, ln)
        built_ln = V["built"].loc[SKUS_BY_LINE[ln]].sum()
        b = [float(built_ln[w].sum()) for _, w in per]
        c = [float(cap[[t - 1 for t in w]].sum()) for _, w in per]
        rows.append({"": f"{LINE_WORDS[ln]} line · capacity", "Size": "", **{k: _n(y) for k, y in zip(cols, c)},
                     **tail(_n(sum(c)), _n(cap.sum()))})
        cells.append(["", ""] + ["muted"] * (len(cols) + shown + 1))
        kinds.append("cap")
        for s in [k for k in ORDER if k in SKUS_BY_LINE[ln]]:
            v = [float(V["built"].loc[s, w].sum()) for _, w in per]
            rows.append({"": s, "Size": SKU.at[s, "size"], **{k: _n(x) for k, x in zip(cols, v)},
                         **tail(_n(sum(v)), _n(V["built"].loc[s, whole].sum()))})
            cells.append(["sub"] + [""] * (len(cols) + shown + 2))
            kinds.append("")
        tot_all = float(built_ln.sum())
        rows.append({"": "Line total", "Size": "", **{k: _n(x) for k, x in zip(cols, b)},
                     **tail(_n(sum(b)), _n(tot_all))})
        cells.append(["sub", ""] + ["full" if y > 0 and x >= y - 0.5 else "" for x, y in zip(b, c)]
                     + (["full" if sum(b) >= sum(c) - 0.5 else ""] if shown else [])
                     + ["full" if tot_all >= cap.sum() - 0.5 else ""])
        kinds.append("total")
    t = pd.DataFrame(rows)
    return t, pd.DataFrame(cells, columns=t.columns), kinds


def build_csv(V) -> str:
    """The weekly build plan for the whole horizon, one row per SKU per week (the deliverable)."""
    return aux_fns.build_plan_table(V["R"]["obj"], V["R"]["builds"]).to_csv(index=False)


def transfer_csv(V):
    """Weekly transfers to the PDC, or None when the plan does not decide transfers."""
    if "move" not in V["case"].decides:
        return None
    tp = V["moved"].stack().rename("units").reset_index()
    tp.columns = ["sku", "t", "units"]
    tp = tp[tp["units"] > 0].assign(week_start=lambda d: d["t"].map(WEEKS), units=lambda d: d["units"].astype(int))
    return tp[["week_start", "sku", "units"]].to_csv(index=False)


# ---------------- Summarized Plan ----------------

def work_in_progress(V, skus: list) -> pd.Series:
    """Bikes started and not yet finished at the end of each week 0..H: runs of the last `build time` weeks. A run in
    week u lands in stock in week u + build time (the make edge's delay); nothing is in build at the snapshot."""
    bw = V["case"].build_weeks
    out = pd.Series(0.0, index=range(0, H + 1))
    for s in skus:
        n = int(bw[SKU.at[s, "line_id"]])
        if n:
            runs = V["built"].loc[s]
            out += pd.Series([float(runs.loc[max(1, t - n + 1):t].sum()) if t else 0.0 for t in out.index],
                             index=out.index)
    return out


def summarized_plan(V, skus: list, gran: str):
    """The balance of the SKUs in scope, period by period (Month, Quarter or Fiscal year; FY = Sep–Aug).
    Totals in the period: forecast demand, builds, capacity. At the period's end: stock on hand, in transit, work in
    progress, open orders, net inventory; how many SKUs are at target. Every period balances: net inventory + work in
    progress at its end = the same at its start + builds − forecast demand.
    Returns (table of text with a 'Measure' column, a class per cell, a class per row)."""
    per = ui_periods(gran)
    labels = list(dict.fromkeys(per))
    weeks_in = {p: [int(t) for t in per.index[per == p]] for p in labels}
    ends = [0] + [max(weeks_in[p]) for p in labels]
    start = "Start · " + fdate(WEEKS[1])
    cols = [start] + labels
    lines_in = sorted({SKU.at[s, "line_id"] for s in skus}, key=LINES.index)
    whole_lines = all(set(SKUS_BY_LINE[ln]) <= set(skus) for ln in lines_in)

    def total(df):
        return [None] + [float(df.loc[skus, weeks_in[p]].values.sum()) for p in labels]

    def at_end(df):
        return [float(df.loc[skus, t].sum()) for t in ends]

    sections = [("Demand", [("Forecast demand", total(V["demand"]))])]
    supply = [("Builds", total(V["built"]))]
    if whole_lines:
        cap = [None] + [float(sum(p2.capacity(V, ln)[[t - 1 for t in weeks_in[p]]].sum() for ln in lines_in))
                        for p in labels]
        supply += [("Capacity", cap),
                   ("Capacity used", [None] + [b / c if c else np.nan for b, c in zip(supply[0][1][1:], cap[1:])])]
    sections.append(("Supply", supply))
    stock = [("On hand", at_end(V["on_hand"]))]
    if "move" in V["case"].decides:
        stock.append(("In transit to the PDC", at_end(V["transit"])))
    if any(V["case"].build_weeks[SKU.at[s, "line_id"]] for s in skus):
        w = work_in_progress(V, skus)
        stock.append((WIP, [float(w[t]) for t in ends]))
    stock += [("Open orders", at_end(V["open_orders"])), ("Net inventory", at_end(V["net"]))]
    sections.append(("Stock at the period's end", stock))
    ok = [V["start_ok"].loc[skus]] + [V["at_target"].loc[skus, t] for t in ends[1:]]
    tgt = [("SKUs at target", [f"{int(o.sum())} of {len(skus)}" for o in ok])]
    if len(skus) == 1:
        R = V["R"]
        keys = [k for k in R["wos"].index if k[0] == skus[0]]
        low = [min(float(R["wos"].at[k, t]) for k in keys) for t in ends]
        tw = [float(R["target_wos"].loc[keys[0], max(t, 1)]) for t in ends]
        tgt = [("Weeks of supply" + (" (lowest site)" if len(keys) > 1 else ""), low), ("Target (weeks)", tw)] + tgt
    sections.append(("At the period's end", tgt))

    def fmt(name, v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return ""
        if isinstance(v, str):
            return v
        if name == "Capacity used":
            return f"{v:.0%}"
        if name.startswith("Weeks of supply") or name.startswith("Target"):
            return f"{v:,.1f}"
        return f"{v:,.0f}".replace("-", "−")

    rows, cells, kinds = [], [], []
    for title, items in sections:
        rows.append([title] + [""] * len(cols))
        cells.append([""] * (len(cols) + 1))
        kinds.append("section")
        for name, vals in items:
            rows.append([name] + [fmt(name, v) for v in vals])
            c = [""]
            for i, v in enumerate(vals):
                bad = (name == "Net inventory" and v is not None and v < -0.5) or \
                      (name == "SKUs at target" and not bool(ok[i].all())) or \
                      (name.startswith("Weeks of supply") and v is not None and not bool(ok[i].all()))
                c.append("below" if bad else "")
            cells.append(c)
            kinds.append("em" if name in ("Builds", "Net inventory") else "")
    t = pd.DataFrame(rows, columns=["Measure"] + cols)
    return t, pd.DataFrame(cells, columns=t.columns), kinds


# ---------------- Plan by SKU ----------------

SKU_COLS = ["", "Size", "Stock", "Open orders", "Net", "Built", "Forecast", "Net ", "Target", "At the start",
            "At target from", "Weeks below"]
SKU_GROUPS = [("", 2), ("At the start, 7 Sep 2026", 3), ("Over the plan", 2), ("At the end", 1),
              ("Weeks of supply", 4)]


def sku_numbers(V, s) -> dict:
    R = V["R"]
    keys = [k for k in R["wos"].index if k[0] == s]
    held = [sc.held_from(R["at_target"].loc[[k]]).iloc[0] for k in keys]
    w = work_in_progress(V, [s])
    return {"stock": float(V["on_hand"].at[s, 0] + V["transit"].at[s, 0]), "open": float(V["open_orders"].at[s, 0]),
            "net0": float(V["net"].at[s, 0]), "built": float(V["built"].loc[s].sum()),
            "forecast": float(V["demand"].loc[s].sum()), "net1": float(V["net"].at[s, H]), "wip1": float(w[H]),
            "targets": list(dict.fromkeys(float(v) for v in R["target_wos"].loc[keys[0], 1:H])),
            "wos0": min(float(R["wos"].at[k, 0]) for k in keys),
            "held": None if any(pd.isna(h) for h in held) else WEEKS[int(max(held))],
            "below": int((~R["at_target"].loc[keys]).values.sum())}


def sku_table(V):
    """One row per SKU, a subtotal per line and a total: stock, open orders and net inventory at the start; bikes
    built and forecast demand over the plan; net inventory at the end (start + built − forecast, less any bikes still
    in build); the target; weeks of supply at the start (lowest site); when it holds target; weeks below target.
    Returns (table of text, a class per cell, a class per row)."""
    facts, limit = lines(V)
    rows, cells, kinds = [], [], []
    allv = {k: 0.0 for k in ("stock", "open", "net0", "built", "forecast", "net1", "below")}

    def money(x):
        return f"{x:,.0f}".replace("-", "−")

    for ln in LINES:
        sub = {k: 0.0 for k in allv}
        for s in [k for k in ORDER if k in SKUS_BY_LINE[ln]]:
            d = sku_numbers(V, s)
            rows.append([s, SKU.at[s, "size"], money(d["stock"]), money(d["open"]), money(d["net0"]),
                         money(d["built"]), money(d["forecast"]), money(d["net1"]),
                         " → ".join(f"{v:g}" for v in d["targets"]), f"{d['wos0']:,.1f}",
                         fdate(d["held"]) if d["held"] is not None else "never", f"{d['below']:,}"])
            cells.append(["sub", "", "", "", "below" if d["net0"] < -0.5 else "", "", "", "", "",
                          "below" if d["wos0"] < d["targets"][0] else "", "", ""])
            kinds.append("")
            for k in sub:
                sub[k] += d[k]
        held = facts[ln]["held_from"]
        rows.append([f"{LINE_WORDS[ln]} line", "", money(sub["stock"]), money(sub["open"]), money(sub["net0"]),
                     money(sub["built"]), money(sub["forecast"]), money(sub["net1"]), "", "",
                     fdate(held) if held is not None else "never", f"{int(sub['below']):,}"])
        cells.append([""] * 10 + (["accent"] if ln == limit else [""]) + [""])
        kinds.append("total")
        for k in allv:
            allv[k] += sub[k]
    held = V["card"]["All targets held from"]
    rows.append(["All SKUs", "", money(allv["stock"]), money(allv["open"]), money(allv["net0"]), money(allv["built"]),
                 money(allv["forecast"]), money(allv["net1"]), "", "", fdate(held) if held is not None else "never",
                 f"{int(allv['below']):,}"])
    cells.append([""] * 12)
    kinds.append("grand")
    t = pd.DataFrame(rows, columns=SKU_COLS)
    return t, pd.DataFrame(cells, columns=t.columns), kinds
