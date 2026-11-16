"""What the planner says about one plan, and about one plan against another, computed from the plans (ui.view_of) and
nothing else. No Streamlit here: every function is tested against the engine's own numbers (tests/test_planner2.py).

    one plan        plan_reading, kpis, bike_dates, assumptions, monthly_stack, pivot_data
    two plans       kpis (with the change), change_lines, same_plan, pivot_compare, change_weeks
    the supply map  supply, supply_map, map_end (one plan; two are drawn one above the other)"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from redwheel import aux_fns, changes as ch, tunables as tu
from ui import H, LINES, ORDER, SKU, SKUS_BY_LINE, WEEKS

LINE_WORDS = {"road-base": "Road base", "road-carbon": "Road carbon", "mtb-base": "MTB base", "mtb-carbon": "MTB carbon"}
PLAN_WEEKS = list(range(1, H + 1))


def fdate(d) -> str:
    return "never" if d is None else pd.Timestamp(d).strftime("%-d %b %Y")


def minus(text: str) -> str:
    """A signed number with a true minus sign."""
    return text.replace("-", "−")


def weeks_between(a, b) -> int:
    return round((pd.Timestamp(b) - pd.Timestamp(a)).days / 7)


def capacity(V, ln) -> np.ndarray:
    """A line's weekly capacity in this scenario (weeks 1..H): from the scenario's object, which a change may edit."""
    return V["R"]["obj"].arrivals.loc[f"capacity||RENO/{ln}", 1:H].to_numpy(float)


def line_builds(V, ln) -> np.ndarray:
    return V["built"].loc[SKUS_BY_LINE[ln]].sum().to_numpy(float)


# ---------------- one plan ----------------

def held_week(ok_rows: pd.DataFrame):
    """First week from which every row holds to the end (None if one fails in the last week)."""
    fails = ~ok_rows.all(axis=0)
    if fails.iloc[-1]:
        return None
    return int(fails[fails].index.max()) + 1 if fails.any() else 1


def plan_reading(V) -> dict:
    """Per line: how long it runs full from the start, when its SKUs hold target, how much capacity it uses; which
    line sets the date every target is held."""
    R = V["R"]
    out = {}
    for ln in LINES:
        full = (R["X"].loc[f"capacity||RENO/{ln}", 1:H] < 0.5).astype(int)
        streak = int(full.cumprod().sum())
        cap = capacity(V, ln)
        rows = R["at_target"][R["line"].reindex(R["at_target"].index).values == ln]
        held = held_week(rows)
        out[ln] = {"full_to": WEEKS[streak] if streak else None, "no_capacity_weeks": int((cap[:streak] == 0).sum()),
                   "held_from": WEEKS[held] if held else None, "used": float(line_builds(V, ln).sum() / cap.sum()),
                   "below": int((~rows).values.sum())}
    dated = {ln: d["held_from"] for ln, d in out.items() if d["held_from"] is not None}
    limit = max(dated, key=dated.get) if len(dated) == len(LINES) else None
    return {"lines": out, "limit": limit}


def kpis(V, V0=None) -> list:
    """[(label, value, change against V0 or None, tone)]: the deck's four measures. Tone: 'bad' (later, more weeks below
    target, lower fill), 'good', 'same', or 'neutral' (more or fewer bikes built is neither). The fill's change is taken
    between the rounded figures shown, so it reads as their difference."""
    c, c0 = V["card"], (V0["card"] if V0 is not None else None)
    built, below = c["Bikes built"], c["Position-weeks below target"]
    held, fill = c["All targets held from"], round(c["On-time fill rate"] * 100, 1)
    if c0 is None:
        d = [(None, None)] * 4
    else:
        db, dw = built - c0["Bikes built"], below - c0["Position-weeks below target"]
        h0 = c0["All targets held from"]
        dh = None if held is None or h0 is None else weeks_between(h0, held)
        df = round(fill - round(c0["On-time fill rate"] * 100, 1), 1)
        d = [(minus(f"{db:+,}"), "neutral") if db else ("same", "same"),
             (minus(f"{dw:+,}"), "bad" if dw > 0 else "good") if dw else ("same", "same"),
             ("same", "same") if dh == 0 or (held is None and h0 is None) else
             ((minus(f"{dh:+d} wk"), "bad" if dh > 0 else "good") if dh is not None else
              (f"was {fdate(h0)}", "bad" if held is None else "good")),
             (minus(f"{df:+.1f} pt"), "bad" if df < 0 else "good") if df else ("same", "same")]
    return [("Bikes built", f"{built:,}", *d[0]), ("Position-weeks below target", f"{below:,}", *d[1]),
            ("All targets held from", fdate(held), *d[2]), ("On-time fill", f"{fill:.1f}%", *d[3])]


def _per_sku_week(V, ok: pd.DataFrame) -> dict:
    """{sku: first week from which the condition holds at every one of its stock sites, or None}."""
    out = {}
    for s in ORDER:
        rows = ok[ok.index.get_level_values("item") == s]
        out[s] = held_week(rows)
    return out


def bike_dates(V) -> dict:
    """{sku: (orders cleared on, at target on)}: the first week from which no order of the SKU waits, and from which
    it is at target, at every stock site, to the end of the plan."""
    R = V["R"]
    cleared = _per_sku_week(V, R["flows"]["open_orders"][PLAN_WEEKS] < 0.5)
    at = _per_sku_week(V, R["at_target"][PLAN_WEEKS])
    return {s: (WEEKS[cleared[s]] if cleared[s] else None, WEEKS[at[s]] if at[s] else None) for s in ORDER}


# ---------------- two plans ----------------

def change_lines(case0, case, V) -> list:
    """[(change, what, from, to)]: everything `case` sets differently from `case0`, one line each. A change to the data
    reads with the numbers it changed (from the run's own change report); rows that differ only in what they apply to
    are merged ('Build time', 'Road carbon, MTB carbon', '1 week', '2 weeks'); a priority order is one line."""
    d = tu.differences(case0, case)
    cr = tu.change_rows(case.changes, V["R"]["change_report"]) if case.changes else pd.DataFrame()
    by_what = {r["What"]: r for r in cr.to_dict("records")}
    whole = f" · weeks of {fdate(WEEKS[1])} to {fdate(WEEKS[H])}"
    out, merged = [], {}
    for r in d.to_dict("records"):
        if r["Tunable"] == "Priority order":
            if not any(x[0] == "Priority order" for x in out):
                out.append(("Priority order", "", priority_words(case0), priority_words(case)))
            continue
        n = by_what.get(r["What"])
        what = r["What"].replace(whole, "")
        if n is not None and r["To"] != "as in the data":
            out.append((r["Tunable"], what, n["From"], n["To"]))
            continue
        key = (r["Tunable"], r["From"], r["To"])
        if key in merged:
            i_ = merged[key]
            out[i_] = (out[i_][0], out[i_][1] + ", " + what, out[i_][2], out[i_][3])
        else:
            merged[key] = len(out)
            out.append((r["Tunable"], what, r["From"], r["To"]))
    return out


def _same_builds(V, V0, ln) -> bool:
    s = SKUS_BY_LINE[ln]
    return bool(np.array_equal(V["built"].loc[s].to_numpy(), V0["built"].loc[s].to_numpy()))


def same_plan(V, V0) -> bool:
    """The same builds, bike by bike and week by week."""
    return all(_same_builds(V, V0, ln) for ln in LINES)


# ---------------- tables ----------------


def build_csv(V) -> str:
    """The weekly build plan for the whole horizon, one row per bike per week (the deliverable)."""
    return aux_fns.build_plan_table(V["R"]["obj"], V["R"]["builds"]).to_csv(index=False)


def transfer_csv(V):
    """Weekly transfers to the PDC, or None when the plan does not decide transfers."""
    if "move" not in V["case"].decides:
        return None
    tp = V["moved"].stack().rename("units").reset_index()
    tp.columns = ["sku", "t", "units"]
    tp = tp[tp["units"] > 0].assign(week_start=lambda d: d["t"].map(WEEKS), units=lambda d: d["units"].astype(int))
    return tp[["week_start", "sku", "units"]].to_csv(index=False)


# ---------------- the scenario template and the comparison ----------------

FLOOR_WORDS = {"due": "past-due", "owed": "open orders", "target": "target"}
SITE_WORDS = {"RENO": "Reno", "CMH": "PDC"}
CUSTOMER_WORDS = {"WEB": "web", "DEALERS": "dealer", "COMMERCIAL": "commercial"}
MONTH = WEEKS.dt.to_period("M")
MONTHS = list(dict.fromkeys(MONTH))
MONTH_WEEKS = {p: [int(t) for t in WEEKS.index[MONTH == p]] for p in MONTHS}


def _wk(n) -> str:
    return f"{n:g} wk"


def priority_words(case) -> str:
    """'even rule', or the walk's floors in order and any ranked line:
    'past-due > open orders > target; MTB carbon: RW-9304 > RW-4418 > RW-6416'."""
    if not case.walk:
        return "even rule"
    floors = list(dict.fromkeys(FLOOR_WORDS[s.floor] for s in case.walk.steps))
    ranked = []
    for s in case.walk.steps:
        if s.share == "ranked" and "line_id" in s.select:
            lines_ = [s.select["line_id"]] if isinstance(s.select["line_id"], str) else s.select["line_id"]
            ranked.append(f"{', '.join(LINE_WORDS.get(x, x) for x in lines_)}: {' > '.join(s.order)}")
    return " > ".join(floors) + ("; " + "; ".join(ranked) if ranked else "")


STEP_WORDS = {"due": "orders past their date", "owed": "all open orders", "target": "the target"}


def objective_words(case) -> str:
    """The plan's objective in one sentence (docs/SOLVER.md §2, §2a)."""
    if not case.walk:
        return ("Minimise each line's largest shortfall against target, in weeks of supply, summed over the weeks; "
                "then the total shortfall; then stock above target.")
    steps, ranked = [], []
    for s in case.walk.steps:
        if STEP_WORDS[s.floor] not in steps:
            steps.append(STEP_WORDS[s.floor])
        if s.share == "ranked" and "line_id" in s.select:
            lines_ = [s.select["line_id"]] if isinstance(s.select["line_id"], str) else s.select["line_id"]
            ranked.append(f"{', '.join(LINE_WORDS.get(x, x) for x in lines_)} one bike at a time, "
                          f"{', then '.join(s.order)}")
    return ("Minimise the shortfall in steps, each held at its best before the next: " + ", then ".join(steps)
            + (f" ({'; '.join(ranked)})" if ranked else "") + ".")


def constraint_words(V) -> list:
    """The plan's constraints, in short phrases: capacity, build time, where stock serves, what the plan decides."""
    a, case = dict(assumptions(V)), V["case"]
    out = ["line capacity, week by week", f"build lead time {a['Build lead time']}"]
    if len(V["R"]["pools"]) == 1:
        out.append("stock at Reno and the PDC pooled against every order")
    else:
        out.append(f"orders served {a['Sourcing']}; Reno to the PDC {a['Transfer lead time']}")
    out.append("the plan decides builds" + (" and transfers" if "move" in case.decides else ""))
    return out


def targets_words(V) -> str:
    """'Road 8 wk, 10 from 3 Jan 2028 · MTB base 12 wk · MTB carbon 15 wk', from the plan's own targets."""
    R = V["R"]
    out = []
    for name, ln in (("Road", "road-base"), ("MTB base", "mtb-base"), ("MTB carbon", "mtb-carbon")):
        k = next(k for k in R["target_wos"].index if R["line"][k] == ln)
        tw = R["target_wos"].loc[k, 1:H]
        steps = [(int(t), float(v)) for t, v in tw.items() if t == 1 or v != tw[t - 1]]
        out.append(f"{name} {steps[0][1]:g} wk" + "".join(f", {v:g} from {fdate(WEEKS[t])}" for t, v in steps[1:]))
    return " · ".join(out)


def assumptions(V) -> list:
    """[(label, value)]: the settings that shape the plan, in technical shorthand."""
    case, pools = V["case"], V["R"]["pools"]
    if len(pools) == 1:
        sourcing = "pooled (" + " + ".join(SITE_WORDS[x] for x in ("RENO", "CMH")) + ")"
    else:
        sourcing = "; ".join(f"{', '.join(CUSTOMER_WORDS[c] for c in ('WEB', 'DEALERS', 'COMMERCIAL') if c in p['customers'])}"
                             f" ← {' + '.join(SITE_WORDS[x] for x in p['stock'])}"
                             for p in sorted(pools.values(), key=lambda p: "WEB" not in p["customers"]))
    bw = case.build_weeks
    carbon, base = ({bw[ln] for ln in LINES if kind in ln} for kind in ("carbon", "base"))
    if len(set(bw.values())) == 1:
        build = _wk(next(iter(bw.values())))
    elif len(carbon) == 1 and len(base) == 1:
        build = f"carbon lines {_wk(carbon.pop())}, base lines {_wk(base.pop())}"
    else:
        build = ", ".join(f"{LINE_WORDS[ln]} {_wk(bw[ln])}" for ln in LINES)
    return [("Sourcing", sourcing), ("Build lead time", build), ("Transfer lead time", _wk(case.transfer_weeks)),
            ("Decisions", "builds" + (", transfers" if "move" in case.decides else "")),
            ("Priority", priority_words(case)), ("Targets (weeks of supply)", targets_words(V))]


def monthly_stack(V, ln) -> dict:
    """A line by month (a week counts in the month of its Monday): bikes built per bike (totals), forecast demand and
    capacity (totals), and open orders at the month's last week (bikes waiting)."""
    pick = [MONTH_WEEKS[p] for p in MONTHS]
    cap = capacity(V, ln)
    skus = [s for s in ORDER if s in SKUS_BY_LINE[ln]]
    return {"built": {s: [float(V["built"].loc[s, w].sum()) for w in pick] for s in skus},
            "demand": [float(V["demand"].loc[skus, w].values.sum()) for w in pick],
            "capacity": [float(cap[[t - 1 for t in w]].sum()) for w in pick],
            "open_orders": [float(V["open_orders"].loc[skus, max(w)].sum()) for w in pick]}


# ---------------- the build plan table: line → bike → metric, by fiscal year → quarter → month ----------------

METRICS = [   # key, label, kind, on by default, scope ('bike': bike rows and their sums; 'line': line rows only), emphasised
    ("on_hand", "On hand", "level", True, "bike", False),
    ("forecast", "Forecast", "flow", True, "bike", False),
    ("open", "Open orders", "level", True, "bike", False),
    ("build", "Build plan", "flow", True, "bike", True),
    ("capacity", "Capacity", "flow", True, "line", False),
    ("use", "Utilisation", "share", True, "line", False),
    ("net", "Net inventory", "level", True, "bike", True),
    ("target", "Target inventory", "level", True, "bike", False),
    ("wos", "Weeks of supply", "ratio", True, "bike", False),
    ("shipped", "Shipped", "flow", False, "bike", False),
    ("at_target", "At target", "flag", False, "bike", False),
]


def period_tree() -> list:
    """Columns of the build plan table, in order: Start, then each fiscal year (Sep–Aug) with its quarters and each
    quarter with its months, then Total. [{id, label, level ('S', 'Y', 'Q', 'M', 'T'), parent, weeks}]"""
    fy = WEEKS.dt.year - (WEEKS.dt.month < 9)
    q = (WEEKS.dt.month - 9) % 12 // 3 + 1
    out = [{"id": "start", "label": "Start", "level": "S", "parent": None, "weeks": [0]}]
    for y in dict.fromkeys(fy):
        yid = f"FY{y % 100:02d}"
        wy = [int(t) for t in fy.index[fy == y]]
        out.append({"id": yid, "label": yid, "level": "Y", "parent": None, "weeks": wy})
        for qq in dict.fromkeys(q[fy == y]):
            qid = f"{yid} Q{qq}"
            wq = [int(t) for t in fy.index[(fy == y) & (q == qq)]]
            out.append({"id": qid, "label": f"Q{qq}", "level": "Q", "parent": yid, "weeks": wq})
            for p in dict.fromkeys(MONTH[wq]):
                out.append({"id": str(p), "label": p.strftime("%b %y"), "level": "M", "parent": qid,
                            "weeks": MONTH_WEEKS[p]})
    out.append({"id": "total", "label": "Total", "level": "T", "parent": None, "weeks": list(range(1, H + 1))})
    return out


def _bike_series(V, s) -> dict:
    """Weekly series of one bike: flows on weeks 1..H, levels on weeks 0..H (the target from week 1)."""
    R = V["R"]
    keys = [k for k in R["wos"].index if k[0] == s]
    return {"build": V["built"].loc[s], "forecast": V["demand"].loc[s], "shipped": V["shipped"].loc[s],
            "open": V["open_orders"].loc[s], "on_hand": V["on_hand"].loc[s] + V["transit"].loc[s],
            "net": V["net"].loc[s], "target": V["target_units"].loc[s],
            "wos": R["wos"].loc[keys].min(axis=0), "target_wos": R["target_wos"].loc[keys[0]],
            "at_target": V["at_target"].loc[s].astype(float)}


def _cell(kind, series, weeks):
    """One cell: a flow is summed over the period's weeks; a level is read at its last week (None before the plan
    for flows, and where the series has no value)."""
    if kind == "flow":
        return None if weeks == [0] else float(series.reindex(weeks).fillna(0).sum())
    t = max(weeks)
    if t == 0 and 0 not in series.index:                      # the target before week 1: the target of week 1
        t = 1
    return None if t not in series.index else float(series[t])


def pivot_data(V) -> dict:
    """Everything the build plan table shows, computed: columns, metrics, and one row per (line, bike, metric), per
    (line, metric) for the line's subtotal and per metric for all lines. Values are per column id."""
    cols = period_tree()
    level_end = {c["id"]: c["weeks"] for c in cols}
    rows = []

    def values(kind, series):
        return {cid: _cell(kind, series, w) for cid, w in level_end.items()
                if not (kind != "flow" and cid == "total")}

    for ln in LINES:
        skus = [s for s in ORDER if s in SKUS_BY_LINE[ln]]
        series = {s: _bike_series(V, s) for s in skus}
        for s in skus:
            for key, label, kind, _, scope, _ in METRICS:
                if scope != "bike":
                    continue
                if kind in ("ratio", "flag"):
                    vals = values("level", series[s][key])
                    if kind == "ratio":                       # below target at the period's end: shaded
                        bad = {cid: bool(series[s]["at_target"].get(max(w), 1.0) < 0.5) if max(w) >= 1
                               else bool(series[s]["wos"][0] < series[s]["target_wos"][1])
                               for cid, w in level_end.items() if cid != "total"}
                        rows.append({"line": ln, "sku": s, "metric": key, "values": vals, "bad": bad})
                        continue
                else:
                    vals = values(kind, series[s][key])
                rows.append({"line": ln, "sku": s, "metric": key, "values": vals})
        cap = pd.Series(capacity(V, ln), index=range(1, H + 1))
        built = sum(series[s]["build"] for s in skus)
        for key, label, kind, _, scope, _ in METRICS:
            if kind == "ratio":
                continue
            if key == "capacity":
                vals = values("flow", cap)
            elif key == "use":
                c, b = values("flow", cap), values("flow", built)
                vals = {cid: (b[cid] / c[cid] if c.get(cid) else None) for cid in c}
            elif kind == "flag":
                vals = {cid: sum(r["values"][cid] or 0 for r in rows if r["line"] == ln and r["metric"] == key)
                        for cid in level_end if cid != "total"}
            else:
                vals = {cid: sum(r["values"].get(cid) or 0 for r in rows
                                 if r["line"] == ln and r["sku"] and r["metric"] == key)
                        for cid in values(kind, series[skus[0]][key])}
            rows.append({"line": ln, "sku": None, "metric": key, "values": vals, "of": len(skus)})
    for key, label, kind, _, scope, _ in METRICS:
        if kind == "ratio":
            continue
        sub = [r for r in rows if r["sku"] is None and r["metric"] == key]
        if key == "use":
            c = {cid: sum(r["values"].get(cid) or 0 for r in rows if r["sku"] is None and r["metric"] == "capacity")
                 for cid in sub[0]["values"]}
            b = {cid: sum(r["values"].get(cid) or 0 for r in rows if r["sku"] is None and r["metric"] == "build")
                 for cid in sub[0]["values"]}
            vals = {cid: (b[cid] / c[cid] if c[cid] else None) for cid in c}
        else:
            vals = {cid: sum(r["values"].get(cid) or 0 for r in sub) for cid in sub[0]["values"]}
            if kind == "flow":
                vals["start"] = None
        rows.append({"line": None, "sku": None, "metric": key, "values": vals, "of": len(ORDER)})
    for r in rows:                                            # no start value for flows
        if METRIC_KIND[r["metric"]] in ("flow", "share"):
            r["values"]["start"] = None
    return {"columns": [{k: c[k] for k in ("id", "label", "level", "parent")} for c in cols],
            "metrics": [{"key": k, "label": lab, "kind": kind, "on": on, "scope": sc_, "em": em}
                        for k, lab, kind, on, sc_, em in METRICS],
            "lines": [{"id": ln, "label": LINE_WORDS[ln]} for ln in LINES],
            "bikes": {s: {"size": SKU.at[s, "size"]} for s in ORDER},
            "rows": rows}


METRIC_KIND = {k: kind for k, _, kind, *_ in METRICS}


# ---------------- comparing two plans: the phases, the difference table ----------------

COMPARE_ON = {"open", "build", "capacity", "net", "wos"}      # the measures the difference table opens with


def _selected_lines(c, obj) -> set:
    ids, _ = ch.selected(obj, c.select)
    res, tsk = obj.resources.set_index("resource_id"), obj.tasks.set_index("task_id")
    out = set()
    for i in ids:
        item, loc = (res.at[i, "item"], res.at[i, "location"]) if i in res.index else (tsk.at[i, "item"], None)
        if isinstance(item, str) and item in SKU.index:
            out.add(SKU.at[item, "line_id"])
        elif isinstance(loc, str) and loc.split("/")[-1] in LINES:
            out.add(loc.split("/")[-1])
    return out


def pivot_compare(V, V0) -> dict:
    """The build plan table for two plans: the same rows and columns as pivot_data, with three sets of values (V
    minus V0, V0, V) and, per row, whether it differs anywhere."""
    a, b = pivot_data(V0), pivot_data(V)
    key = lambda r: f"{r['line']}|{r['sku']}|{r['metric']}"                               # noqa: E731
    by_a = {key(r): r for r in a["rows"]}
    diff = []
    for r in b["rows"]:
        r0 = by_a[key(r)]
        vals = {cid: (None if v is None and r0["values"].get(cid) is None else (v or 0) - (r0["values"].get(cid) or 0))
                for cid, v in r["values"].items()}
        diff.append({**{k: v for k, v in r.items() if k not in ("values", "bad")}, "values": vals,
                     "changed": any(v is not None and abs(v) > 1e-9 for v in vals.values())})
    metrics = [{**m, "on": m["key"] in COMPARE_ON} for m in b["metrics"]]
    return {**{k: b[k] for k in ("columns", "lines", "bikes")}, "metrics": metrics, "rows": diff,
            "modes": {"diff": diff, "a": a["rows"], "b": b["rows"]},
            "labels": {"diff": f"{V['case'].key} − {V0['case'].key}", "a": V0["case"].key, "b": V["case"].key}}


def change_weeks(V, V0, ln) -> list:
    """(first, last) week of each dated change V has and V0 has not on this line (not one over the whole plan)."""
    theirs = {json.dumps(r, sort_keys=True) for r in ch.to_records(V0["case"].changes)}
    obj = V["R"]["obj"]
    return [(c.from_t, min(c.to_t, H)) for c, r in zip(V["case"].changes, ch.to_records(V["case"].changes))
            if json.dumps(r, sort_keys=True) not in theirs and c.from_t is not None
            and not (c.from_t == 1 and c.to_t >= H) and ln in _selected_lines(c, obj)]


# ---------------- the supply map: every bike, every week, against its target ----------------


def phase_runs(V, skus: list) -> list:
    """[[phase, first week, last week]] over the plan's weeks: 'w' while any of the bikes has an order waiting at the
    week's end, else 'b' while any is below its target, else 'a'."""
    waiting = V["open_orders"].loc[skus, 1:H].sum() > 0.5
    ok = V["at_target"].loc[skus, 1:H].all()
    runs = []
    for t in PLAN_WEEKS:
        x = "w" if waiting[t] else ("a" if ok[t] else "b")
        if runs and runs[-1][0] == x:
            runs[-1][2] = t
        else:
            runs.append([x, t, t])
    return runs


def held_from_runs(runs: list):
    """The week from which the bikes are at target to the end of the plan, or None."""
    return runs[-1][1] if runs[-1][0] == "a" else None


def supply(V, skus: list) -> tuple:
    """(weeks of supply, target), weeks 1..H, of a group of bikes read at its worst: the target less the largest
    shortfall among the bikes (each at its worst stock site). At or above the target: every bike is at target; below
    zero: customers wait. The bikes of a line share their target."""
    R = V["R"]
    gap, tgt = [], []
    for s in skus:
        keys = [k for k in R["wos"].index if k[0] == s]
        w = R["wos"].loc[keys, 1:H].to_numpy(float)
        t = R["target_wos"].loc[keys, 1:H].to_numpy(float)
        gap.append((w - t).min(axis=0))
        tgt.append(t.max(axis=0))
    t = np.max(tgt, axis=0)
    return t + np.min(gap, axis=0), t


WAIT_DEPTH, ABOVE_DEPTH = 20.0, 6.0     # weeks: the darkest red (customers waiting) and darkest green (above target)


def map_end(*views) -> int:
    """The supply map's last week: Jan 2028 (week 70), or 9 weeks after the last bike in these plans is at target;
    the end of the plan when one never is."""
    held = [held_from_runs(phase_runs(V, [s])) for V in views for s in ORDER]
    return H if None in held else int(min(H, max(70, max(held) + 9)))


def supply_map(V, end: int) -> list:
    """The supply map of one plan, weeks 1..end: one row per bike, in line order, with the value the map colours each
    week by (0–1 customers waiting, darker the deeper; 1–2 below target, darker the further; 2–3 at target, darker the
    further above), its weeks of supply and target, and the week it is at target from (or None)."""
    rows = []
    for ln in LINES:
        for s in [s for s in ORDER if s in SKUS_BY_LINE[ln]]:
            w, t = (x[:end] for x in supply(V, [s]))
            z = np.where(w < 0, 0.99 * (1 - np.minimum(-w / WAIT_DEPTH, 1)),
                         np.where(w < t - 1e-6, 1 + 0.99 * np.clip(w / t, 0, 1),
                                  2 + 0.99 * np.minimum((w - t) / ABOVE_DEPTH, 1)))
            rows.append({"line": ln, "sku": s, "label": f"{s} {SKU.at[s, 'size']}", "z": z, "wos": w, "target": t,
                         "held": held_from_runs(phase_runs(V, [s]))})
    return rows
