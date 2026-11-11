"""Generic helpers: flag parsing and the data-quality log."""
from __future__ import annotations

import pandas as pd

from redwheel.config import FALSE_FLAGS, TRUE_FLAGS

# Data-quality log, keyed by id so re-running a cell overwrites instead of duplicating.
DQ: dict[str, dict] = {}


def dq(id_: str, file: str, issue: str, rule: str, kind: str, rows: int) -> None:
    """Record one data decision. kind: 'fact' (seen in the file) or 'assumption' (our choice)."""
    DQ[id_] = dict(file=file, issue=issue, rule=rule, kind=kind, rows=rows)


def to_bool(s: pd.Series, file: str) -> pd.Series:
    """Map true/Y/Yes -> True and false/N/No -> False; raise on anything else."""
    low = s.str.strip().str.lower()
    unknown = ~low.isin(TRUE_FLAGS | FALSE_FLAGS)
    if unknown.any():
        raise ValueError(f"{file}: unmapped flags {sorted(low[unknown].unique())}")
    return low.isin(TRUE_FLAGS)
