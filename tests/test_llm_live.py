"""LLM proposals, live: real requests against the real model, each with a known right answer.

Calls the API (costs money), so it runs only when asked:   RUN_LLM_TESTS=1 pytest tests/test_llm_live.py -v
Each request is graded on the exact change list: right changes, nothing extra. Requests the table cannot express
must propose nothing and say so; unclear requests must propose nothing and ask.
"""
import os

import pytest

from redwheel import llm, priors, scenarios as sc

pytestmark = pytest.mark.skipif(os.environ.get("RUN_LLM_TESTS") != "1", reason="live API calls; set RUN_LLM_TESTS=1")


def key(changes):
    return {(c["prior"], c["applies_to"], c.get("from_date") or "", c["new"]) for c in changes}


CASES = {
    "describe scenario B from A": (
        "A", "Web orders should ship only from the PDC in Columbus, which Reno restocks, with the plan deciding those "
             "transfers. Dealer and commercial orders ship straight from Reno. Building a bike now takes one week on "
             "every line.",
        key(priors.diff(sc.CASE_A.priors, sc.CASE_B.priors))),
    "one lead time": (
        "B", "MTB carbon now takes two weeks to build.",
        {("build_weeks", "mtb-carbon", "", "2")}),
    "a target step on a date": (
        "A", "From 6 September 2027, raise the MTB carbon weeks-of-supply target to 18 weeks.",
        {("target_weeks", "mtb_carbon", "2027-09-06", "18")}),
    "not expressible": (
        "B", "When the PDC runs short of a bike, let Reno ship that web order instead.",
        "unsupported"),
    "unclear": (
        "B", "Can you make the plan better?",
        "question"),
}


@pytest.mark.parametrize("name", CASES)
def test_live_proposal(name, obj):
    start, request, expected = CASES[name]
    p = llm.propose(request, sc.CASES[start].priors, obj)
    print(f"\n{name}: attempts {p.attempts}, tokens {p.usage}, errors {p.errors}")
    for c in p.changes:
        print("  ", priors.describe_change(c), "|", c["reason"])
    print("   unsupported:", p.unsupported, "| question:", p.question)
    if expected == "unsupported":
        assert p.changes == [] and p.unsupported
    elif expected == "question":
        assert p.changes == [] and p.question
    else:
        assert p.ok, p.errors
        assert key(p.changes) == expected


# ---------------- any tunable: requests -> edits, graded on what they do to the scenario ----------------

from redwheel import tunables as tu                                                          # noqa: E402
from redwheel.changes import Change                                                          # noqa: E402


def same_edits(changes, expected):
    """The same edits to the data, in any order (these requests' edits do not overlap, so order does not matter)."""
    return sorted(tu._key(c) for c in changes) == sorted(tu._key(c) for c in expected)


EDIT_CASES = {
    "your sentence: which line?": ("A", "A line is down for the next two weeks.", "question"),
    "MTB carbon down the next two weeks": (
        "A", "The MTB carbon line is down for the next two weeks.",
        [Change("arrival", {"kind": "capacity", "location": "RENO/mtb-carbon"}, "set", 0, 1, 2)]),
    "a whole month": (
        "A", "The road carbon line is down for all of March 2027.",                    # Mondays 1, 8, 15, 22, 29 Mar
        [Change("arrival", {"kind": "capacity", "location": "RENO/road-carbon"}, "set", 0, 26, 30)]),
    "E1 and E2 in one sentence": (
        "A", "The MTB carbon line is down for maintenance for the three weeks starting 1 March 2027, and dealer demand "
             "for RW-4418 is up 30% for the 13 weeks starting 4 January 2027.",
        list(sc.CASE_E1.changes + sc.CASE_E2.changes)),
    "E3, parts late": (
        "A", "Frames for RW-4418 will be late: none can be built in the eight weeks starting 25 October 2027.",
        list(sc.CASE_E3.changes)),
    "a stock count": (
        "A", "We counted 200 fewer RW-9324 at Reno than the books say.",
        [Change("opening", {"kind": "inventory", "item": "RW-9324", "location": "RENO"}, "add", -200)]),
    "B from A, rules only": (
        "A", "Web orders should ship only from the PDC in Columbus, which Reno restocks, with the plan deciding those "
             "transfers. Dealer and commercial orders ship straight from Reno. Building a bike now takes one week on "
             "every line.", "B"),
    "not expressible": ("B", "When the PDC runs short of a bike, let Reno ship that web order instead.", "unsupported"),
}


@pytest.mark.parametrize("name", EDIT_CASES)
def test_live_edits(name):
    start, request, expected = EDIT_CASES[name]
    case = {"A": sc.CASE_A, "B": sc.CASE_B}[start]
    p = llm.propose_edits(request, case)
    print(f"\n{name}: attempts {p.attempts}, tokens {p.usage}, errors {p.errors}")
    for w, r, e in zip(p.words, p.reasons, p.edits):
        print("  ", w, "|", r, "| why:", e.values.get("why", ""))
    print("   unsupported:", p.unsupported, "| question:", p.question)
    if expected in ("question", "unsupported"):
        assert p.edits == [] and (p.question if expected == "question" else p.unsupported)
        return
    assert p.ok, p.errors
    new = p.scenario()
    if expected == "B":
        assert priors.diff(new.priors, sc.CASE_B.priors) == [] and new.changes == ()
    else:
        assert priors.diff(new.priors, case.priors) == [] and same_edits(new.changes, expected)
