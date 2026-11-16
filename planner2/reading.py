"""What the planner says about one plan, and about one plan against another, computed from the plans (ui.view_of) and
nothing else. No Streamlit here: every function is tested against the engine's own numbers (tests/test_planner2.py).

    one plan        plan_reading, kpis, bike_dates, assumptions, monthly_stack, pivot_data
    two plans       summary, assumptions_table, headline, what_changed, grouped_changes, same_plan, lines_changed,
                    monthly_difference, pivot_compare, built_by_period, period_labels, ahead_behind, change_weeks"""
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
    """[(label, value, change against V0 or None, tone, help)]. Tone: 'bad' (a date later, fill lower), 'good'
    (earlier, higher), 'same', or 'neutral' (more or fewer bikes built is neither)."""
    c, c0 = V["card"], (V0["card"] if V0 is not None else None)
    k0 = V0["case"].key if V0 is not None else ""

    def date_delta(k):
        if c0 is None:
            return None, None
        if c[k] is None or c0[k] is None:
            return (f"same as {k0}", "same") if c[k] == c0[k] else (f"{k0}: {fdate(c0[k])}",
                                                                    "bad" if c[k] is None else "good")
        w = weeks_between(c0[k], c[k])
        return (f"{w:+d} wk vs {k0}", "bad" if w > 0 else "good") if w else (f"same as {k0}", "same")

    chk = V["checks"]
    cap = sum(capacity(V, ln).sum() for ln in LINES)
    built, fill = c["Bikes built"], c["On-time fill rate"]
    bd = fd = (None, None)
    if c0 is not None:
        bb, ff = built - c0["Bikes built"], fill - c0["On-time fill rate"]
        bd = (f"{bb:+,} vs {k0}", "neutral") if bb else (f"same as {k0}", "same")
        fd = (f"{ff * 100:+.1f} pts vs {k0}", "bad" if ff < 0 else "good") if abs(ff) >= 5e-4 else \
            (f"same as {k0}", "same")
    return [
        ("Targets held from", fdate(c["All targets held from"]), *date_delta("All targets held from"),
         "First week from which every bike is at its weeks-of-supply target, to the end of the plan"),
        ("Orders cleared", fdate(c["Open orders cleared from"]), *date_delta("Open orders cleared from"),
         "First week from which no order is waiting (orders ship as soon as stock exists, an assumption)"),
        ("Bikes built", f"{built:,}", *bd, f"{built / cap:.0%} of the four lines' capacity"),
        ("On-time fill", f"{fill:.1%}", *fd, "Forecast demand shipped in the week it arrives"),
        ("Plan checks", f"{int(chk['pass'].sum())} of {len(chk)}", None, None, "Computed on every plan"),
    ]


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

def what_changed(case0, case, V) -> pd.DataFrame:
    """Change | What | From | To | Numbers: everything `case` sets differently from `case0`. A change to the data is
    shown with the numbers it changed (from the run's own change report), a setting or priority order in words."""
    d = tu.differences(case0, case)
    cr = tu.change_rows(case.changes, V["R"]["change_report"]) if case.changes else pd.DataFrame()
    by_what = {r["What"]: r for r in cr.to_dict("records")}
    rows = []
    for r in d.to_dict("records"):
        n = by_what.get(r["What"])
        if n is not None and r["To"] != "as in the data":           # a change added: its numbers
            rows.append({"Change": r["Tunable"], "What": r["What"], "From": n["From"], "To": n["To"],
                         "Numbers": f"{int(n['Numbers changed']):,}"})
        else:
            rows.append({"Change": r["Tunable"], "What": r["What"], "From": r["From"], "To": r["To"], "Numbers": ""})
    return pd.DataFrame(rows, columns=["Change", "What", "From", "To", "Numbers"])


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


def sources(obj) -> pd.DataFrame:
    """Where each number in the object comes from: the file, the part of the model, and the total, computed from the
    object itself."""
    res = obj.resources.set_index("resource_id")
    op = obj.opening

    def opening(kind, locs):
        ids = res.index[(res["kind"] == kind) & res["location"].isin(locs)]
        return float(op.reindex(ids).fillna(0).sum())

    def arriving(kind):
        ids = res.index[res["kind"] == kind]
        return float(obj.arrivals.loc[ids, 1:H].values.sum())

    by = {loc: opening("order", [loc]) for loc in ("WEB", "DEALERS", "COMMERCIAL")}
    return pd.DataFrame([
        ("plant_inventory_snapshot.csv", "Stock at Reno and the PDC", "opening level of inventory",
         f"{opening('inventory', ['RENO', 'CMH']):,.0f} bikes"),
        ("dtc_web_orders, dealer_orders_export, Commercial_PO_Log", "Open orders at the snapshot",
         "opening level of orders, and the date each is due",
         f"{sum(by.values()):,.0f} bikes (web {by['WEB']:,.0f} · dealers {by['DEALERS']:,.0f} · commercial "
         f"{by['COMMERCIAL']:,.0f})"),
        ("forecast_dtc, forecast_dealer, forecast_commercial", "Forecast, each week", "arrivals onto orders",
         f"{arriving('order'):,.0f} bikes over the plan"),
        ("capacity_plan.csv", "Line capacity, each week", "arrivals onto the four lines",
         f"{arriving('capacity'):,.0f} bikes over the plan"),
        ("dealer_stock_report.csv", "Dealer stock (theirs, not counted)", "opening level, no edges",
         f"{opening('inventory', ['DEALERS']):,.0f} bikes"),
        ("assumed", "Lines at Reno · Reno → PDC 1 week · either site serves any channel · an order with no date is "
                    "due 7 days after it was placed", "edges, their delays, the routes", ""),
    ], columns=["From", "What", "In the model", "Total"])


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


def targets_words(V) -> str:
    """'Road 8 → 10 wk (3 Jan 2028) · MTB base 12 wk · MTB carbon 15 wk', from the plan's own targets."""
    R = V["R"]
    out = []
    for name, ln in (("Road", "road-base"), ("MTB base", "mtb-base"), ("MTB carbon", "mtb-carbon")):
        k = next(k for k in R["target_wos"].index if R["line"][k] == ln)
        tw = R["target_wos"].loc[k, 1:H]
        steps = [(int(t), float(v)) for t, v in tw.items() if t == 1 or v != tw[t - 1]]
        out.append(f"{name} {' → '.join(f'{v:g}' for _, v in steps)} wk"
                   + "".join(f" ({fdate(WEEKS[t])})" for t, _ in steps[1:]))
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
    build = _wk(next(iter(bw.values()))) if len(set(bw.values())) == 1 else \
        ", ".join(f"{LINE_WORDS[ln]} {_wk(bw[ln])}" for ln in LINES)
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


def grouped_changes(wc: pd.DataFrame) -> list:
    """what_changed rows, with rows that differ only in what they apply to merged: 'Build time · Road base, Road
    carbon, MTB base, MTB carbon: same week → 1 week'."""
    out = {}
    for r in wc.to_dict("records"):
        if r["Numbers"]:
            out[len(out)] = dict(r)
            continue
        key = (r["Change"], r["From"], r["To"])
        if key in out:
            out[key]["What"] += ", " + r["What"]
        else:
            out[key] = dict(r)
    return list(out.values())


def summary(views: dict) -> pd.DataFrame:
    """Measures × scenarios (in the order given; the first is the reference). Dates and numbers carry their change
    against the first."""
    keys = list(views)
    V0 = views[keys[0]]
    rows = {}
    for k, V in views.items():
        col = {}
        for label, value, delta, tone, _ in kpis(V, V0 if k != keys[0] else None):
            col[label] = value + (f" ({delta.split(' vs ')[0]})" if delta and tone != "same" else "")
        held, held0 = plan_reading(V)["lines"], plan_reading(V0)["lines"]
        for ln in LINES:
            a, b = held0[ln]["held_from"], held[ln]["held_from"]
            w = weeks_between(a, b) if a is not None and b is not None else 0
            col[f"At target · {LINE_WORDS[ln]}"] = fdate(b) + (f" ({w:+d} wk)" if k != keys[0] and w else "")
        rows[k] = col
    return pd.DataFrame(rows)


def assumptions_table(views: dict) -> pd.DataFrame:
    return pd.DataFrame({k: dict(assumptions(V)) for k, V in views.items()})


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


# ---------------- comparing two plans: the headline, the difference chart, the difference table ----------------

COMPARE_ON = {"open", "build", "capacity", "net", "wos"}      # the measures the difference table opens with


def headline(V, V0) -> list:
    """[(label, value in V, change against V0, tone)] for the four plan measures."""
    return [(label, value, delta, tone) for label, value, delta, tone, _ in kpis(V, V0) if label != "Plan checks"]


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


def monthly_difference(V, V0, ln) -> dict:
    """The line by month, V minus V0: bikes built per bike, forecast, capacity, open orders at month end."""
    d, d0 = monthly_stack(V, ln), monthly_stack(V0, ln)
    sub = lambda a, b: [x - y for x, y in zip(a, b)]                                       # noqa: E731
    return {"built": {s: sub(d["built"][s], d0["built"][s]) for s in d["built"]}, "demand": sub(d["demand"], d0["demand"]),
            "capacity": sub(d["capacity"], d0["capacity"]), "open_orders": sub(d["open_orders"], d0["open_orders"])}


def lines_changed(V, V0) -> list:
    """Lines whose month figures (builds per bike, forecast, capacity, open orders) or at-target date differ."""
    held, held0 = plan_reading(V)["lines"], plan_reading(V0)["lines"]
    out = []
    for ln in LINES:
        d = monthly_difference(V, V0, ln)
        moved = any(any(abs(v) > 0.5 for v in vals) for vals in [*d["built"].values(), d["demand"], d["capacity"],
                                                                     d["open_orders"]])
        if moved or held[ln]["held_from"] != held0[ln]["held_from"]:
            out.append(ln)
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


def compare_periods(level: str) -> list:
    """[(label, [weeks])] for the side-by-side chart: fiscal quarters ('FY26 Q1') or months ('Sep 26')."""
    if level == "Quarter":
        fq = (WEEKS.dt.year - (WEEKS.dt.month < 9)).map(lambda y: f"FY{y % 100:02d}") + " Q" + \
             ((WEEKS.dt.month - 9) % 12 // 3 + 1).astype(str)
        return [(q, [int(t) for t in fq.index[fq == q]]) for q in dict.fromkeys(fq)]
    return [(p.strftime("%b %y"), MONTH_WEEKS[p]) for p in MONTHS]


def built_by_period(V, ln, level: str) -> dict:
    """{bike: [bikes built per period]} for a line."""
    per = compare_periods(level)
    return {s: [float(V["built"].loc[s, w].sum()) for _, w in per] for s in ORDER if s in SKUS_BY_LINE[ln]}


LABEL_MIN, LABEL_SHARE = 50, 0.02          # a period's difference is labelled at 50 bikes and 2% of the busiest period


def period_labels(V, V0, ln, level: str) -> list:
    """[(period, difference, top)] where the line's builds differ materially between the two plans (at least LABEL_MIN
    bikes and LABEL_SHARE of the reference's busiest period); top is the taller of the two bars."""
    per = [lab for lab, _ in compare_periods(level)]
    a = np.sum(list(built_by_period(V0, ln, level).values()), axis=0)
    b = np.sum(list(built_by_period(V, ln, level).values()), axis=0)
    cut = max(LABEL_MIN, LABEL_SHARE * float(a.max()))
    return [(p, float(y - x), float(max(x, y))) for p, x, y in zip(per, a, b) if abs(y - x) >= cut]


def ahead_behind(V, V0, ln) -> dict:
    """Cumulative bikes built, V minus V0, week by week: per bike and for the line (weeks 1..H)."""
    out = {s: (V["built"].loc[s] - V0["built"].loc[s]).cumsum().to_numpy(float) for s in ORDER if s in SKUS_BY_LINE[ln]}
    out["line"] = sum(out.values())
    return out


def change_weeks(V, V0, ln) -> list:
    """(first, last) week of each dated change V has and V0 has not on this line (not one over the whole plan)."""
    theirs = {json.dumps(r, sort_keys=True) for r in ch.to_records(V0["case"].changes)}
    obj = V["R"]["obj"]
    return [(c.from_t, min(c.to_t, H)) for c, r in zip(V["case"].changes, ch.to_records(V["case"].changes))
            if json.dumps(r, sort_keys=True) not in theirs and c.from_t is not None
            and not (c.from_t == 1 and c.to_t >= H) and ln in _selected_lines(c, obj)]
