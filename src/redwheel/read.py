"""Readers: one per raw file. Rename to common columns and parse types; no business logic."""
from __future__ import annotations

import pandas as pd

from redwheel.config import RAW_DIR
from redwheel.utils import to_bool


def _csv(f: str) -> pd.DataFrame:
    return pd.read_csv(RAW_DIR / f, dtype=str)


def read_dtc() -> pd.DataFrame:
    f = "dtc_web_orders.csv"
    r = _csv(f)
    return pd.DataFrame({
        "channel": "dtc",
        "order_id": r["order_id"],
        "party_id": r["customer_id"],
        "party_name": None,                      # web customers have no name
        "state": r["ship_to_state"],
        "order_date": pd.to_datetime(r["order_date"], format="%Y-%m-%d"),
        "need_by_date": pd.NaT,                  # no requested date on web orders
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
    r = _csv(f)
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
    r = _csv(f)
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


def read_plant_inventory() -> pd.DataFrame:
    r = _csv("plant_inventory_snapshot.csv")
    return pd.DataFrame({
        "as_of_date": pd.to_datetime(r["as_of_date"], format="%Y-%m-%d"),
        "location_code": r["location_code"],
        "location_name": r["location_name"],
        "state": None,                           # not in the file
        "sku": r["sku"],
        "on_hand": r["on_hand_qty"].astype(int),
    })


def read_dealer_stock() -> pd.DataFrame:
    r = _csv("dealer_stock_report.csv")
    return pd.DataFrame({
        "as_of_date": pd.to_datetime(r["Count Date"], format="%m/%d/%Y"),
        "location_code": r["Dealer #"],
        "location_name": r["Dealer"],
        "state": r["State"],
        "sku": r["Item"],
        "on_hand": r["On Hand"].astype(int),
    })


def read_capacity() -> pd.DataFrame:
    r = _csv("capacity_plan.csv")
    return pd.DataFrame({
        "week_start": pd.to_datetime(r["week_start"], format="%Y-%m-%d"),
        "class": r["class"],
        "trim": r["trim"],
        "capacity_units": r["capacity_units"].astype(int),
    })


def read_forecast(channel: str) -> pd.DataFrame:
    """channel: 'dtc' | 'dealer' | 'commercial' -> forecast_{channel}.csv"""
    r = _csv(f"forecast_{channel}.csv")
    return pd.DataFrame({
        "week_start": pd.to_datetime(r["week_start"], format="%Y-%m-%d"),
        "sku": r["sku"],
        "channel": channel,
        "forecast_units": r["forecast_units"].astype(int),
    })
