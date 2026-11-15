"""LLM proposals, offline: a fake model stands in for the API, so these test the loop, not the model."""
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from redwheel import llm, priors, scenarios as sc


def change(prior, applies_to, value, from_date="", action="set"):
    return {"prior": prior, "applies_to": applies_to, "from_date": from_date, "action": action, "value": value,
            "reason": "test"}


A_TO_B = [change("route", "RENO>WEB", "no"), change("route", "CMH>DEALERS", "no"),
          change("route", "CMH>COMMERCIAL", "no"), change("decides", "move", "yes")] + \
         [change("build_weeks", ln, "1") for ln in ("road-base", "road-carbon", "mtb-base", "mtb-carbon")]


class FakeClient:
    """Returns the given answers in order and records every request."""
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        a = self.answers.pop(0)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(a))],
                               usage=SimpleNamespace(input_tokens=100, output_tokens=50))


def answer(changes=(), unsupported=(), question=""):
    return {"changes": list(changes), "unsupported": list(unsupported), "question": question}


def test_a_valid_answer_becomes_a_checked_proposal(obj):
    p = llm.propose("describe B", sc.CASE_A.priors, obj, FakeClient(answer(A_TO_B)))
    assert p.ok and p.attempts == 1 and p.errors == []
    assert priors.diff(p.table, sc.CASE_B.priors) == []                   # exactly scenario B
    assert {(c["prior"], c["applies_to"], c["old"], c["new"]) for c in p.changes} == \
        {(c["prior"], c["applies_to"], c["old"], c["new"]) for c in priors.diff(sc.CASE_A.priors, sc.CASE_B.priors)}


def test_a_failed_check_goes_back_once_and_can_be_corrected(obj):
    bad = [change("decides", "move", "yes")]                               # transfers inside one pool: refused
    client = FakeClient(answer(bad), answer(A_TO_B))
    p = llm.propose("describe B", sc.CASE_A.priors, obj, client)
    assert p.ok and p.attempts == 2
    retry = client.calls[1]["messages"][-1]["content"]
    assert "fails these checks" in retry and "same orders" in retry


def test_it_stops_after_the_second_failure_and_reports_the_errors(obj):
    bad = [change("decides", "move", "yes")]
    p = llm.propose("x", sc.CASE_A.priors, obj, FakeClient(answer(bad), answer(bad)))
    assert not p.ok and p.attempts == 2 and any("same orders" in e for e in p.errors)


def test_unsupported_or_unclear_requests_propose_nothing(obj):
    p = llm.propose("ship from Reno only when the PDC is short", sc.CASE_B.priors, obj,
                    FakeClient(answer(unsupported=["conditional shipping from Reno"])))
    assert not p.ok and p.changes == [] and p.table is None and p.unsupported
    p = llm.propose("make it better", sc.CASE_B.priors, obj, FakeClient(answer(question="Better how?")))
    assert not p.ok and p.question == "Better how?"


def test_names_in_the_schema_come_from_the_network(obj):
    s = llm.schema(obj)["properties"]["changes"]["items"]["properties"]
    assert set(s["prior"]["enum"]) == set(priors.MEANING)
    assert {"RENO>WEB", "CMH>COMMERCIAL", "mtb-carbon", "RENO>CMH", "mtb_base", "move"} <= set(s["applies_to"]["enum"])


def test_no_order_or_sku_data_goes_to_the_model(obj, m):
    client = FakeClient(answer(question="?"))
    llm.propose("describe B", sc.CASE_A.priors, obj, client)
    sent = client.calls[0]["system"] + json.dumps(client.calls[0]["messages"])
    assert not any(s in sent for s in m["dim_sku"]["sku"])                 # no SKU ids
    assert not any(str(o) in sent for o in m["fact_orders"]["order_id"].head(50))


# ---------------- explain: answers about computed results ----------------

class TextClient(FakeClient):
    def _create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=self.answers.pop(0))],
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5))


def test_explain_sends_only_the_facts_and_the_question():
    client = TextClient("B holds targets three weeks later.")
    out = llm.explain("Why is B later?", "FACT: A held 6 Sep 2027; B held 27 Sep 2027.", client)
    assert out["answer"] == "B holds targets three weeks later."
    sent = client.calls[0]
    assert "FACT: A held 6 Sep 2027" in sent["messages"][0]["content"] and "Why is B later?" in sent["messages"][0]["content"]
    assert "Use only those facts" in sent["system"]


# ---------------- any tunable: a request -> checked edits ----------------

from redwheel import tunables as tu                                                     # noqa: E402
from redwheel.changes import Change                                                     # noqa: E402

def edit(tunable, reason="test", **fields):
    """An edit as the model writes it: the tunable, its fields as name/value text pairs, and a reason."""
    return {"tunable": tunable, "fields": [{"name": k, "value": str(v)} for k, v in fields.items()], "reason": reason}


LINE_DOWN = edit("line_capacity", "MTB carbon line down for three weeks", line="mtb-carbon", first="2027-03-01", weeks=3,
                 percent=0, why="maintenance")


def edits_answer(edits=(), unsupported=(), question=""):
    return {"edits": list(edits), "unsupported": list(unsupported), "question": question}


def test_a_line_down_request_becomes_a_checked_edit():
    client = FakeClient(edits_answer([LINE_DOWN]))
    p = llm.propose_edits("The MTB carbon line is down for maintenance for three weeks from 1 March 2027.", sc.CASE_A, client)
    assert p.ok and p.attempts == 1 and p.errors == []
    assert p.edits[0].change == replace(sc.CASE_E1.changes[0], reason="maintenance")
    assert p.words == ["MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027 · down (none)"]
    assert p.reasons == ["MTB carbon line down for three weeks"]
    assert p.scenario(key="X").changes == (p.edits[0].change,)
    call = client.calls[0]
    assert call["output_config"]["format"]["schema"] == llm.edits_schema() and call["thinking"] == {"type": "adaptive"}
    assert call["system"] == llm.EDITS_SYSTEM
    assert call["messages"][0]["content"] == llm.scenario_text(sc.CASE_A) + "\n\nRequest: " + \
        "The MTB carbon line is down for maintenance for three weeks from 1 March 2027."


def test_rules_and_data_together_and_the_rules_rebuild_b():
    rules = [edit("ship_from", channel="WEB", site="PDC"), edit("ship_from", channel="DEALERS", site="Reno"),
             edit("ship_from", channel="COMMERCIAL", site="Reno"), edit("plan_transfers", decide="yes")] + \
            [edit("build_time", line=ln, weeks=1) for ln in ("road-base", "road-carbon", "mtb-base", "mtb-carbon")]
    p = llm.propose_edits("describe B, with the MTB carbon line down", sc.CASE_A, FakeClient(edits_answer(rules + [LINE_DOWN])))
    assert p.ok, p.errors
    new = p.scenario()
    assert priors.diff(new.priors, sc.CASE_B.priors) == [] and len(new.changes) == 1


def test_edits_that_fail_a_check_go_back_once_with_the_reasons():
    past = edit("line_capacity", line="mtb-carbon", first="2028-12-18", weeks=3, percent=0)     # weeks 120-122
    still_wrong = edit("line_capacity", line="mtb-carbon", first="2027-03-01", weeks=3, percent=100)   # changes nothing
    client = FakeClient(edits_answer([past]), edits_answer([LINE_DOWN]))
    p = llm.propose_edits("line down", sc.CASE_A, client)
    assert p.ok and p.attempts == 2
    back = client.calls[1]["messages"][-1]["content"]
    assert "weeks after the plan (122–156) can change only on order resources" in back
    assert client.calls[1]["messages"][-2] == {"role": "assistant", "content": json.dumps(edits_answer([past]))}
    client = FakeClient(edits_answer([still_wrong]), edits_answer([past]))
    p = llm.propose_edits("line down", sc.CASE_A, client)
    assert not p.ok and p.attempts == 2 and "can change only on order resources" in p.errors[0]
    assert "Capacity (% of normal): 100 would change nothing" in client.calls[1]["messages"][-1]["content"]


def test_a_limit_the_plan_cannot_use_goes_back():
    limit = edit("transfer_limit", skus="all", first="2026-11-09", weeks=4, most=20)
    p = llm.propose_edits("cap transfers at 20 a week", sc.CASE_A, FakeClient(edits_answer([limit]), edits_answer([limit])))
    assert not p.ok and "plans no transfers" in p.errors[0]
    assert llm.propose_edits("cap transfers at 20 a week", sc.CASE_B, FakeClient(edits_answer([limit]))).ok


def test_an_unclear_or_unsupported_request_proposes_nothing():
    p = llm.propose_edits("A line is down for the next two weeks.", sc.CASE_A,
                          FakeClient(edits_answer(question="Which line is down?")))
    assert not p.ok and p.edits == [] and p.question == "Which line is down?" and p.errors == []
    p = llm.propose_edits("Ship web from Reno when the PDC is short.", sc.CASE_B,
                          FakeClient(edits_answer(unsupported=["a rule that depends on stock"])))
    assert not p.ok and p.edits == [] and p.unsupported == ["a rule that depends on stock"]
    with pytest.raises(ValueError):
        p.scenario()


def test_the_edits_schema_is_small_strict_and_names_only_real_tunables_and_fields():
    s = llm.edits_schema()
    e = s["properties"]["edits"]["items"]
    assert e["properties"]["tunable"]["enum"] == list(tu.TUNABLES)
    assert set(e["properties"]["fields"]["items"]["properties"]["name"]["enum"]) == \
        {f.key for t in tu.TUNABLES.values() for f in t.fields}
    def strict(node):                                    # every object: additionalProperties false, all fields required
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False and set(node["required"]) == set(node["properties"])
            for v in node.values():
                strict(v)
        elif isinstance(node, list):
            for v in node:
                strict(v)
    strict(s)
    text = json.dumps(s)
    assert not any(k in text for k in ('"minimum"', '"maximum"', '"minLength"', '"maxLength"', '"multipleOf"', "anyOf"))
    assert len(text) < 2000                              # one form per tunable as anyOf was refused as too large


def test_the_instructions_carry_every_form_and_the_catalogue():
    sys_ = llm.EDITS_SYSTEM
    for t in tu.TUNABLES.values():
        assert f"- {t.key} ({t.name};" in sys_
        for f in t.fields:
            assert f"    {f.key}: " in sys_
    assert "RW-4418 (MTB carbon, size M)" in sys_ and "RW-9901 (MTB base, size L)" in sys_
    assert "percent: a whole number from 0 to 200, not 100." in sys_
    assert "line: one of road-base (Road base line), road-carbon (Road carbon line)" in sys_
    assert "sku: a SKU id from the catalogue." in sys_


def test_a_field_left_out_is_never_filled_by_a_default():
    """'Slow the line to half' with percent left out must not become 0% (the default): it goes back as missing."""
    no_percent = edit("line_capacity", line="mtb-carbon", first="2027-03-01", weeks=3)
    client = FakeClient(edits_answer([no_percent]), edits_answer([no_percent]))
    p = llm.propose_edits("slow the MTB carbon line to half for three weeks from 1 March 2027", sc.CASE_A, client)
    assert not p.ok and p.errors == ["edit 1: Line capacity: missing field(s) ['percent']"]
    assert "missing field(s) ['percent']" in client.calls[1]["messages"][-1]["content"]
    bad = [edit("line_capacity", line="mtb-carbon", first="2027-03-01", weeks=3, percent=0, colour="red"),
           edit("line_capacity", line="mtb-carbon", first="2027-03-01", weeks="three", percent=0)]
    p = llm.propose_edits("x", sc.CASE_A, FakeClient(edits_answer(bad), edits_answer(bad)))
    assert p.errors[0].startswith("edit 1: Line capacity: no field(s) ['colour']")
    assert "Weeks: a number is needed" in p.errors[1]
    p = llm.propose_edits("x", sc.CASE_A, FakeClient(edits_answer([edit("stock", sku="RW-9324", site="RENO", bikes=-200)])))
    assert p.ok and p.edits[0].values["why"] == ""                    # `why` may be left out
    twice = {"tunable": "stock", "reason": "x", "fields": [{"name": "sku", "value": "RW-9324"}, {"name": "site", "value": "RENO"},
                                                         {"name": "bikes", "value": "-200"}, {"name": "bikes", "value": "-300"}]}
    p = llm.propose_edits("x", sc.CASE_A, FakeClient(edits_answer([twice]), edits_answer([twice])))
    assert p.errors == ["edit 1: Stock count: field bikes given twice"]


def test_what_the_model_sees_is_the_scenario_in_words_and_no_data(m):
    """Settings and changes in words, the tunables and the catalogue; no order ids and no stock or forecast numbers."""
    client = FakeClient(edits_answer(question="?"))
    llm.propose_edits("anything", sc.CASE_E1, client)
    sent = client.calls[0]["system"] + json.dumps(client.calls[0]["messages"]) + json.dumps(client.calls[0]["output_config"])
    assert not any(str(o) in sent for o in m["fact_orders"]["order_id"].head(50))
    assert "1,250" not in sent and "1250" not in sent                   # RW-9324's stock at Reno
    assert llm.scenario_text(sc.CASE_E1) == (
        "Scenario: Scenario E1 · MTB carbon line down three weeks\n"
        "Settings: Web orders ship from Either site; Dealer orders ship from Either site; Commercial orders ship from "
        "Either site; plan transfers: no; build time: Road base same week, Road carbon same week, MTB base same week, "
        "MTB carbon same week; transfer time Reno to the PDC: 1 week; targets: Road 8 weeks, then 10 weeks from "
        "2028-01-03; MTB base 12 weeks; MTB carbon 15 weeks.\n"
        "Changes already in this scenario: (1) MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027 · down (none).\n"
        "Priority order in this scenario: none (a line that is short keeps its bikes equally short; order dates are "
        "not considered).")
    assert llm.scenario_text(sc.CASE_P1).split("\n")[-1] == (
        "Priority order in this scenario: 1. Orders past their date · every bike · shared evenly 2. All open orders · "
        "every bike · shared evenly 3. Target · MTB carbon line · in order: RW-9304, then RW-4418, then RW-6416 "
        "4. Target · MTB base, Road base and Road carbon lines · shared evenly An order with no date is due 7 days "
        "after it was placed.")


# ---------------- a priority order from a sentence ----------------

PRIORITY = edit("priority", "RW-9304 first, then RW-4418, then RW-6416", line="mtb-carbon",
                order="RW-9304, RW-4418, RW-6416", decides="target")


def test_a_priority_request_becomes_the_built_in_scenario():
    client = FakeClient(edits_answer([PRIORITY]))
    p = llm.propose_edits("On the MTB carbon line build RW-9304 to target first, then RW-4418, then RW-6416.", sc.CASE_A, client)
    assert p.ok and p.attempts == 1
    assert p.words == ["Priority order · MTB carbon · RW-9304, then RW-4418, then RW-6416 (target)"]
    assert p.scenario(key="X").walk == sc.CASE_P1.walk
    assert "priority" in client.calls[0]["output_config"]["format"]["schema"]["properties"]["edits"]["items"][
        "properties"]["tunable"]["enum"]
    system = client.calls[0]["system"]
    assert "- priority (Priority order; what comes first when a line is short: steps)" in system
    assert "order: text. SKU ids of that line separated by commas" in system and "invent an order" in system


def test_a_priority_answer_that_is_wrong_goes_back_with_the_reason():
    wrong_line = edit("priority", line="mtb-carbon", order="RW-9835, RW-9304", decides="target")
    client = FakeClient(edits_answer([wrong_line]), edits_answer([PRIORITY]))
    p = llm.propose_edits("RW-9304 first on MTB carbon", sc.CASE_A, client)
    assert p.ok and p.attempts == 2
    assert "RW-9835 is not on the MTB carbon line" in client.calls[1]["messages"][-1]["content"]
    missing = edit("priority", line="mtb-carbon", order="RW-9304")                # `decides` not given: no default
    p = llm.propose_edits("RW-9304 first", sc.CASE_A, FakeClient(*[edits_answer([missing])] * llm.MAX_ATTEMPTS))
    assert not p.ok and "missing field(s) ['decides']" in p.errors[0]
    again = llm.propose_edits("the same order", sc.CASE_P1, FakeClient(*[edits_answer([PRIORITY])] * llm.MAX_ATTEMPTS))
    assert not again.ok and "it would change nothing (that is already the priority order)" in again.errors[0]
