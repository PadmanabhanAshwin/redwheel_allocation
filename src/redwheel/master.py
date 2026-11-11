"""Step 1 — master data. Run cell by cell (VS Code: "Run Cell"), or end to end:

    python -m redwheel.master

Each cell defines one function and, under `if __name__ == "__main__":`, runs it and
prints the checks. That block runs interactively but is skipped when tests/app import
this module.

Sub-steps
    1.1  orders     3 channel files  -> fact_orders (+ open_at_snapshot)
    1.2  inventory  plant + dealer   -> fact_inventory (nettable flag)
    1.3  capacity, forecast          -> fact_capacity, fact_forecast
    1.4  dimensions                  -> dim_sku, dim_line, dim_week, dim_policy
    1.5  derived + validate + write  -> opening_position, outputs/*.parquet, DQ log
"""
# %% 1.0 setup
from __future__ import annotations

import pandas as pd

from redwheel.config import FALSE_FLAGS, RAW_DIR, SNAPSHOT, TRUE_FLAGS

# Data-quality log: one entry per decision taken on the raw data.
# Keyed by id so re-running a cell overwrites rather than duplicates.
DQ: dict[str, dict] = {}


def dq(id_: str, file: str, issue: str, rule: str, kind: str, rows: int) -> None:
    """kind: 'fact' (observed in the file) or 'assumption' (our choice)."""
    DQ[id_] = dict(file=file, issue=issue, rule=rule, kind=kind, rows=rows)


def to_bool(s: pd.Series, file: str) -> pd.Series:
    """Map true/Y/Yes and false/N/No to bool; fail loudly on anything else."""
    low = s.str.strip().str.lower()
    unknown = ~low.isin(TRUE_FLAGS | FALSE_FLAGS)
    if unknown.any():
        raise ValueError(f"{file}: unmapped flags {sorted(low[unknown].unique())}")
    return low.isin(TRUE_FLAGS)


# %% 1.1 orders — one reader per channel, mapped onto common column names
# Common shape for every reader. class/trim/size are carried only to build
# dim_sku in 1.4 and are dropped from fact_orders.
ORDER_COLS = [
    "channel", "order_id", "party_id", "party_name", "state",
    "order_date", "need_by_date", "sku", "class", "trim", "size",
    "qty", "unit_price", "fulfilled", "ship_date", "source_file",
]


def read_dtc() -> pd.DataFrame:
    f = "dtc_web_orders.csv"
    r = pd.read_csv(RAW_DIR / f, dtype=str)
    return pd.DataFrame({
        "channel": "dtc",
        "order_id": r["order_id"],
        "party_id": r["customer_id"],
        "party_name": None,                      # web customers have no name
        "state": r["ship_to_state"],
        "order_date": pd.to_datetime(r["order_date"], format="%Y-%m-%d"),
        "need_by_date": pd.NaT,                  # web orders carry no requested date
        "sku": r["sku"],
        "class": r["class"], "trim": r["trim"], "size": r["size"],
        "qty": r["qty"].astype(int),
        "unit_price": r["unit_price"].astype(float),
        "fulfilled": to_bool(r["is_fulfilled"], f),
        "ship_date": pd.to_datetime(r["ship_date"], format="%Y-%m-%d"),
        "source_file": f,
    })


def read_dealer() -> pd.DataFrame:
    f = "dealer_orders_export.csv"
    r = pd.read_csv(RAW_DIR / f, dtype=str)
    return pd.DataFrame({
        "channel": "dealer",
        "order_id": r["Dealer Order #"],
        "party_id": r["Dealer ID"],
        "party_name": r["Dealer Name"],
        "state": r["State"],
        "order_date": pd.to_datetime(r["Order Date"], format="%m/%d/%Y"),
        "need_by_date": pd.to_datetime(r["Requested Ship Date"], format="%m/%d/%Y"),
        "sku": r["SKU"],
        "class": r["Class"], "trim": r["Trim"], "size": r["Size"],
        "qty": r["Qty"].astype(int),
        "unit_price": r["Wholesale Price"].astype(float),
        "fulfilled": to_bool(r["Fulfilled (Y/N)"], f),
        "ship_date": pd.to_datetime(r["Shipped"], format="%m/%d/%Y"),
        "source_file": f,
    })


def read_commercial() -> pd.DataFrame:
    f = "Commercial_PO_Log.csv"
    r = pd.read_csv(RAW_DIR / f, dtype=str)
    return pd.DataFrame({
        "channel": "commercial",
        "order_id": r["PO Number"],
        "party_id": r["Account"],                # no account id in the file; name is the key
        "party_name": r["Account"],
        "state": None,                           # no location in the file
        "order_date": pd.to_datetime(r["PO Date"], format="%d-%b-%Y"),
        "need_by_date": pd.to_datetime(r["Need By"], format="%d-%b-%Y"),
        "sku": r["Product"],
        "class": r["Class"], "trim": r["Material"], "size": r["Length"],
        "qty": r["Units"].astype(int),
        "unit_price": r["Net Price"].astype(float),
        "fulfilled": to_bool(r["Fulfilled"], f),
        "ship_date": pd.to_datetime(r["Delivered"], format="%d-%b-%Y"),
        "source_file": f,
    })


def read_orders() -> pd.DataFrame:
    """Union of the three channels, attributes normalised, open_at_snapshot derived."""
    o = pd.concat([read_dtc(), read_dealer(), read_commercial()], ignore_index=True)[ORDER_COLS]
    for c in ("class", "trim"):
        o[c] = o[c].str.strip().str.lower()       # 'Road'/'road', 'Carbon'/'carbon'
    o["size"] = o["size"].str.strip().str.upper()

    # An order is open at the snapshot if it has not shipped, or ships after the snapshot.
    shipped_later = o["ship_date"] > SNAPSHOT
    o["open_at_snapshot"] = ~o["fulfilled"] | shipped_later

    dq("ORD-01", "all order files", "three date formats (ISO, MM/DD/YYYY, DD-Mon-YYYY)",
       "explicit format per file; parse fails loudly", "fact", len(o))
    dq("ORD-02", "all order files", "fulfilled flag spelled true/Y/Yes",
       "map to bool; unknown values raise", "fact", len(o))
    dq("ORD-03", "all order files", "orders marked fulfilled with ship date after snapshot",
       "treated as open (backlog) at snapshot", "assumption", int(shipped_later.sum()))
    return o


if __name__ == "__main__":
    orders = read_orders()
    print(f"{len(orders):,} order lines\n")
    print("rows by channel:", orders["channel"].value_counts().to_dict())
    print("duplicate (channel, order_id):", orders.duplicated(["channel", "order_id"]).sum())
    print("nulls in key fields:",
          orders[["order_id", "order_date", "sku", "qty"]].isna().sum().to_dict())
    print("order date range:", orders["order_date"].min().date(), "->",
          orders["order_date"].max().date())

    # Fulfilment consistency: a fulfilled order should have a ship date and vice versa.
    print("\nfulfilled but no ship date:", (orders.fulfilled & orders.ship_date.isna()).sum())
    print("not fulfilled but has ship date:", (~orders.fulfilled & orders.ship_date.notna()).sum())
    print("ship date before order date:", (orders.ship_date < orders.order_date).sum())

    # SKU attributes must be identical across channels (one class/trim/size per sku).
    attrs = orders.groupby("sku")[["class", "trim", "size"]].nunique()
    print("\nSKUs with conflicting attributes:", int((attrs > 1).any(axis=1).sum()))

    # Backlog at snapshot, by sku x channel.
    print("\nopen units at snapshot (backlog):")
    print(orders[orders.open_at_snapshot]
          .pivot_table(index="sku", columns="channel", values="qty", aggfunc="sum",
                       fill_value=0, margins=True, margins_name="total"))

# %% 1.2 inventory — plant + dealer -> fact_inventory            (next)

# %% 1.3 capacity, forecast -> fact_capacity, fact_forecast      (next)

# %% 1.4 dimensions -> dim_sku, dim_line, dim_week, dim_policy   (next)

# %% 1.5 opening_position, validate, write outputs + DQ log      (next)
