"""The planner (planner2/): Model, Scenarios, Compare, Try a change. What each view shows is checked against the
engine computed independently (held_from on the run's own flows, the scorecard, the object's numbers) and against the
acceptance numbers in the other sessions' notes; every flow is run with fakes standing in for Claude. Runs are saved
to a scratch folder."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "app")]

import ui  # noqa: E402
from planner2 import charts, facts, reading as rd, state  # noqa: E402
from redwheel import llm, priors, scenarios as sc, store, tunables as tu  # noqa: E402
from redwheel.changes import Change  # noqa: E402

APP = str(ROOT / "planner2" / "app.py")
BUILT_IN = ["A", "B", "E1", "E2", "E3", "E4", "E5", "P1"]
CASES = {k: getattr(sc, f"CASE_{k}") for k in BUILT_IN}
H, W = ui.H, ui.WEEKS


def short(k) -> str:
    return CASES[k].name.removeprefix("Scenario ")


@pytest.fixture(scope="module")
def views():
    return {k: ui.view_of(sc.run_case(c)) for k, c in CASES.items()}


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "FOLDER", tmp_path)
    return tmp_path


def date(s) -> pd.Timestamp:
    return pd.Timestamp(s)


# ---------------- one plan ----------------

def per_sku(ok) -> dict:
    """{sku: first week from which `ok` holds at every one of its positions}, from scenarios.held_from directly."""
    hf = sc.held_from(ok)
    out = {}
    for s in ui.ORDER:
        v = hf[[k for k in hf.index if k[0] == s]]
        out[s] = None if v.isna().any() else int(v.max())
    return out


@pytest.mark.parametrize("key", BUILT_IN)
def test_bike_dates_are_the_engines(views, key):
    R = views[key]["R"]
    weeks = list(range(1, H + 1))
    cleared, at = per_sku(R["flows"]["open_orders"][weeks] < 0.5), per_sku(R["at_target"][weeks])
    d = rd.bike_dates(views[key])
    for s in ui.ORDER:
        assert d[s] == (W[cleared[s]] if cleared[s] else None, W[at[s]] if at[s] else None), s


def test_acceptance_numbers(views):
    """From the solver and object sessions' notes (docs/SOLVER_NOTE_TO_DECK_AND_UI.md, NOTE_TO_STREAMLIT_BOT.md)."""
    card = {k: {label: v for label, v, *_ in rd.kpis(views[k])} for k in BUILT_IN}
    assert card["A"]["Targets held from"] == "6 Sep 2027" and card["A"]["Orders cleared"] == "14 Dec 2026"
    assert card["A"]["Bikes built"] == "94,429" and card["A"]["On-time fill"] == "96.4%"
    assert card["B"]["Orders cleared"] == "4 Jan 2027" and card["B"]["Targets held from"] == "27 Sep 2027"
    assert card["E1"]["Targets held from"] == "4 Oct 2027"
    assert card["E4"]["Targets held from"] == "13 Sep 2027" and card["E4"]["Orders cleared"] == "28 Dec 2026"
    assert card["E5"]["Orders cleared"] == "21 Dec 2026" and card["E5"]["Targets held from"] == "6 Sep 2027"
    assert card["P1"]["Plan checks"] == "10 of 10" and card["A"]["Plan checks"] == "9 of 9"
    p1 = rd.bike_dates(views["P1"])
    assert [p1[s][1] for s in ("RW-9304", "RW-4418", "RW-6416")] == [date("2027-02-22"), date("2027-07-26"),
                                                                    date("2027-09-06")]
    assert all(p1[s][0] == date("2026-12-14") for s in ("RW-9304", "RW-4418", "RW-6416"))


def test_assumptions_in_technical_shorthand(views):
    a = {k: dict(rd.assumptions(views[k])) for k in ("A", "B", "P1")}
    assert a["A"] == {"Sourcing": "pooled (Reno + PDC)", "Build lead time": "0 wk", "Transfer lead time": "1 wk",
                      "Decisions": "builds", "Priority": "even rule",
                      "Targets (weeks of supply)": "Road 8 → 10 wk (3 Jan 2028) · MTB base 12 wk · MTB carbon 15 wk"}
    assert a["B"]["Sourcing"] == "web ← PDC; dealer, commercial ← Reno" and a["B"]["Build lead time"] == "1 wk"
    assert a["B"]["Decisions"] == "builds, transfers"
    assert a["P1"]["Priority"] == "past-due > open orders > target; MTB carbon: RW-9304 > RW-4418 > RW-6416"


def test_monthly_differences_and_the_weeks_a_change_applies(views):
    for k in ("E1", "E3", "E4", "P1", "B"):
        V, V0 = views[k], views["A"]
        for ln in ui.LINES:
            d, a, b = rd.monthly_difference(V, V0, ln), rd.monthly_stack(V0, ln), rd.monthly_stack(V, ln)
            for s in d["built"]:
                assert d["built"][s] == [y - x for x, y in zip(a["built"][s], b["built"][s])]
            for key in ("demand", "capacity", "open_orders"):
                assert d[key] == [y - x for x, y in zip(a[key], b[key])]

    def weeks(k, k0="A", ln="mtb-carbon"):
        return [(W[a], W[b]) for a, b in rd.change_weeks(views[k], views[k0], ln)]
    assert weeks("E1") == [(date("2027-03-01"), date("2027-03-15"))]                    # the three weeks it is down
    assert weeks("E3") == [(date("2027-10-25"), date("2027-12-13"))]
    assert weeks("E1", ln="road-base") == [] and weeks("E1", "E1") == []                # another line; a change both have
    assert weeks("E5") == [] and weeks("B") == [] and weeks("P1") == []                 # lots, settings, priority: no period


def test_the_weekly_csv_is_the_whole_plan(views):
    for V in views.values():
        csv = pd.read_csv(pd.io.common.StringIO(rd.build_csv(V)))
        assert csv["units"].sum() == V["card"]["Bikes built"] and len(csv) == 10 * H
        assert (rd.transfer_csv(V) is None) == ("move" not in V["case"].decides)





def test_sources_are_the_objects_numbers():
    t = rd.sources(ui.obj).set_index("From")["Total"]
    assert t["plant_inventory_snapshot.csv"] == "3,000 bikes"
    assert t["dtc_web_orders, dealer_orders_export, Commercial_PO_Log"].startswith("5,991 bikes (web 2,139")
    assert t["forecast_dtc, forecast_dealer, forecast_commercial"] == "79,622 bikes over the plan"
    assert t["capacity_plan.csv"] == "123,150 bikes over the plan" and t["dealer_stock_report.csv"] == "2,000 bikes"


def test_the_scenario_chart_stacks_each_bike_and_marks_open_orders(views):
    for k in ("A", "E1", "B"):
        V = views[k]
        fig = charts.plan_figure(V)
        bars = [t for t in fig.data if t.type == "bar"]
        assert [t.hovertemplate.split(":")[0] for t in bars] == ui.ORDER                 # one bar per bike, line by line
        for i, ln in enumerate(ui.LINES):
            d = rd.monthly_stack(V, ln)
            for s, y in d["built"].items():
                bar = next(t for t in bars if t.hovertemplate.startswith(s + ":"))
                assert np.array_equal(np.array(bar.y), y)
                assert sum(y) == V["built"].loc[s].sum()
            weeks = [rd.MONTH_WEEKS[p] for p in rd.MONTHS]
            skus = ui.SKUS_BY_LINE[ln]
            assert d["open_orders"] == [float(V["open_orders"].loc[skus, max(w)].sum()) for w in weeks]
            marks = [t for t in fig.data if t.name == "open orders, month end"][i]
            assert [y for y in marks.y if y is not None] == [v for v in d["open_orders"] if v > 0.5]
        assert fig.layout.barmode == "stack"


def test_the_build_plan_table_periods_cover_each_week_once():
    cols = rd.period_tree()
    for level in "YQM":
        assert sorted(w for c in cols if c["level"] == level for w in c["weeks"]) == list(range(1, H + 1)), level
    for c in cols:
        kids = [x for x in cols if x["parent"] == c["id"]]
        if kids:
            assert sorted(w for x in kids for w in x["weeks"]) == sorted(c["weeks"]), c["id"]
    assert [c["id"] for c in cols if c["level"] == "Y"] == ["FY26", "FY27", "FY28"]
    assert [c["label"] for c in cols if c["parent"] == "FY26 Q1"] == ["Sep 26", "Oct 26", "Nov 26"]


@pytest.mark.parametrize("key", ["A", "B", "E1", "P1"])
def test_the_build_plan_table_is_the_runs_numbers(views, key):
    V = views[key]
    R = V["R"]
    d = rd.pivot_data(V)
    cols = [c for c in rd.period_tree()]
    rows = {(r["line"], r["sku"], r["metric"]): r for r in d["rows"]}
    flows = {"build": V["built"], "forecast": V["demand"], "shipped": V["shipped"]}
    levels = {"open": V["open_orders"], "net": V["net"], "on_hand": V["on_hand"] + V["transit"]}
    for s in ui.ORDER:
        ln = ui.SKU.at[s, "line_id"]
        for m, df in flows.items():
            v = rows[(ln, s, m)]["values"]
            assert v["start"] is None
            for c in cols[1:]:
                assert v[c["id"]] == df.loc[s, c["weeks"]].sum(), (m, s, c["id"])
        for m, df in levels.items():
            v = rows[(ln, s, m)]["values"]
            assert "total" not in v
            for c in cols[:-1]:
                assert v[c["id"]] == df.at[s, max(c["weeks"])], (m, s, c["id"])
        t = rows[(ln, s, "target")]["values"]
        assert t["start"] == V["target_units"].at[s, 1] and t["FY27"] == V["target_units"].at[s, max(cols[cols.index(next(c for c in cols if c["id"] == "FY27"))]["weeks"])]
        w = rows[(ln, s, "wos")]
        keys = [k for k in R["wos"].index if k[0] == s]
        for c in cols[1:-1]:
            end = max(c["weeks"])
            assert w["values"][c["id"]] == R["wos"].loc[keys, end].min()
            assert w["bad"][c["id"]] == (not bool(V["at_target"].at[s, end]))
    for ln in ui.LINES:
        skus = ui.SKUS_BY_LINE[ln]
        for m in ("build", "forecast", "shipped", "open", "target", "on_hand", "net"):
            sub = rows[(ln, None, m)]["values"]
            for cid, v in sub.items():
                parts = [rows[(ln, s, m)]["values"][cid] for s in skus]
                if v is None:                                   # a flow before the plan: blank, as are its bikes
                    assert all(x is None for x in parts), (ln, m, cid)
                else:
                    assert v == pytest.approx(sum(x or 0 for x in parts)), (ln, m, cid)
        cap, use = rows[(ln, None, "capacity")]["values"], rows[(ln, None, "use")]["values"]
        built = rows[(ln, None, "build")]["values"]
        for c in cols[1:]:
            assert cap[c["id"]] == R["obj"].arrivals.loc[f"capacity||RENO/{ln}", c["weeks"]].sum()
            assert use[c["id"]] == pytest.approx(built[c["id"]] / cap[c["id"]]) if cap[c["id"]] else use[c["id"]] is None
        at = rows[(ln, None, "at_target")]
        assert at["of"] == len(skus) and at["values"]["FY28"] == sum(bool(V["at_target"].at[s, H]) for s in skus)
    total = rows[(None, None, "build")]["values"]
    assert total["total"] == V["card"]["Bikes built"] and total["start"] is None
    assert rows[(None, None, "open")]["values"]["start"] == R["flows"]["open_orders"][0].sum()


def test_the_build_plan_table_measures_in_the_agreed_order(views):
    m = rd.pivot_data(views["A"])["metrics"]
    bike = [x["label"] for x in m if x["scope"] == "bike"]
    assert bike == ["On hand", "Forecast", "Open orders", "Build plan", "Net inventory", "Target inventory",
                    "Weeks of supply", "Shipped", "At target"]
    assert [x["label"] for x in m][:6] == ["On hand", "Forecast", "Open orders", "Build plan", "Capacity", "Utilisation"]
    assert [x["label"] for x in m if x["em"]] == ["Build plan", "Net inventory"]
    assert [x["label"] for x in m if not x["on"]] == ["Shipped", "At target"]


def test_the_build_plan_page_embeds_the_table_data(views):
    from planner2 import pivot
    import json
    data = rd.pivot_data(views["A"])
    page = pivot.html(data)
    assert json.dumps(data) in page and "__DATA__" not in page


# ---------------- comparing ----------------

def test_summary_and_assumptions_side_by_side(views):
    s = rd.summary({k: views[k] for k in ("A", "B", "P1")})
    assert list(s.columns) == ["A", "B", "P1"]
    assert s.at["Targets held from", "A"] == "6 Sep 2027" and s.at["Targets held from", "B"] == "27 Sep 2027 (+3 wk)"
    assert s.at["On-time fill", "B"] == "95.3% (-1.1 pts)" and s.at["Targets held from", "P1"] == "6 Sep 2027"
    assert s.at["At target · MTB base", "B"] == "15 Mar 2027 (+5 wk)" and s.at["Plan checks", "P1"] == "10 of 10"
    a = rd.assumptions_table({k: views[k] for k in ("A", "B")})
    assert a.at["Build lead time", "A"] == "0 wk" and a.at["Build lead time", "B"] == "1 wk"


def test_what_changed_shows_the_numbers_a_change_touched(views):
    def rows(k):
        return rd.what_changed(CASES["A"], CASES[k], views[k]).to_dict("records")
    assert rows("E1") == [{"Change": "Line capacity", "What": "MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027",
                           "From": "1,125 bikes", "To": "0 bikes", "Numbers": "3"}]
    assert [(r["Change"], r["Numbers"]) for r in rows("E3")] == [("Build limit", "8")]
    assert [(r["From"], r["To"], r["Numbers"]) for r in rows("E4")] == [("7 bikes", "307 bikes", "1")]
    assert [(r["Change"], r["Numbers"]) for r in rows("E5")] == [("Lot size", "121")]
    assert rd.what_changed(CASES["A"], CASES["A"], views["A"]).empty
    b = rd.grouped_changes(rd.what_changed(CASES["A"], CASES["B"], views["B"]))
    assert [(r["Change"], r["What"], r["To"]) for r in b] == [
        ("Ship from", "Web orders", "PDC"), ("Ship from", "Dealer orders, Commercial orders", "Reno"),
        ("Build time", "Road base, Road carbon, MTB base, MTB carbon", "1 week"),
        ("Plan transfers", "Reno to the PDC", "yes")]


def test_only_the_lines_that_moved_are_drawn(views):
    assert rd.lines_changed(views["E1"], views["A"]) == ["mtb-carbon"]
    assert rd.lines_changed(views["E3"], views["A"]) == ["mtb-carbon"]
    assert rd.lines_changed(views["B"], views["A"]) == ui.LINES
    assert rd.lines_changed(views["A"], views["A"]) == []
    more = Change("arrival", {"kind": "capacity", "location": "RENO/road-base"}, "scale", 1.2, 80, 90, "t")
    V = ui.view_of(sc.run_case(sc.Case("T", "T", sc.CASE_A.priors, "", "A", (more,))))
    assert rd.lines_changed(V, views["A"]) == ["road-base"] and rd.same_plan(V, views["A"])   # capacity alone moved
    p1 = rd.bike_dates(views["P1"])
    assert p1["RW-9304"][1] == date("2027-02-22") and rd.bike_dates(views["A"])["RW-9304"][1] == date("2027-09-06")
    assert rd.same_plan(views["A"], views["A"]) and not rd.same_plan(views["E3"], views["A"])





def test_the_periods_cover_each_week_once_and_the_bars_are_each_plans_builds(views):
    for level, n in (("Quarter", 10), ("Month", 28)):
        per = rd.compare_periods(level)
        assert len(per) == n and sorted(t for _, w in per for t in w) == list(range(1, H + 1))
    assert [p for p, _ in rd.compare_periods("Quarter")][:3] == ["FY26 Q1", "FY26 Q2", "FY26 Q3"]   # FY from September
    E1, A = views["E1"], views["A"]
    fig = charts.side_by_side_figure(E1, A, ["mtb-carbon"], "Quarter")
    assert [a.text for a in fig.layout.annotations] == ["<b>MTB carbon</b> · at target 4 Oct 2027 (+4 wk vs A)"]
    for grp, V in (("A", A), ("E1", E1)):
        bars = [t for t in fig.data if t.type == "bar" and t.offsetgroup == grp]
        want = rd.built_by_period(V, "mtb-carbon", "Quarter")
        assert [t.hovertemplate.split(" · ")[1].split(":")[0] for t in bars] == list(want)
        base = np.zeros(10)
        for t, (s_, y) in zip(bars, want.items()):                                   # stacked: each bike on the last
            assert np.allclose(t.y, y) and np.allclose(t.base if t.base is not None else 0, base)
            assert np.isclose(sum(y), E1["built"].loc[s_].sum() if grp == "E1" else A["built"].loc[s_].sum())
            base = base + np.array(y)
        assert {t.opacity for t in bars} == {0.35 if grp == "A" else 1.0}
    text = [t for t in fig.data if t.type == "scatter"][0]
    assert list(text.x) == ["FY26 Q3", "FY27 Q1"] and list(text.text) == ["−1,125", "+1,125"]  # down three weeks, made up
    month = charts.side_by_side_figure(E1, A, ["mtb-carbon"], "Month")
    assert len(month.data[0].x) == 28 and list(month.layout.xaxis.tickvals) == list(month.data[0].x)[::3]
    four = charts.side_by_side_figure(views["B"], A, ui.LINES, "Quarter")
    dom = [four.layout[f"yaxis{i if i > 1 else ''}"].domain for i in range(1, 5)]
    assert len(four.layout.annotations) == 4 and np.allclose([d[1] - d[0] for d in dom], dom[0][1] - dom[0][0])
    assert four.layout.height == 4 * 210 + 3 * 78 + 92
    m = four.layout.margin
    assert all((d[1] - d[0]) * (four.layout.height - m.t - m.b) >= 200 for d in dom)   # no panel squashed (px)


@pytest.mark.parametrize("key", ["B", "E1", "E3", "E4", "P1"])
def test_labels_mark_every_material_difference_and_nothing_else(views, key):
    V, V0 = views[key], views["A"]
    for ln in rd.lines_changed(V, V0):
        for level in ("Quarter", "Month"):
            per = rd.compare_periods(level)
            a = [V0["built"].loc[ui.SKUS_BY_LINE[ln], w].to_numpy().sum() for _, w in per]
            b = [V["built"].loc[ui.SKUS_BY_LINE[ln], w].to_numpy().sum() for _, w in per]
            cut = max(rd.LABEL_MIN, rd.LABEL_SHARE * max(a))
            want = [(p, y - x, max(x, y)) for (p, _), x, y in zip(per, a, b) if abs(y - x) >= cut]
            got = rd.period_labels(V, V0, ln, level)
            assert [p for p, _, _ in got] == [p for p, _, _ in want]
            assert np.allclose([d for _, d, _ in got], [d for _, d, _ in want])
            assert np.allclose([t for _, _, t in got], [t for _, _, t in want])
    assert rd.period_labels(views["P1"], V0, "mtb-carbon", "Month") == []                # a re-mix: same line totals


def test_ahead_or_behind_is_the_cumulative_difference(views):
    A = views["A"]
    for k in ("E1", "E3", "P1", "B"):
        V = views[k]
        for ln in rd.lines_changed(V, A):
            d = rd.ahead_behind(V, A, ln)
            for s in ui.SKUS_BY_LINE[ln]:
                assert np.allclose(d[s], np.cumsum(V["built"].loc[s].to_numpy() - A["built"].loc[s].to_numpy()))
            assert np.allclose(d["line"], sum(d[s] for s in ui.SKUS_BY_LINE[ln]))
            assert abs(d["line"][-1]) < 0.5                                             # the same bikes built in the end
    e1 = rd.ahead_behind(views["E1"], A, "mtb-carbon")["line"]
    assert e1.min() == -1125 and W[int(np.argmin(e1)) + 1] == date("2027-03-15")       # behind by the three lost weeks
    p1 = rd.ahead_behind(views["P1"], A, "mtb-carbon")
    assert np.abs(p1["line"]).max() < 0.5 and p1["RW-9304"].max() == 1127               # RW-9304 first, same line total
    fig = charts.ahead_figure(views["E1"], A, ["mtb-carbon"])
    line = [t for t in fig.data if t.name == "line total"][0]
    assert np.allclose(line.y, e1) and list(line.x) == list(W)
    rects = [s_ for s_ in fig.layout.shapes if s_.type == "rect"]
    assert len(rects) == 1 and pd.Timestamp(rects[0].x0) == date("2027-03-01")
    assert pd.Timestamp(rects[0].x1) == date("2027-03-22")                             # through the week of 15 Mar
    assert [t.name for t in fig.data if t.type == "bar"] == ["weeks changed"]
    four = charts.ahead_figure(views["B"], A, ui.LINES)
    assert not [s_ for s_ in four.layout.shapes if s_.type == "rect"] and not [t for t in four.data if t.type == "bar"]
    ids = {"yaxis": "y", "yaxis2": "y2", "yaxis3": "y3", "yaxis4": "y4"}
    assert len({four.layout[a].matches or i for a, i in ids.items()}) == 1               # one scale for every line
    assert len(four.layout.annotations) == 4 and four.layout.height == 2 * 220 + 64 + 92   # two by two


@pytest.mark.parametrize("key", ["E1", "E3", "P1", "B"])
def test_the_difference_table_is_b_minus_a_cell_by_cell(views, key):
    V, V0 = views[key], views["A"]
    c = rd.pivot_compare(V, V0)
    a = {(r["line"], r["sku"], r["metric"]): r for r in rd.pivot_data(V0)["rows"]}
    b = {(r["line"], r["sku"], r["metric"]): r for r in rd.pivot_data(V)["rows"]}
    for r in c["rows"]:
        k = (r["line"], r["sku"], r["metric"])
        for cid, v in r["values"].items():
            x, y = a[k]["values"].get(cid), b[k]["values"].get(cid)
            assert v == (None if x is None and y is None else (y or 0) - (x or 0)), (k, cid)
        assert r["changed"] == any(v is not None and abs(v) > 1e-9 for v in r["values"].values())
    assert c["labels"] == {"diff": f"{key} − A", "a": "A", "b": key}
    assert [m["key"] for m in c["metrics"] if m["on"]] == ["open", "build", "capacity", "net", "wos"]
    changed = {(r["line"], r["sku"]) for r in c["rows"] if r["changed"] and r["sku"]}
    if key == "E3":
        assert changed == {("mtb-carbon", "RW-4418")}                                  # only the late bike moves
    if key == "E1":
        assert {ln for ln, _ in changed} == {"mtb-carbon"}





def test_headline_changes_carry_their_tone(views):
    def tones(k):
        return {lab: (d, tone) for lab, _, d, tone, _ in rd.kpis(views[k], views["A"])}
    assert tones("E1")["Targets held from"] == ("+4 wk vs A", "bad") and tones("E1")["Bikes built"] == ("same as A", "same")
    assert tones("P1")["Targets held from"] == ("same as A", "same")
    assert tones("B")["On-time fill"][1] == "bad" and tones("B")["Orders cleared"] == ("+3 wk vs A", "bad")
    assert tones("E2")["Bikes built"] == ("+191 vs A", "neutral")


def test_the_facts_for_ask_hold_changes_priority_and_bike_dates(views):
    f = facts.facts([("A", CASES["A"], views["A"]), ("P1", CASES["P1"], views["P1"])])
    assert "Bike RW-9304: open orders cleared from 14 Dec 2026; at target from 22 Feb 2027" in f
    assert "Priority order: 1. Orders past their date" in f and "WHAT P1 SETS DIFFERENTLY FROM A: Priority order" in f
    f = facts.facts([("E1", CASES["E1"], views["E1"])])
    assert "MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027: down (none) (3 numbers, 1,125 bikes -> 0 bikes)" in f


# ---------------- the app ----------------

def start(page=None):
    at = AppTest.from_file(APP, default_timeout=400).run()
    if page:
        at.switch_page(page).run()
    return ok(at)


def ok(at):
    assert not at.exception, [e.message for e in at.exception]
    return at


def md(at, text) -> bool:
    return any(text in m.value for m in at.markdown)


def test_the_four_views_render(folder):
    at = start()
    assert at.title[0].value == "Model"
    at.switch_page("scenarios.py").run()
    assert ok(at).title[0].value == "Scenarios" and [t.label for t in at.tabs] == [short(k) for k in state.FEATURED]
    assert sum("rw-strip" in m.value for m in at.markdown) == len(state.FEATURED)        # the template, once each
    assert md(at, "pooled (Reno + PDC)") and md(at, "web ← PDC; dealer, commercial ← Reno")
    assert not any("rw-cards" in m.value for m in at.markdown)                           # no measure cards
    at.switch_page("compare.py").run()
    assert ok(at).title[0].value == "Compare" and md(at, "+3 wk vs A")
    at.switch_page("whatif.py").run()
    assert ok(at).title[0].value == "Try a change" and at.radio(key="_run").value == "E1" and md(at, "+4 wk vs A")


def test_compare_any_pair(folder):
    at = start("compare.py")
    at.selectbox(key="_k").set_value("P1").run()
    assert ok(at) and md(at, "Priority order") and md(at, "RW-9304, then RW-4418, then RW-6416 (target)")
    at.selectbox(key="_k").set_value("A").run()
    assert any("Pick two different scenarios" in c.value for c in at.caption)


def test_every_example_reads_against_a(folder):
    import json
    at = start("whatif.py")
    for k in state.EXAMPLES:
        at.radio(key="_run").set_value(k).run()
        ok(at)
        assert at.subheader[0].value == f"{short(k)}, against A"
    at.radio(key="_run").set_value("E1").run()
    side, ahead = (json.loads(c.proto.spec) for c in at.get("plotly_chart")[:2])
    assert [a["text"] for a in side["layout"]["annotations"]] == \
        ["<b>MTB carbon</b> · at target 4 Oct 2027 (+4 wk vs A)"]                         # only the line that moved
    assert [a["text"] for a in ahead["layout"]["annotations"]] == ["<b>MTB carbon</b>"]
    assert md(at, "**Builds: A (faded) and E1** · same as A: Road base, Road carbon, MTB base")
    assert len(side["data"][0]["x"]) == 10
    at.radio(key="lvl_tc_A_E1").set_value("Month").run()
    assert len(json.loads(ok(at).get("plotly_chart")[0].proto.spec)["data"][0]["x"]) == 28


def test_a_change_by_form_runs_and_reads_against_its_start(folder):
    at = start("whatif.py")
    assert at.selectbox(key="tc_tunable").value == "line_capacity"          # its defaults are E1
    at.button(key="tc_run").click().run()
    ok(at)
    new = at.radio(key="_run").value
    assert new not in BUILT_IN and (folder / f"{new}.json").exists() and md(at, "+4 wk vs A")
    assert tu.same_changes(store.load_all(folder)[new].changes, CASES["E1"].changes)
    at.button(key="tc_remove").click().run()
    assert ok(at) and not (folder / f"{new}.json").exists() and new not in at.radio(key="_run").options


def test_a_change_from_b_reads_against_b(folder):
    at = start("whatif.py")
    at.selectbox(key="tc_base").set_value("B").run()
    at.button(key="tc_run").click().run()
    ok(at)
    assert at.subheader[0].value.endswith("against B") and md(at, "vs B")


def test_a_change_that_alters_nothing_cannot_run(folder):
    at = start("whatif.py")
    at.number_input(key="tc_line_capacity_percent").set_value(100).run()
    assert at.button(key="tc_run").disabled and any("change nothing" in c.value for c in at.caption)


def test_a_change_in_words_runs_only_after_checked(folder, monkeypatch):
    seen = []

    def fake(request, case, client=None):
        seen.append((request, case.key))
        return llm.EditProposal(request=request, case=case, edits=[tu.make("extra_order")], reasons=[request])
    monkeypatch.setattr(llm, "propose_edits", fake)
    at = start("whatif.py")
    at.text_input(key="tc_req").input("A fleet order of 300 RW-4418 lands in November").run()
    at.button(key="tc_propose").click().run()
    assert seen == [("A fleet order of 300 RW-4418 lands in November", "A")] and md(at, "+300 bikes")
    at.button(key="tc_prop_run").click().run()
    ok(at)
    assert at.radio(key="_run").value not in BUILT_IN and md(at, "+300 vs A")


def test_claude_asking_back_or_failing_changes_nothing(folder, monkeypatch):
    monkeypatch.setattr(llm, "propose_edits", lambda r, c, client=None: llm.EditProposal(
        request=r, case=c, question="Which line is down?", unsupported=["a rule that depends on the weather"]))
    at = start("whatif.py")
    at.text_input(key="tc_req").input("A line is down").run()
    at.button(key="tc_propose").click().run()
    assert any(i.value == "Which line is down?" for i in at.info) and not any(b.key == "tc_prop_run" for b in at.button)
    assert any("a rule that depends on the weather" in c.value for c in at.caption)

    def down(*a, **k):
        raise ConnectionError("no network")
    monkeypatch.setattr(llm, "propose_edits", down)
    at.button(key="tc_propose").click().run()
    assert not at.exception and any("did not go through" in w.value for w in at.warning)


def test_ask_answers_from_the_pair_on_screen(folder, monkeypatch):
    seen = []
    monkeypatch.setattr(llm, "explain", lambda q, f, client=None: seen.append((q, f)) or {"answer": "Lead time."})
    at = start("compare.py")
    at.button(key="ask_A_B_ex0").click().run()
    at.button(key="ask_A_B_go").click().run()
    assert seen[0][0] == "Why does B differ from A?" and "SCENARIO B" in seen[0][1] and md(at, "Lead time.")


def test_a_saved_priority_order_runs_with_it(folder):
    store.save(sc.Case("C", "Scenario C · P1 saved", CASES["P1"].priors, "", "A", (), CASES["P1"].walk), folder)
    at = start("whatif.py")
    at.radio(key="_run").set_value("C").run()
    assert ok(at) and md(at, "RW-9304, then RW-4418, then RW-6416 (target)")
    from planner2 import state as st_
    assert rd.bike_dates(st_._run("C", "C", "", "A", priors.normalise(CASES["P1"].priors).to_csv(index=False), "[]",
                                  st_.walk_text(CASES["P1"].walk)))["RW-9304"][1] == date("2027-02-22")


def test_a_saved_run_that_cannot_be_planned_does_not_break_the_app(folder):
    bad = priors.apply_changes(CASES["A"].priors, [{"prior": "decides", "applies_to": "make", "new": "no"}])
    store.save(sc.Case("C", "Scenario C · broken", bad, "edited by hand", "A"), folder)
    at = start("whatif.py")
    at.radio(key="_run").set_value("C").run()
    assert not at.exception and any("Cannot be planned" in e.value for e in at.error)
