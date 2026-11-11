"""Business logic: turn read-in sources into master tables."""
from __future__ import annotations

import numpy as np
import pandas as pd

from redwheel import engine, read, rtn
from redwheel.config import (BUILD_WEEKS, CHANNELS, PLAN_END, PLAN_START, POLICY, SNAPSHOT,
                             TRANSFER_WEEKS)
from redwheel.utils import dq

# FACT: location names in plant_inventory_snapshot.csv. Everything else is a dealer.
SITE_TYPE = {"RENO-FG": "plant", "CMH-DC": "dc"}


def line_id(cls: pd.Series, trim: pd.Series) -> pd.Series:
    return cls + "-" + trim                     # e.g. 'mtb-carbon'


def target_group(cls: pd.Series, trim: pd.Series) -> pd.Series:
    """Brief sets targets for road (both trims), mtb base, mtb carbon."""
    return cls.where(cls == "road", "mtb_" + trim)


# ---------- 1.1 orders ----------

def union_orders(*channels: pd.DataFrame) -> pd.DataFrame:
    """Stack channel orders, normalise sku attributes, flag what is open at the snapshot."""
    o = pd.concat(channels, ignore_index=True)
    o["class"] = o["class"].str.strip().str.lower()
    o["trim"] = o["trim"].str.strip().str.lower()
    o["size"] = o["size"].str.strip().str.upper()

    # Open at snapshot = not fulfilled, or fulfilled but shipped after the snapshot.
    shipped_later = o["ship_date"] > SNAPSHOT
    o["open_at_snapshot"] = ~o["fulfilled"] | shipped_later
    dq("ORD-03", "order files", "marked fulfilled but ship date after snapshot",
       "counted as open (backlog) at snapshot", "assumption", int(shipped_later.sum()))
    return o


# ---------- 1.2 inventory ----------

def union_inventory(plant: pd.DataFrame, dealer: pd.DataFrame) -> pd.DataFrame:
    """One inventory table; `nettable` marks stock Redwheel can ship against its own orders."""
    inv = pd.concat([plant, dealer], ignore_index=True)
    inv["location_type"] = inv["location_code"].map(SITE_TYPE).fillna("dealer")
    inv["nettable"] = inv["location_type"] != "dealer"
    dq("INV-01", "dealer_stock_report.csv", "dealer on-hand is stock already sold to dealers",
       "reported only, not netted against Redwheel backlog", "assumption",
       int((~inv["nettable"]).sum()))
    return inv


# ---------- 1.3 capacity, forecast ----------

def build_capacity(cap: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "week_start": cap["week_start"],
        "line_id": line_id(cap["class"], cap["trim"]),
        "capacity_units": cap["capacity_units"],
    })


def union_forecast(*channels: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(channels, ignore_index=True)


# ---------- 1.4 dimensions ----------

def build_dim_sku(orders: pd.DataFrame) -> pd.DataFrame:
    d = orders.groupby("sku", as_index=False)[["class", "trim", "size"]].first()
    d["line_id"] = line_id(d["class"], d["trim"])
    d["target_group"] = target_group(d["class"], d["trim"])
    return d


def build_dim_line(dim_sku: pd.DataFrame) -> pd.DataFrame:
    return (dim_sku[["line_id", "class", "trim", "target_group"]]
            .drop_duplicates().sort_values("line_id").reset_index(drop=True))


def build_dim_week(forecast: pd.DataFrame) -> pd.DataFrame:
    """Every forecast week. week_idx 1 = plan start (0 is the opening snapshot);
    fiscal year runs Sep-Aug, named by start year."""
    w = pd.DataFrame({"week_start": sorted(forecast["week_start"].unique())})
    w["week_idx"] = ((w["week_start"] - PLAN_START).dt.days // 7 + 1).astype(int)
    w["fiscal_year"] = w["week_start"].dt.year - (w["week_start"].dt.month < 9)
    w["in_plan_horizon"] = w["week_start"].between(PLAN_START, PLAN_END)
    return w


# Customer location per order channel. Dealers also hold their own stock -> class 'dealer'.
CUSTOMER_LOCATION = {"dtc": "WEB", "dealer": "DEALERS", "commercial": "COMMERCIAL"}


def build_dim_location(dim_line: pd.DataFrame) -> pd.DataFrame:
    """The places in Redwheel's network. source_code / channel link a location to the raw files."""
    rows = [
        # location_id, location_class, parent, name, source_code, channel
        ("RENO", "factory", None, "Reno Plant - Finished Goods", "RENO-FG", None),
        ("CMH", "distribution_center", None, "Columbus Distribution Center", "CMH-DC", None),
        (rtn.transit_location("RENO", "CMH"), "in_transit", None, "Reno -> Columbus", None, None),
    ]
    rows += [(f"RENO/{ln}", "production_line", "RENO", f"Reno {ln} line", None, None)
             for ln in dim_line["line_id"]]
    rows += [(loc, "dealer" if ch == "dealer" else "customer", None, f"{ch} customers", None, ch)
             for ch, loc in CUSTOMER_LOCATION.items()]
    d = pd.DataFrame(rows, columns=["location_id", "location_class", "parent", "name",
                                    "source_code", "channel"])
    d.insert(3, "ours", d["location_class"].map(lambda c: rtn.LOCATION_CLASSES[c]["ours"]))
    return d


def build_dim_policy() -> pd.DataFrame:
    p = pd.DataFrame(POLICY, columns=["target_group", "effective_from", "target_wos"])
    p["effective_from"] = pd.to_datetime(p["effective_from"])
    return p


# ---------- 1.5 opening position ----------

def build_opening_position(orders: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    """Per sku at the snapshot: nettable on-hand (all Redwheel sites), backlog, net = on-hand - backlog."""
    on_hand = inventory[inventory["nettable"]].groupby("sku")["on_hand"].sum()
    backlog = orders[orders["open_at_snapshot"]].groupby("sku")["qty"].sum()
    p = pd.DataFrame({"on_hand_nettable": on_hand, "backlog": backlog}).fillna(0).astype(int)
    p["net0"] = p["on_hand_nettable"] - p["backlog"]
    return p.rename_axis("sku").reset_index()


# ---------- everything, in one call (for tests and later steps) ----------

def build_master() -> dict[str, pd.DataFrame]:
    orders = union_orders(read.read_dtc(), read.read_dealer(), read.read_commercial())
    inventory = union_inventory(read.read_plant_inventory(), read.read_dealer_stock())
    forecast = union_forecast(*(read.read_forecast(c) for c in CHANNELS))
    dim_sku = build_dim_sku(orders)
    dim_line = build_dim_line(dim_sku)
    return {
        "fact_orders": orders,
        "fact_inventory": inventory,
        "fact_capacity": build_capacity(read.read_capacity()),
        "fact_forecast": forecast,
        "dim_sku": dim_sku,
        "dim_line": dim_line,
        "dim_location": build_dim_location(dim_line),
        "dim_week": build_dim_week(forecast),
        "dim_policy": build_dim_policy(),
        "opening_position": build_opening_position(orders, inventory),
    }


# ---------- 2 the object ----------

def build_routing(dim_sku: pd.DataFrame, build_weeks: int = BUILD_WEEKS) -> pd.DataFrame:
    """What is built where. FACT: a sku's class + trim match exactly one line.
    ASSUMPTION: all lines are at Reno; one unit of line capacity per bike."""
    return pd.DataFrame({
        "item": dim_sku["sku"],
        "line": "RENO/" + dim_sku["line_id"],
        "output": "RENO",
        "capacity_per_unit": 1,
        "delay": build_weeks,
    })


def build_routes(transfer_weeks: int = TRANSFER_WEEKS) -> pd.DataFrame:
    """What can go where. Every physically possible route; which ones to *use* is a planning prior.
    ASSUMPTION: Reno -> Columbus takes TRANSFER_WEEKS; either site can ship to every customer."""
    rows = [("RENO", "CMH", transfer_weeks)]
    rows += [(site, cust, 0) for site in ("RENO", "CMH") for cust in CUSTOMER_LOCATION.values()]
    return pd.DataFrame(rows, columns=["origin", "destination", "delay"])


def _on_resources(resources: pd.DataFrame, ids: pd.Series, qty: pd.Series, what: str) -> pd.Series:
    """Sum qty onto resource ids; raise if any id is not a resource (a mapping error)."""
    unknown = set(ids) - set(resources["resource_id"])
    if unknown:
        raise ValueError(f"{what}: no resource for {sorted(unknown)[:3]}")
    return qty.groupby(ids.values).sum().reindex(resources["resource_id"], fill_value=0)


def build_opening(m: dict, resources: pd.DataFrame) -> pd.Series:
    """Level at t = 0. Our sites from the plant snapshot, dealer stock (all dealers summed),
    backlog per sku x channel. In-transit starts empty (ASSUMPTION: no transfer data)."""
    loc = m["dim_location"]
    site = loc.dropna(subset=["source_code"]).set_index("source_code")["location_id"]
    cust = loc.dropna(subset=["channel"]).set_index("channel")["location_id"]

    inv = m["fact_inventory"]
    plant = inv[inv["nettable"]]
    dealer = inv[~inv["nettable"]]
    o = m["fact_orders"][m["fact_orders"]["open_at_snapshot"]]
    ids = pd.concat([
        "inventory|" + plant["sku"] + "|" + plant["location_code"].map(site),
        "inventory|" + dealer["sku"] + "|" + cust["dealer"],
        "order|" + o["sku"] + "|" + o["channel"].map(cust),
    ], ignore_index=True)
    qty = pd.concat([plant["on_hand"], dealer["on_hand"], o["qty"]], ignore_index=True)
    return _on_resources(resources, ids, qty, "opening").rename("opening")


def build_arrivals(m: dict, resources: pd.DataFrame, weeks: pd.DataFrame) -> pd.DataFrame:
    """What comes from outside each week: forecast onto orders, capacity onto lines."""
    loc = m["dim_location"]
    cust = loc.dropna(subset=["channel"]).set_index("channel")["location_id"]
    t = weeks.set_index("week_start")["t"]

    f = m["fact_forecast"][m["fact_forecast"]["week_start"].isin(t.index)]
    c = m["fact_capacity"]
    ids = pd.concat(["order|" + f["sku"] + "|" + f["channel"].map(cust),
                     "capacity||RENO/" + c["line_id"]], ignore_index=True)
    week = pd.concat([f["week_start"], c["week_start"]], ignore_index=True).map(t)
    qty = pd.concat([f["forecast_units"], c["capacity_units"]], ignore_index=True)
    if week.isna().any():
        raise ValueError("arrival outside the plan horizon")
    unknown = set(ids) - set(resources["resource_id"])
    if unknown:
        raise ValueError(f"arrivals: no resource for {sorted(unknown)[:3]}")
    a = qty.groupby([ids.values, week.astype(int).values]).sum().unstack(fill_value=0)
    return a.reindex(index=resources["resource_id"], columns=weeks["t"], fill_value=0)


def forecast_by_item(m: dict) -> pd.DataFrame:
    """Total forecast (all channels) per sku x week index, every forecast week (1..156),
    including the weeks after the plan horizon that targets near the end look ahead into."""
    t = m["dim_week"].set_index("week_start")["week_idx"]
    f = m["fact_forecast"].assign(t=m["fact_forecast"]["week_start"].map(t))
    return f.pivot_table(index="sku", columns="t", values="forecast_units", aggfunc="sum").rename_axis("item")


def target_wos(m: dict, weeks: pd.DataFrame) -> pd.DataFrame:
    """Target weeks of supply per sku x plan week, from dim_policy (latest row effective that week)."""
    p = m["dim_policy"].sort_values("effective_from")
    groups = m["dim_sku"].set_index("sku")["target_group"]
    out = pd.DataFrame(index=groups.index.rename("item"), columns=weeks["t"], dtype=float)
    for t, ws in zip(weeks["t"], weeks["week_start"]):
        current = p[p["effective_from"] <= ws].groupby("target_group")["target_wos"].last()
        out[t] = groups.map(current).to_numpy()
    return out


# ---------- demand sources ----------

# FACT: site coordinates are public geography. ASSUMPTION: a state is served by the nearer site
# (straight-line distance from the state's approximate geographic centre). Used only to describe
# where demand is; the base plan does not use it.
SITE_COORD = {"RENO": (39.53, -119.81), "CMH": (39.96, -83.00)}
STATE_CENTRE = {
    "OR": (44.0, -120.5), "MN": (46.3, -94.3), "WA": (47.4, -120.5), "CO": (39.0, -105.5), "MA": (42.3, -71.8),
    "UT": (39.3, -111.7), "CA": (37.2, -119.4), "GA": (32.7, -83.4), "VT": (44.0, -72.7), "MT": (47.0, -109.6),
    "FL": (28.6, -82.4), "MI": (44.3, -85.4), "PA": (40.9, -77.8), "AZ": (34.3, -111.7), "NY": (42.9, -75.5),
    "NC": (35.6, -79.4), "ID": (44.4, -114.6), "TX": (31.5, -99.3), "NM": (34.4, -106.1), "IL": (40.0, -89.2),
}


def _km(a: tuple, b: tuple) -> float:
    """Great-circle distance."""
    la1, lo1, la2, lo2 = map(np.radians, (*a, *b))
    h = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return float(6371 * 2 * np.arcsin(np.sqrt(h)))


def nearest_site(state: str) -> str:
    if state not in STATE_CENTRE:
        raise ValueError(f"no coordinates for state {state}")
    return min(SITE_COORD, key=lambda site: _km(STATE_CENTRE[state], SITE_COORD[site]))


def demand_sources(m: dict) -> dict:
    """Where demand comes from: channel, geography, customer. History = the 52 weeks of orders."""
    o, f = m["fact_orders"], m["fact_forecast"]
    line = m["dim_sku"].set_index("sku")["line_id"]
    plan_weeks = m["dim_week"].loc[m["dim_week"]["in_plan_horizon"], "week_start"]
    first52 = plan_weeks.iloc[:52]
    hist = o.groupby("channel")["qty"].sum()
    by_channel = pd.DataFrame({
        "orders_last_52": hist,
        "order_lines": o.groupby("channel").size(),
        "forecast_next_52": f[f["week_start"].isin(first52)].groupby("channel")["forecast_units"].sum(),
        "forecast_horizon": f[f["week_start"].isin(plan_weeks)].groupby("channel")["forecast_units"].sum(),
    })
    wk = o["order_date"] - pd.to_timedelta(o["order_date"].dt.dayofweek, unit="D")
    located = o[o["state"].notna()]
    by_state = located.pivot_table(index="state", columns="channel", values="qty", aggfunc="sum", fill_value=0)
    by_state["site"] = [nearest_site(s) for s in by_state.index]
    dealers = (o[o["channel"] == "dealer"].groupby(["party_id", "party_name", "state"], as_index=False)["qty"].sum()
               .sort_values("qty", ascending=False).reset_index(drop=True))
    return {
        "by_channel": by_channel,
        "weekly_orders": o.groupby([wk.rename("week"), "channel"])["qty"].sum().unstack(fill_value=0),
        "weekly_forecast": (f[f["week_start"].isin(plan_weeks)].groupby(["week_start", "channel"])["forecast_units"]
                            .sum().unstack(fill_value=0)),
        "by_state": by_state,
        "line_by_channel": o.assign(line=o["sku"].map(line)).pivot_table(index="line", columns="channel",
                                                                         values="qty", aggfunc="sum", fill_value=0),
        "dealers": dealers,
        "commercial_types": (o[o["channel"] == "commercial"].groupby("party_type")["qty"]
                             .agg(units="sum", order_lines="size").sort_values("units", ascending=False)),
        "commercial_accounts": int(o.loc[o["channel"] == "commercial", "party_id"].nunique()),
        "total": int(o["qty"].sum()),
    }


# ---------- 4 report ----------

def _held_from(ok: pd.DataFrame) -> pd.Series:
    """First week from which ok holds every week to the end; NaN if it fails in the last week."""
    not_ok_last = ok.apply(lambda r: (~r)[~r].index.max() if (~r).any() else 0, axis=1)
    last = ok.columns.max()
    return (not_ok_last + 1).where(not_ok_last < last)


def target_report(m: dict, obj: rtn.RTN, X: pd.DataFrame, X_base: pd.DataFrame,
                  target_units: pd.DataFrame, target_wos: pd.DataFrame, demand: pd.DataFrame) -> pd.DataFrame:
    """Per sku: is the plan hitting its target, from when, and against doing nothing.
    'Below target' is judged in units (net position < next N weeks of forecast), as in the LP."""
    weeks = list(target_units.columns)
    net = rtn.net_position(obj, X).loc[target_units.index]
    wos = rtn.weeks_of_supply(net, demand)
    at_target = net[weeks] >= target_units - 1e-6
    base_at_target = rtn.net_position(obj, X_base).loc[target_units.index, weeks] >= target_units - 1e-6
    held = _held_from(at_target)
    date = obj.weeks.set_index("t")["week_start"]
    once_held = pd.DataFrame({t: t >= held for t in weeks})          # False where never held
    over = (wos[weeks] - target_wos).where(once_held)
    sku = m["dim_sku"].set_index("sku")
    r = pd.DataFrame({
        "line": sku["line_id"], "group": sku["target_group"],
        "target_wk1": target_wos[1],
        "wos_wk1": wos[1].round(1),
        "first_at_target": at_target.idxmax(axis=1).where(at_target.any(axis=1)),
        "held_from": held,
        "held_from_date": held.map(date),
        "weeks_below": (~at_target).sum(axis=1),
        "weeks_below_no_plan": (~base_at_target).sum(axis=1),
        "backlog_cleared_from": _held_from(net[weeks] >= -1e-6),
        "max_wos_over_target_once_held": over.max(axis=1).round(1),
    })
    r["limited_by"] = [_limited_by(obj, at_target.loc[s], held[s], sku.at[s, "line_id"], date) for s in r.index]
    return r.rename_axis("sku")


def _limited_by(obj: rtn.RTN, ok: pd.Series, held, line_id: str, date: pd.Series) -> str:
    """Why a sku is not at target earlier, read from the plan (the line is at full capacity throughout,
    which plan_checks verifies):
    - it reached target, then fell below again   -> demand in those weeks exceeded what the line could add
    - it first reaches target as capacity steps up -> capacity until that step-up
    - otherwise                                   -> clearing the opening backlog"""
    if ok.all():
        return "—"
    first = ok.idxmax() if ok.any() else None
    if first is not None and first < held:
        dip = ok.index[(~ok) & (ok.index > first)]
        span = date[dip.min()].strftime("%b"), date[dip.max()].strftime("%b %Y")
        return f"demand peak ahead (below target {span[0]}–{span[1]})"
    cap = obj.arrivals.loc[f"capacity||RENO/{line_id}"]
    step_up = [t for t in cap.index[1:] if cap[t] > cap[t - 1]]
    if pd.notna(held) and int(held) in step_up:
        return f"capacity until step-up, {date[int(held)].strftime('%-d %b %Y')}"
    return "opening backlog"


def group_wos(wos: pd.DataFrame, dim_sku: pd.DataFrame) -> pd.DataFrame:
    """Lowest sku weeks of supply in each target group: skus do not offset each other."""
    return wos.groupby(dim_sku.set_index("sku")["target_group"]).min()


def build_plan_table(obj: rtn.RTN, builds: pd.DataFrame) -> pd.DataFrame:
    """The deliverable: units to build per sku per week, long format."""
    t = builds.stack().rename("units").reset_index()
    t.columns = ["task_id", "t", "units"]
    parts = t["task_id"].str.split("|")
    out = pd.DataFrame({"week_start": t["t"].map(obj.weeks.set_index("t")["week_start"]),
                        "line": parts.str[2].str.replace("RENO/", "", regex=False),
                        "sku": parts.str[1], "units": t["units"].astype(int)})
    return out.sort_values(["week_start", "line", "sku"]).reset_index(drop=True)


def utilisation_by_year(obj: rtn.RTN, X: pd.DataFrame) -> pd.DataFrame:
    u = rtn.utilisation(obj, X)
    u.index = u.index.str.replace("capacity||RENO/", "", regex=False)
    ws = obj.weeks.set_index("t")["week_start"]
    fy = (ws.dt.year - (ws.dt.month < 9)).loc[u.columns]
    used = u.T.groupby(fy.values).mean().T.round(2)
    full = (u > 1 - 1e-9).T.groupby(fy.values).sum().T
    return pd.concat({"share_used": used, "weeks_full": full}, axis=1)


def build_object(m: dict, build_weeks: int = BUILD_WEEKS, transfer_weeks: int = TRANSFER_WEEKS) -> rtn.RTN:
    items = m["dim_sku"].rename(columns={"sku": "item"})
    locations = m["dim_location"]
    weeks = (m["dim_week"][m["dim_week"]["in_plan_horizon"]]
             .rename(columns={"week_idx": "t"})[["t", "week_start"]].reset_index(drop=True))
    resources = rtn.generate_resources(items, locations)
    tasks, arrows = rtn.generate_tasks(build_routing(m["dim_sku"], build_weeks), build_routes(transfer_weeks),
                                       items, locations)
    obj = rtn.RTN(items=items, locations=locations, weeks=weeks,
                  resources=resources, tasks=tasks, arrows=arrows,
                  opening=build_opening(m, resources),
                  arrivals=build_arrivals(m, resources, weeks))
    rtn.validate(obj)
    return obj


# ---------- the single button ----------

def run_plan() -> dict:
    """Raw files -> master data -> object -> LP -> whole-bike build plan -> report. One call."""
    m = build_master()
    obj = build_object(m)
    H = len(obj.weeks)
    demand = forecast_by_item(m)
    tw = target_wos(m, obj.weeks)
    tu = engine.forward_sum(demand, tw)
    line = m["dim_sku"].set_index("sku")["line_id"]
    free = list(obj.tasks.loc[obj.tasks["kind"] == "make", "task_id"])     # ships, moves stay 0
    lp = engine.decide(obj, free, tu, demand.loc[:, 1:H].mean(axis=1), line)
    builds = engine.round_runs(obj, lp.runs)
    X, X_base = rtn.levels(obj, builds), rtn.levels(obj)
    net, net_base = rtn.net_position(obj, X), rtn.net_position(obj, X_base)
    wos = rtn.weeks_of_supply(net, demand).loc[tu.index]
    return {
        "m": m, "obj": obj, "demand": demand, "target_wos": tw, "target_units": tu, "line": line,
        "lp": lp, "builds": builds, "X": X, "X_base": X_base, "net": net, "net_base": net_base,
        "wos": wos, "wos_base": rtn.weeks_of_supply(net_base, demand).loc[tu.index],
        "report": target_report(m, obj, X, X_base, tu, tw, demand),
        "group_wos": group_wos(wos, m["dim_sku"]),
        "utilisation": utilisation_by_year(obj, X),
        "build_plan": build_plan_table(obj, builds),
        "flows": ship_asap(m, obj, builds, demand.loc[:, 1:H]),
    }


def ship_asap(m: dict, obj: rtn.RTN, builds: pd.DataFrame, demand: pd.DataFrame) -> dict:
    """Project on hand and open orders per sku, assuming orders ship as soon as stock exists
    (sites pooled). The plan decides builds only; this splits its net position into its two parts.

    shipped[t]  = min(on_hand[t-1] + built[t], open[t-1] + demand[t])
    on_hand[t]  = on_hand[t-1] + built[t] - shipped[t]
    open[t]     = open[t-1] + demand[t] - shipped[t]
    so on_hand - open = net position every week, and from week 1 at most one of them is positive."""
    op = m["opening_position"].set_index("sku")
    items = list(demand.index)
    built = builds.groupby(builds.index.str.split("|").str[1]).sum().loc[items]
    H = demand.shape[1]
    on, opn, shp = (pd.DataFrame(0.0, index=items, columns=range(0, H + 1)) for _ in range(3))
    on[0], opn[0] = op.loc[items, "on_hand_nettable"].astype(float), op.loc[items, "backlog"].astype(float)
    for t in range(1, H + 1):
        avail, owed = on[t - 1] + built[t], opn[t - 1] + demand[t]
        shp[t] = np.minimum(avail, owed)
        on[t], opn[t] = avail - shp[t], owed - shp[t]
    return {"on_hand": on, "open_orders": opn, "shipped": shp.loc[:, 1:], "built": built, "demand": demand}


def plan_checks(r: dict) -> pd.DataFrame:
    """Every check that the plan is right, computed from the run itself."""
    m, obj, tu = r["m"], r["obj"], r["target_units"]
    weeks = list(tu.columns)
    X, lp, builds = r["X"], r["lp"], r["builds"]
    cap = X[X.index.str.startswith("capacity|")].loc[:, weeks]
    net = r["net"].loc[tu.index, weeks]
    below = net < tu - 1e-9
    below_lp = rtn.net_position(obj, lp.levels).loc[tu.index, weeks] < tu - 1e-6
    full_so_far = (cap < 0.5).cumprod(axis=1).astype(bool)
    not_explained = sum(not full_so_far.at[f"capacity||RENO/{r['line'][s]}", t]
                        for s in below.index for t in below.columns[below.loc[s]])
    gap = builds.cumsum(axis=1) - lp.runs.cumsum(axis=1)
    o = m["fact_orders"]
    net0_master = m["opening_position"].set_index("sku")["net0"]
    rows = [
        ("Master data", "order lines read", f"{len(o):,}", len(o) == 13_974),
        ("Master data", "backlog units at snapshot", f"{int(o.loc[o.open_at_snapshot, 'qty'].sum()):,}",
         o.loc[o.open_at_snapshot, "qty"].sum() == 5_991),
        ("Object", "resources / tasks / edges", f"{len(obj.resources)} / {len(obj.tasks)} / {len(obj.arrows)}",
         (len(obj.resources), len(obj.tasks), len(obj.arrows)) == (74, 80, 180)),
        ("Object", "opening net position = master data, every SKU", "",
         bool((r["net"][0].reindex(net0_master.index) == net0_master).all())),
        ("Solver", "closure: LP levels = equation rolled forward with LP builds",
         f"{np.abs(rtn.levels(obj, lp.runs).values - lp.levels.values).max():.1e}",
         np.abs(rtn.levels(obj, lp.runs).values - lp.levels.values).max() < 1e-6),
        ("Build plan", "whole bikes, none negative", "", bool((builds.values == np.round(builds.values)).all()
                                                               and builds.values.min() >= 0)),
        ("Build plan", "capacity never exceeded, no level below zero", f"lowest level {X.values.min():.0f}",
         X.values.min() >= 0),
        ("Build plan", "within 1 bike of the LP, cumulative, every SKU",
         f"{gap.values.min():.2f} to {gap.values.max():.2f}", gap.values.min() > -1 and gap.values.max() < 1),
        ("Build plan", "rounding adds no missed targets", "", not (below & ~below_lp).values.any()),
        ("Targets", "below target only when the line ran full every week until then",
         f"{int(below.values.sum())} SKU-weeks below, {not_explained} unexplained", not_explained == 0),
    ]
    return pd.DataFrame(rows, columns=["area", "check", "value", "pass"])


# ---------- LP vs the planner's rule ----------

def compare_plans(r: dict) -> dict:
    """Score three plans the same way: the LP (whole bikes), the lowest-cover-first rule, and no builds."""
    obj, tu = r["obj"], r["target_units"]
    weeks = list(tu.columns)
    H = len(weeks)
    wd = r["demand"].loc[:, 1:H].mean(axis=1)
    free = list(obj.tasks.loc[obj.tasks["kind"] == "make", "task_id"])
    plans = {"LP plan": r["builds"],
             "Lowest-cover-first rule": engine.lowest_cover_first(obj, free, tu, wd),
             "No builds": pd.DataFrame(0, index=free, columns=weeks)}
    date = obj.weeks.set_index("t")["week_start"]
    line = r["line"]
    summary, by_line, below_by_week, wos, at_target = {}, {}, {}, {}, {}
    for name, runs in plans.items():
        X = rtn.levels(obj, runs)
        net = rtn.net_position(obj, X).loc[tu.index, weeks]
        ok = net >= tu - 1e-6
        held = _held_from(ok)
        flows = ship_asap(r["m"], obj, runs, r["demand"].loc[:, 1:H])
        prev_open = flows["open_orders"].loc[:, 0:H - 1].set_axis(weeks, axis=1)
        on_time = flows["shipped"] - flows["shipped"].clip(upper=prev_open)
        summary[name] = {
            "Bikes built": int(runs.values.sum()),
            "Capacity respected": bool(X.values.min() >= -1e-9),
            "SKU-weeks below target": int((~ok).values.sum()),
            "Shortfall (weeks of demand, summed)": float((tu - net).clip(lower=0).div(wd, axis=0).values.sum()),
            "All targets held from": date[int(held.max())] if held.notna().all() else None,
            "On-time fill rate": float(on_time.values.sum() / flows["demand"].values.sum()),
            "LP objective (lower is better)": engine.objective_value(obj, runs, tu, wd, line),
        }
        by_line[name] = pd.DataFrame({"below": (~ok).sum(axis=1), "held": held}).groupby(line[tu.index]).agg(
            below=("below", "sum"), held=("held", "max"))
        below_by_week[name] = (~ok).sum(axis=0)
        wos[name] = rtn.weeks_of_supply(rtn.net_position(obj, X), r["demand"]).loc[tu.index]
        at_target[name] = ok
    return {"plans": plans, "summary": pd.DataFrame(summary), "by_line": by_line, "below_by_week": below_by_week,
            "wos": wos, "at_target": at_target,
            "lp_solver_objective": r["lp"].objective,
            "lp_unrounded_objective": engine.objective_value(obj, r["lp"].runs, tu, wd, line)}
