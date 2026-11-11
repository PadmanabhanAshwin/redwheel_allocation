"""Business logic: turn read-in sources into master tables."""
from __future__ import annotations

import pandas as pd

from redwheel import read, rtn
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

def build_routing(dim_sku: pd.DataFrame) -> pd.DataFrame:
    """What is built where. FACT: a sku's class + trim match exactly one line.
    ASSUMPTION: all lines are at Reno; one unit of line capacity per bike."""
    return pd.DataFrame({
        "item": dim_sku["sku"],
        "line": "RENO/" + dim_sku["line_id"],
        "output": "RENO",
        "capacity_per_unit": 1,
        "delay": BUILD_WEEKS,
    })


def build_routes() -> pd.DataFrame:
    """What can go where. Every physically possible route; which ones to *use* is a planning prior.
    ASSUMPTION: Reno -> Columbus takes TRANSFER_WEEKS; either site can ship to every customer."""
    rows = [("RENO", "CMH", TRANSFER_WEEKS)]
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


def build_object(m: dict) -> rtn.RTN:
    items = m["dim_sku"].rename(columns={"sku": "item"})
    locations = m["dim_location"]
    weeks = (m["dim_week"][m["dim_week"]["in_plan_horizon"]]
             .rename(columns={"week_idx": "t"})[["t", "week_start"]].reset_index(drop=True))
    resources = rtn.generate_resources(items, locations)
    tasks, arrows = rtn.generate_tasks(build_routing(m["dim_sku"]), build_routes(), items, locations)
    obj = rtn.RTN(items=items, locations=locations, weeks=weeks,
                  resources=resources, tasks=tasks, arrows=arrows,
                  opening=build_opening(m, resources),
                  arrivals=build_arrivals(m, resources, weeks))
    rtn.validate(obj)
    return obj
