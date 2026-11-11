"""Planning priors: every setting a scenario runs under, as one table.

A scenario is a name plus this table; `scenarios.run_case` reads nothing else. One row per setting:

    prior            applies_to        value      from_date
    route            RENO>WEB          yes                     orders of this customer may ship from this site
    build_weeks      mtb-carbon        1                       line capacity used -> bike in Reno stock
    transfer_weeks   RENO>CMH          1                       Reno -> PDC
    target_weeks     road              10         2028-01-03   weeks-of-supply target from that date
    decides          move              yes                     the plan decides this task kind

The table is checked against the network before a run (`validate`): a person or an LLM can change values, but
only to settings the network can carry out.
"""
from __future__ import annotations

import networkx as nx
import pandas as pd

from redwheel import rtn
from redwheel.config import LINES, PLAN_START, POLICY

COLUMNS = ["prior", "applies_to", "value", "from_date"]
MEANING = {
    "route": ("Orders of this customer may ship from this site", "planning prior"),
    "build_weeks": ("Weeks from using line capacity to a bike in Reno stock", "lead time"),
    "transfer_weeks": ("Weeks from Reno to the PDC", "lead time"),
    "target_weeks": ("Weeks-of-supply target for a target group, from a date", "brief"),
    "decides": ("The plan decides this task kind", "model"),
}
MAX_WEEKS = 12                                  # sanity bound on lead times
YES_NO = {"yes": True, "no": False}


def table(routes, build_weeks: int | dict, transfer_weeks: int, decides, lines, targets=POLICY) -> pd.DataFrame:
    """Build a priors table. routes: allowed (site, customer) pairs, out of all six. build_weeks: one value for
    every line, or {line: weeks}. decides: task kinds the plan decides. targets: (group, from, weeks) rows."""
    sites, customers = ("RENO", "CMH"), ("WEB", "DEALERS", "COMMERCIAL")
    bw = build_weeks if isinstance(build_weeks, dict) else {ln: build_weeks for ln in lines}
    rows = [("route", f"{s}>{c}", "yes" if (s, c) in set(routes) else "no", "") for s in sites for c in customers]
    rows += [("build_weeks", ln, int(bw[ln]), "") for ln in lines]
    rows += [("transfer_weeks", "RENO>CMH", int(transfer_weeks), "")]
    rows += [("target_weeks", g, w, d) for g, d, w in targets]
    rows += [("decides", k, "yes" if k in decides else "no", "") for k in ("make", "move")]
    return normalise(pd.DataFrame(rows, columns=COLUMNS))


def describe(t: pd.DataFrame) -> pd.DataFrame:
    """The table with what each row means and what kind of setting it is, for people."""
    return t.assign(meaning=t["prior"].map(lambda p: MEANING[p][0]), kind=t["prior"].map(lambda p: MEANING[p][1]))


def _rows(t, prior):
    return t[t["prior"] == prior]


def settings(t: pd.DataFrame) -> dict:
    """What the run needs, read from the table (assumed valid)."""
    r = _rows(t, "route")
    pol = _rows(t, "target_weeks")
    return {
        "ship_routes": tuple(tuple(a.split(">")) for a, v in zip(r["applies_to"], r["value"]) if v == "yes"),
        "build_weeks": {ln: int(float(v)) for ln, v in zip(_rows(t, "build_weeks")["applies_to"],
                                                            _rows(t, "build_weeks")["value"])},
        "transfer_weeks": int(float(_rows(t, "transfer_weeks")["value"].iloc[0])),
        "decides": tuple(k for k, v in zip(_rows(t, "decides")["applies_to"], _rows(t, "decides")["value"]) if v == "yes"),
        "dim_policy": pd.DataFrame({"target_group": pol["applies_to"].values,
                                    "effective_from": pd.to_datetime(pol["from_date"].values),
                                    "target_wos": pol["value"].astype(float).values}),
    }


def _int_in_range(v) -> bool:
    try:
        return float(v) == int(float(v)) and 0 <= int(float(v)) <= MAX_WEEKS
    except (TypeError, ValueError):
        return False


def validate(t: pd.DataFrame, obj: rtn.RTN) -> list[str]:
    """Every reason this table cannot run on this network; empty when it can."""
    errs = []
    if list(t.columns[:4]) != COLUMNS:
        return [f"columns must start with {COLUMNS}"]
    unknown = sorted(set(t["prior"]) - set(MEANING))
    if unknown:
        errs.append(f"unknown prior(s): {unknown}")
    dup = t[t.duplicated(["prior", "applies_to", "from_date"], keep=False)]
    if len(dup):
        errs.append(f"duplicate rows: {sorted(set(dup['prior'] + ' ' + dup['applies_to']))}")

    # routes: exactly the ship routes the network has, each yes/no; every customer served
    fulfil = obj.tasks[obj.tasks["kind"] == "fulfil"]["task_id"].str.split("|").str[2]
    net_routes = set(fulfil)
    r = _rows(t, "route")
    if set(r["applies_to"]) != net_routes:
        errs.append(f"route rows must be exactly the network's ship routes {sorted(net_routes)}")
    bad = r[~r["value"].isin(YES_NO)]
    if len(bad):
        errs.append(f"route values must be yes/no: {list(bad['applies_to'])}")
    allowed = [a.split(">") for a, v in zip(r["applies_to"], r["value"]) if v == "yes"]
    customers = {a.split(">")[1] for a in net_routes}
    unserved = sorted(customers - {c for _, c in allowed})
    if unserved:
        errs.append(f"no route serves {unserved}")

    # lead times
    lines = set(obj.resources.loc[obj.resources["kind"] == "capacity", "location"].str.split("/").str[1])
    b = _rows(t, "build_weeks")
    if set(b["applies_to"]) != lines:
        errs.append(f"build_weeks needs one row per line {sorted(lines)}")
    if not all(_int_in_range(v) for v in b["value"]):
        errs.append(f"build_weeks must be whole weeks, 0 to {MAX_WEEKS}")
    tr = _rows(t, "transfer_weeks")
    moves = set(obj.tasks.loc[obj.tasks["kind"] == "move", "task_id"].str.split("|").str[2])
    if set(tr["applies_to"]) != moves or len(tr) != len(moves):
        errs.append(f"transfer_weeks needs one row per transfer route {sorted(moves)}")
    if not all(_int_in_range(v) for v in tr["value"]):
        errs.append(f"transfer_weeks must be whole weeks, 0 to {MAX_WEEKS}")

    # targets: every group covered from the plan start, positive weeks, readable dates
    p = _rows(t, "target_weeks")
    dates = pd.to_datetime(p["from_date"], errors="coerce")
    if dates.isna().any():
        errs.append("target_weeks rows need a from_date (YYYY-MM-DD)")
    weeks = pd.to_numeric(p["value"], errors="coerce")
    if weeks.isna().any() or (weeks <= 0).any() or (weeks > 52).any():
        errs.append("target_weeks values must be more than 0 and at most 52")
    groups = set(obj.items["target_group"])
    covered = set(p.loc[dates <= PLAN_START, "applies_to"])
    if groups - covered:
        errs.append(f"no target from the plan start for {sorted(groups - covered)}")
    if set(p["applies_to"]) - groups:
        errs.append(f"unknown target group(s) {sorted(set(p['applies_to']) - groups)}")

    # what the plan decides
    d = dict(zip(_rows(t, "decides")["applies_to"], _rows(t, "decides")["value"]))
    if set(d) != {"make", "move"} or not set(d.values()) <= set(YES_NO):
        errs.append("decides needs make and move, each yes/no")
    elif d["make"] != "yes":
        errs.append("the plan must decide builds (decides make = yes)")
    else:
        g = nx.Graph()
        g.add_nodes_from(("site", s) for s in ("RENO", "CMH"))
        g.add_edges_from((("site", s), ("cust", c)) for s, c in allowed)
        same_pool = nx.has_path(g, ("site", "RENO"), ("site", "CMH"))
        pdc_serves = any(s == "CMH" for s, _ in allowed)
        if d["move"] == "yes" and same_pool:
            errs.append("transfers are decided but Reno and the PDC serve the same orders: moving stock between "
                        "them gains nothing, and stock in transit would only hide surplus")
        if d["move"] == "no" and pdc_serves and not same_pool:
            errs.append("the PDC serves orders on its own but the plan may not transfer stock to it")
    return errs


# ---------- changes: what a person or an LLM proposes, as a list ----------

KEY = ["prior", "applies_to", "from_date"]


def normalise(t: pd.DataFrame) -> pd.DataFrame:
    """Same table, every cell as text (numbers without trailing .0), in a fixed row order. Two tables that mean the
    same thing normalise to the same rows."""
    def txt(v):
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        return "" if pd.isna(v) else str(v).strip()
    out = t[COLUMNS].copy()
    for c in COLUMNS:
        out[c] = out[c].map(txt)
    order = {p: i for i, p in enumerate(MEANING)}
    natural = {a: i for i, a in enumerate([f"{s}>{c}" for s in ("RENO", "CMH") for c in ("WEB", "DEALERS", "COMMERCIAL")]
                                          + list(LINES) + list(dict.fromkeys(g for g, _, _ in POLICY)) + ["make", "move"])}
    return out.assign(_o=out["prior"].map(order).fillna(len(order)), _a=out["applies_to"].map(natural).fillna(len(natural))) \
              .sort_values(["_o", "_a", "applies_to", "from_date"], kind="stable") \
              .drop(columns=["_o", "_a"]).reset_index(drop=True)


def diff(old: pd.DataFrame, new: pd.DataFrame) -> list[dict]:
    """Changes that turn old into new: [{prior, applies_to, from_date, old, new}]; old or new is None for a row
    removed or added."""
    a, b = (normalise(t).groupby(KEY, sort=False)["value"].last() for t in (old, new))   # a duplicate row: last wins
    out = []
    for k in list(a.index) + [k for k in b.index if k not in a.index]:
        va, vb = a.get(k), b.get(k)
        if va != vb:
            out.append({"prior": k[0], "applies_to": k[1], "from_date": k[2], "old": va, "new": vb})
    return out


def apply_changes(t: pd.DataFrame, changes: list[dict]) -> pd.DataFrame:
    """Apply a change list (as from `diff`, or proposed by a person or an LLM). new=None removes the row; a row not
    in the table is added. Validate the result before running it."""
    rows = normalise(t).set_index(KEY)["value"].to_dict()
    for c in changes:
        k = (c["prior"], c["applies_to"], c.get("from_date") or "")
        if c.get("new") is None:
            rows.pop(k, None)
        else:
            rows[k] = str(c["new"]).strip()
    out = pd.DataFrame([(*k, v) for k, v in rows.items()], columns=KEY + ["value"])[COLUMNS]
    return normalise(out)


def describe_change(c: dict) -> str:
    """One change in words, e.g. 'build_weeks · mtb-carbon: 1 → 2'."""
    where = c["applies_to"] + (f" from {c['from_date']}" if c.get("from_date") else "")
    if c.get("old") is None:
        return f"{c['prior']} · {where}: added ({c['new']})"
    if c.get("new") is None:
        return f"{c['prior']} · {where}: removed (was {c['old']})"
    return f"{c['prior']} · {where}: {c['old']} → {c['new']}"
