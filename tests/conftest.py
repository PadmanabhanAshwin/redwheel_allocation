"""Shared fixtures: master data and the Redwheel object are built once per test run."""
import pytest

from redwheel import aux_fns

# Opening net position (on-hand at our sites - backlog) per SKU, recounted from the raw CSVs
# with the standard library only, independent of this codebase.
EXPECTED_NET0 = {
    "RW-1378": 2, "RW-2984": -100, "RW-3980": -634, "RW-4418": -1285, "RW-6416": -752,
    "RW-7298": 61, "RW-9304": -1425, "RW-9324": 1840, "RW-9835": 9, "RW-9901": -707,
}


@pytest.fixture(scope="session")
def m():
    return aux_fns.build_master()


@pytest.fixture(scope="session")
def obj(m):
    return aux_fns.build_object(m)
