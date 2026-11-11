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
