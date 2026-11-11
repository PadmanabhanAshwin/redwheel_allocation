"""LLM proposals, offline: a fake model stands in for the API, so these test the loop, not the model."""
import json
from types import SimpleNamespace

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
