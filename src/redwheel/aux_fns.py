"""Business logic: turn read-in sources into master tables."""
from __future__ import annotations

import pandas as pd

from redwheel import read
from redwheel.config import CHANNELS, PLAN_END, PLAN_START, POLICY, SNAPSHOT
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
    """Every forecast week. week_idx 0 = plan start; fiscal year runs Sep-Aug, named by start year."""
    w = pd.DataFrame({"week_start": sorted(forecast["week_start"].unique())})
    w["week_idx"] = ((w["week_start"] - PLAN_START).dt.days // 7).astype(int)
    w["fiscal_year"] = w["week_start"].dt.year - (w["week_start"].dt.month < 9)
    w["in_plan_horizon"] = w["week_start"].between(PLAN_START, PLAN_END)
    return w


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
    return {
        "fact_orders": orders,
        "fact_inventory": inventory,
        "fact_capacity": build_capacity(read.read_capacity()),
        "fact_forecast": forecast,
        "dim_sku": dim_sku,
        "dim_line": build_dim_line(dim_sku),
        "dim_week": build_dim_week(forecast),
        "dim_policy": build_dim_policy(),
        "opening_position": build_opening_position(orders, inventory),
    }
