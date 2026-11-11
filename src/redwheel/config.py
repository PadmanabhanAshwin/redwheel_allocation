"""Single place for paths, dates and client policy.

Anything that is a *client input* (targets, snapshot date) lives here or in a data
table, never inline in engine code. Facts vs assumptions are marked per constant.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data"          # the nine CSVs exactly as Redwheel shared them (read-only)
OUT_DIR = ROOT / "outputs"       # generated master tables, plan, KPIs

# FACT: inventory files are dated 2026-09-07; order history ends 2026-09-06.
SNAPSHOT = pd.Timestamp("2026-09-07")

# FACT: capacity file covers exactly these 121 Monday weeks -> plan horizon.
PLAN_START = pd.Timestamp("2026-09-07")
PLAN_END = pd.Timestamp("2028-12-25")

# FACT (brief): weeks-of-supply targets per group.
# ASSUMPTION: the 2028 road step applies from the first Monday of 2028 (2028-01-03).
POLICY = [
    # target_group, effective_from, target_wos
    ("road", "2026-09-07", 8),
    ("road", "2028-01-03", 10),
    ("mtb_base", "2026-09-07", 12),
    ("mtb_carbon", "2026-09-07", 15),
]

# Raw value -> bool for the three fulfilment-flag spellings (true / Y / Yes).
TRUE_FLAGS = {"true", "y", "yes"}
FALSE_FLAGS = {"false", "n", "no"}

CHANNELS = ("dtc", "dealer", "commercial")

# ASSUMPTIONS (no data on either): a bike built in a week can ship that week;
# a Reno -> Columbus transfer takes one week.
BUILD_WEEKS = 0
TRANSFER_WEEKS = 1
