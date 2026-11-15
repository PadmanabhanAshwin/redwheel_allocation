"""The planner's Plan view (planner3/): every number it shows, checked against the engine computed independently
(builds and capacity summed from the run and the object, held_by_line, the scorecard, the first UI's plan grid, the
balance identity), the acceptance numbers of scenarios A, B, E1 and E2, and every flow on the page."""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "app")]

import ui  # noqa: E402
from planner3 import charts, reading as rd  # noqa: E402
from redwheel import priors, scenarios as sc, store  # noqa: E402
from redwheel.changes import Change  # noqa: E402

APP = str(ROOT / "planner3" / "app.py")
CASES = {**sc.CASES, **sc.EVENTS}
LINES = ui.LINES
H = ui.H
MONTH = ui.WEEKS.dt.to_period("M")
MONTHS = list(dict.fromkeys(MONTH))


@pytest.fixture(scope="module")
def views():
    return {k: ui.view_of(sc.run_case(c)) for k, c in CASES.items()}


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "FOLDER", tmp_path)
    return tmp_path


def num(text) -> float:
    return float(re.sub(r"[^\d.\-]", "", str(text).replace("−", "-")))


# ---------------- independent recomputation from the engine's run ----------------

def line_built(R, ln) -> np.ndarray:
    """Bikes started on a line each week, summed from the make tasks (weeks 1..H)."""
    b = R["builds"]
    return b[b.index.str.endswith(f"RENO/{ln}")].sum().to_numpy(float)


def line_capacity(R, ln) -> np.ndarray:
    return R["obj"].arrivals.loc[f"capacity||RENO/{ln}", 1:H].to_numpy(float)


def full_mask(R, ln) -> np.ndarray:
    return line_built(R, ln) >= line_capacity(R, ln) - 0.5


def held_by_line(R) -> dict:
    return {ln: pd.Timestamp(v) for ln, v in sc.held_by_line(R).max(axis=1).items()}


def sku_built(R, s) -> pd.Series:
    b = R["builds"]
    return b[b.index.str.split("|").str[1] == s].sum()


def month_weeks(p) -> list:
    return [int(t) for t in MONTH.index[MONTH == p]]


# ---------------- the answer: sentence, headline numbers ----------------

@pytest.mark.parametrize("key, parts", [
    ("A", ["from <b>6 Sep 2027</b>", "<b>MTB carbon</b>", "to w/c 30 Aug 2027",
           "capacity rises from 375 to 580 a week on 6 Sep 2027"]),
    ("B", ["from <b>27 Sep 2027</b>", "<b>MTB carbon</b>", "to w/c 13 Sep 2027", "up to 2 weeks to reach stock"]),
    ("E1", ["from <b>4 Oct 2027</b>", "<b>MTB carbon</b>", "to w/c 27 Sep 2027", "no capacity at all in 3 of those"]),
    ("E2", ["from <b>13 Sep 2027</b>", "<b>MTB carbon</b>", "to w/c 6 Sep 2027"]),
])
def test_the_sentence_names_the_date_and_what_sets_it(views, key, parts):
    s = rd.verdict(views[key])
    for p in parts:
        assert p in s, (p, s)
    if key != "A":
        assert "capacity rises" not in s                 # only said when the rise ends the line's full run


def test_the_sentence_matches_the_engine(views):
    for k, V in views.items():
        R = V["R"]
        held = held_by_line(R)
        last = max(held, key=held.get)
        assert pd.Timestamp(V["card"]["All targets held from"]) == held[last]
        streak = int(np.cumprod(full_mask(R, last)).sum())
        assert f"<b>{rd.LINE_WORDS[last]}</b>" in rd.verdict(V)
        assert f"to w/c {rd.fdate(ui.WEEKS[streak])}" in rd.verdict(V), k
        cap = line_capacity(R, last)
        assert (int((cap[:streak] == 0).sum()) > 0) == ("no capacity at all" in rd.verdict(V))


def test_a_capacity_fall_after_a_full_run_is_not_called_a_rise():
    """Road base runs full in weeks 1-8 of A; capacity cut to 140 in week 9 (it builds 112 there) is a fall."""
    cut = Change("arrival", {"kind": "capacity", "location": "RENO/road-base"}, "set", 140, 9, 9, "test")
    V = ui.view_of(sc.run_case(sc.Case("T", "T", sc.CASE_A.priors, "", "A", (cut,))))
    facts, _ = rd.lines(V)
    assert facts["road-base"]["streak"] == 8 and line_capacity(V["R"], "road-base")[8] == 140
    assert facts["road-base"]["rise"] is None
    assert facts["mtb-carbon"]["rise"] == (375, 580, ui.WEEKS[53])
    for k in CASES:                                  # wherever a rise is reported, it is one, the week after the run
        for ln, d in rd.lines(ui.view_of(sc.run_case(CASES[k])))[0].items():
            if d["rise"]:
                a, b, when = d["rise"]
                assert b > a and when == ui.WEEKS[d["streak"] + 1]


def test_in_A_every_line_reaches_target_the_week_its_full_run_ends(views):
    """What the grid shows: each line's SKUs leave orange the month its dark run ends (no lead time in A)."""
    R = views["A"]["R"]
    held = held_by_line(R)
    for ln in LINES:
        streak = int(np.cumprod(full_mask(R, ln)).sum())
        assert held[ln] == ui.WEEKS[streak + 1], ln


@pytest.mark.parametrize("key", list(CASES))
def test_headline_numbers(views, key):
    V = views[key]
    R, card = V["R"], sc.scorecard(V["R"])
    cards = {label: (value, sub) for label, value, sub, _ in rd.kpi_cards(V)}
    assert cards["All targets held from"][0] == rd.fdate(card["All targets held from"])
    assert cards["Open orders cleared"][0] == rd.fdate(card["Open orders cleared from"])
    assert cards["Open orders cleared"][1].startswith(f"{R['flows']['open_orders'][0].sum():,.0f} open at the start")
    assert num(cards["Bikes built"][0]) == R["builds"].values.sum() == card["Bikes built"]
    cap = sum(line_capacity(R, ln).sum() for ln in LINES)
    assert cards["Bikes built"][1].startswith(f"{card['Bikes built'] / cap:.0%}")
    chk = sc.checks(R)
    assert cards["Plan checks"][0] == f"{int(chk['pass'].sum())} of {len(chk)} pass"
    assert chk["pass"].all()
    below = int((~R["at_target"]).values.sum())
    assert cards["Plan checks"][1] == (f"{below:,} SKU-{'site ' if V['multi'] else ''}weeks below target, all while "
                                       "the line was full")          # no run limit in these scenarios


def test_acceptance_numbers(views):
    """The numbers the presentation quotes, read off the Plan view's own functions."""
    want = {"A": ("6 Sep 2027", "94,429", "278"), "B": ("27 Sep 2027", "94,429", "722"),
            "E1": ("4 Oct 2027", "94,429", "290"), "E2": ("13 Sep 2027", "94,620", "281")}
    for k, (held, built, below) in want.items():
        cards = {label: (v, s) for label, v, s, _ in rd.kpi_cards(views[k])}
        assert cards["All targets held from"][0] == held
        assert cards["Bikes built"][0] == built
        assert cards["Plan checks"][1].startswith(below)


# ---------------- the planning grid ----------------

@pytest.mark.parametrize("key", list(CASES))
def test_grid_is_the_engines(views, key):
    V = views[key]
    R, g = V["R"], rd.grid(V)
    assert g["months"] == MONTHS and len(MONTHS) == 28
    held = held_by_line(R)
    for ln in LINES:
        d = g["lines"][ln]
        built, cap = line_built(R, ln), line_capacity(R, ln)
        for j, p in enumerate(MONTHS):
            w = [t - 1 for t in month_weeks(p)]
            assert d["built"][j] == built[w].sum() and d["capacity"][j] == cap[w].sum()
            assert d["full"][j] == (cap[w].sum() > 0 and built[w].sum() >= cap[w].sum() - 0.5)
            assert d["built"][j] <= d["capacity"][j]
        keys = [k for k in R["wos"].index if R["line"][k] == ln]
        assert sorted((r["sku"], r["pool"]) for r in d["rows"]) == sorted(keys)
        for r in d["rows"]:
            k = (r["sku"], r["pool"])
            ends = [max(month_weeks(p)) for p in MONTHS]
            assert r["wos"] == [R["wos"].at[k, 0]] + [R["wos"].at[k, t] for t in ends]
            assert r["ok"][1:] == [bool(R["at_target"].at[k, t]) for t in ends]
            assert r["ok"][0] == bool(R["wos"].at[k, 0] >= R["target_wos"].at[k, 1])
            assert r["built"][1:] == [sku_built(R, k[0])[month_weeks(p)].sum() for p in MONTHS]
        assert d["held"] == held[ln]


def test_event_months_are_marked_on_the_line_they_touch_only(views):
    events = {k: {ln: rd.grid(views[k])["lines"][ln]["events"] for ln in LINES} for k in CASES}
    mar27, jan27, feb27 = (MONTHS.index(pd.Period(m, "M")) for m in ("2027-03", "2027-01", "2027-02"))
    assert events["E1"] == {"road-base": [], "road-carbon": [], "mtb-base": [], "mtb-carbon": [mar27]}
    assert events["E2"]["mtb-carbon"] == [jan27, feb27, mar27]          # weeks 18-30: 4 Jan to 29 Mar 2027
    assert all(not v for k in ("A", "B") for v in events[k].values())


def test_a_stock_correction_or_a_run_limit_is_marked_where_it_belongs():
    from planner2 import events as ev
    stock = sc.Case("S", "S", sc.CASE_A.priors, "", "A", (ev.stock_correction("RW-9324", "RENO", -200),))
    assert all(not d["events"] for d in rd.grid(ui.view_of(sc.run_case(stock)))["lines"].values())
    if hasattr(sc, "CASE_E3"):                         # frames late: a run limit on RW-4418's builds, weeks 60-67
        V = ui.view_of(sc.run_case(sc.CASE_E3))
        assert rd.has_run_limits(V)
        months = {MONTHS[j].strftime("%b %Y") for j in rd.grid(V)["lines"]["mtb-carbon"]["events"]}
        assert months == {"Oct 2027", "Nov 2027", "Dec 2027"}
        assert all(not rd.grid(V)["lines"][ln]["events"] for ln in LINES if ln != "mtb-carbon")
        assert "or the SKU at its run limit" in dict((c[0], c[2]) for c in rd.kpi_cards(V))["Plan checks"]


def test_figure_draws_each_cell_once_with_its_colour(views):
    for k, V in views.items():
        g = rd.grid(V)
        fig = charts.grid_figure(g)
        layer = {t.name: t for t in fig.data}
        filled = sum((~np.isnan(np.array(t.z, dtype=float))).sum() for t in fig.data)
        n_rows = sum(len(d["rows"]) for d in g["lines"].values())
        assert filled == len(LINES) * 28 + n_rows * 29, k                  # every line month, every SKU cell, once
        assert (~np.isnan(np.array(layer["full"].z, dtype=float))).sum() == sum(sum(d["full"]) for d in g["lines"].values())
        n_below = sum(not ok for d in g["lines"].values() for r in d["rows"] for ok in r["ok"])
        assert sum((~np.isnan(np.array(layer[n].z, dtype=float))).sum() for n in ("deep", "below")) == n_below
        texts = [x for t in fig.data for row in t.text for x in row if x]
        assert not any(x in ("−0", "-0", "0.0 ") for x in texts)
        notes = [a.text for a in fig.layout.annotations]
        for ln, d in g["lines"].items():
            assert any(rd.fdate(d["held"]) in t for t in notes)
        assert len(fig.layout.shapes) == sum(bool(d["events"]) for d in g["lines"].values())


def test_cell_text_never_rounds_onto_the_target():
    assert charts._wos_text(14.6, 15) == "14.6" and charts._wos_text(7.8, 8) == "7.8"
    assert charts._wos_text(-0.3, 8) == "−0.3" and charts._wos_text(-24.2, 15) == "−24" and charts._wos_text(98, 12) == "98"


# ---------------- Build Plans ----------------

@pytest.mark.parametrize("key", list(CASES))
@pytest.mark.parametrize("kind", ["weeks", "months"])
def test_build_plans_table(views, key, kind):
    V = views[key]
    R = V["R"]
    t, cells, kinds = rd.build_table(V, kind)
    per = rd.periods(kind)
    tail = ["12 weeks", "Whole plan"] if kind == "weeks" else ["Whole plan"]
    assert list(t.columns) == ["", "Size", *[lab for lab, _ in per], *tail]
    assert kinds.count("cap") == kinds.count("total") == len(LINES) and len(t) == 2 * len(LINES) + len(ui.SKU)
    i = 0
    for ln in LINES:
        built, cap = line_built(R, ln), line_capacity(R, ln)
        skus = [s for s in ui.ORDER if s in ui.SKUS_BY_LINE[ln]]
        assert t.iloc[i][""] == f"{rd.LINE_WORDS[ln]} line · capacity" and kinds[i] == "cap"
        total = t.iloc[i + 1 + len(skus)]
        assert total[""] == "Line total" and kinds[i + 1 + len(skus)] == "total"
        for lab, weeks in per:
            w = [x - 1 for x in weeks]
            b = sum(0 if t.iloc[i + 1 + j][lab] == "–" else num(t.iloc[i + 1 + j][lab]) for j in range(len(skus)))
            assert b == built[w].sum() == (0 if total[lab] == "–" else num(total[lab]))
            assert num(t.iloc[i][lab]) == cap[w].sum()
            assert (cells.iloc[i + 1 + len(skus)][lab] == "full") == (cap[w].sum() > 0 and b >= cap[w].sum() - 0.5)
        for j, s in enumerate(skus):
            row = t.iloc[i + 1 + j]
            assert row[""] == s and cells.iloc[i + 1 + j][""] == "sub"
            assert num(row["Whole plan"]) == sku_built(R, s).sum()
        assert num(total["Whole plan"]) == built.sum() and num(t.iloc[i]["Whole plan"]) == cap.sum()
        i += 2 + len(skus)
    if kind == "months":                                  # every week is in exactly one month
        assert sum(len(w) for _, w in per) == H


def test_csv_is_the_whole_weekly_plan(views):
    for k, V in views.items():
        d = pd.read_csv(pd.io.common.StringIO(rd.build_csv(V)))
        assert len(d) == len(ui.SKU) * H and d["units"].sum() == V["card"]["Bikes built"]
        assert (rd.transfer_csv(V) is None) == ("move" not in V["case"].decides)
    tc = pd.read_csv(pd.io.common.StringIO(rd.transfer_csv(views["B"])))
    assert tc["units"].sum() == views["B"]["card"]["Bikes transferred to the PDC"]


# ---------------- Summarized Plan ----------------

def rows_of(t) -> dict:
    return {r["Measure"]: list(r)[1:] for _, r in t.iterrows()}


@pytest.mark.parametrize("key", ["A", "B", "E1"])
@pytest.mark.parametrize("gran", ui.GRANULARITY)
def test_summarized_plan_balances_and_matches_the_first_ui(views, key, gran):
    V = views[key]
    skus = list(ui.SKU.index)
    t, cells, kinds = rd.summarized_plan(V, skus, gran)
    r = rows_of(t)
    assert [t.iloc[i]["Measure"] for i, k in enumerate(kinds) if k == "section"] == \
        ["Demand", "Supply", "Stock at the period's end", "At the period's end"]
    n = len(t.columns) - 1
    val = {m: [None if x == "" else num(x) for x in r[m]] for m in r if m != "SKUs at target"}
    net, builds, demand = val["Net inventory"], val["Builds"][1:], val["Forecast demand"][1:]
    wip = val.get(rd.WIP, [0] * n)
    assert (rd.WIP in r) == any(V["case"].build_weeks.values())
    for i in range(1, n):
        assert abs(net[i] + wip[i] - (net[i - 1] + wip[i - 1] + builds[i - 1] - demand[i - 1])) <= 1, (key, gran, i)
    assert sum(builds) == V["card"]["Bikes built"]
    old, flags = ui.plan_grid(V, skus, gran)                      # the first UI's own computation of the same grid
    assert list(old.columns) == list(t.columns[1:])
    for m in ("Forecast demand", "Builds", "On hand", "Open orders", "Net inventory"):
        assert [None if x in ("", None) else num(x) for x in old.loc[m]] == val[m], m
    assert [x.split(" ")[0] for x in r["SKUs at target"]] == \
        [str(round(num(x) / 100 * len(skus))) for x in old.loc["% SKUs @ nominal inv."]]
    assert "Capacity" in r and all(num(x) <= 100 for x in r["Capacity used"][1:])
    for c, ok in flags["% SKUs @ nominal inv."].items():
        assert (cells.loc[[m == "SKUs at target" for m in t["Measure"]], c].iloc[0] == "below") == (not ok)


def test_summarized_plan_for_one_sku_shows_its_weeks_of_supply(views):
    V = views["A"]
    t, cells, kinds = rd.summarized_plan(V, ["RW-4418"], "Quarter")
    r = rows_of(t)
    assert "Capacity" not in r and "Weeks of supply" in r and "Target (weeks)" in r
    R = V["R"]
    k = ("RW-4418", "CMH+RENO")
    end = [0] + [int(x) for x in [ui.FQ_END[q] for q in ui.FQ_ORDER]]
    assert [num(x) for x in r["Weeks of supply"]] == [round(R["wos"].at[k, w], 1) for w in end]
    t, _, _ = rd.summarized_plan(views["B"], ["RW-4418"], "Quarter")
    assert "Weeks of supply (lowest site)" in rows_of(t)


# ---------------- Plan by SKU ----------------

@pytest.mark.parametrize("key", list(CASES))
def test_plan_by_sku_adds_up(views, key):
    V = views[key]
    R = V["R"]
    t, cells, kinds = rd.sku_table(V)
    assert list(t.columns) == rd.SKU_COLS and sum(n for _, n in rd.SKU_GROUPS) == len(rd.SKU_COLS)
    held = held_by_line(R)
    by = {row[""]: row for _, row in t.iterrows()}
    for s in ui.ORDER:
        row, d = by[s], rd.sku_numbers(V, s)
        assert num(row["Built"]) == sku_built(R, s).sum()
        assert num(row["Forecast"]) == V["demand"].loc[s].sum()
        assert abs(num(row["Net "]) + d["wip1"] - (num(row["Net"]) + num(row["Built"]) - num(row["Forecast"]))) <= 1
        assert num(row["Stock"]) - num(row["Open orders"]) == pytest.approx(num(row["Net"]), abs=1)
        keys = [k for k in R["wos"].index if k[0] == s]
        hw = max(sc.held_from(R["at_target"].loc[[k]]).iloc[0] for k in keys)
        assert row["At target from"] == rd.fdate(ui.WEEKS[int(hw)])
        assert num(row["Weeks below"]) == (~R["at_target"].loc[keys]).values.sum()
    for ln in LINES:
        row = by[f"{rd.LINE_WORDS[ln]} line"]
        assert row["At target from"] == rd.fdate(held[ln])
        assert num(row["Built"]) == line_built(R, ln).sum()
    total = by["All SKUs"]
    assert num(total["Built"]) == V["card"]["Bikes built"]
    assert num(total["Weeks below"]) == V["card"]["Position-weeks below target"]
    assert num(total["Open orders"]) == R["flows"]["open_orders"][0].sum()
    assert total["At target from"] == rd.fdate(V["card"]["All targets held from"])


def test_a_sku_is_at_target_when_its_last_site_is():
    """B with 3,000 more RW-4418 at the PDC: the PDC is at target from week 1, Reno only from week 40."""
    from dataclasses import replace
    more = Change("opening", {"kind": "inventory", "item": "RW-4418", "location": "CMH"}, "add", 3000, None, None, "t")
    V = ui.view_of(sc.run_case(replace(sc.CASE_B, key="X", changes=(more,))))
    R = V["R"]
    sites = {k[1]: int(sc.held_from(R["at_target"].loc[[k]]).iloc[0]) for k in R["wos"].index if k[0] == "RW-4418"}
    assert sites == {"CMH": 1, "RENO": 40}
    by = {row[""]: row for _, row in rd.sku_table(V)[0].iterrows()}
    assert by["RW-4418"]["At target from"] == rd.fdate(ui.WEEKS[40])


def test_a_one_week_event_marks_its_month():
    order = Change("arrival", {"kind": "order", "item": "RW-4418", "channel": "commercial"}, "add", 300, 40, 40, "t")
    V = ui.view_of(sc.run_case(sc.Case("O", "O", sc.CASE_A.priors, "", "A", (order,))))
    assert [MONTHS[j] for j in rd.grid(V)["lines"]["mtb-carbon"]["events"]] == [MONTH[40]]


def test_plan_by_sku_numbers_for_A(views):
    by = {row[""]: row for _, row in rd.sku_table(views["A"])[0].iterrows()}
    assert (by["All SKUs"]["Stock"], by["All SKUs"]["Open orders"], by["All SKUs"]["Net"]) == ("3,000", "5,991", "−2,991")
    assert by["All SKUs"]["Forecast"] == "79,622" and by["RW-9324"]["At the start"] == "98.0"


# ---------------- the page ----------------

def start(**query):
    at = AppTest.from_file(APP, default_timeout=300)
    for k, v in query.items():
        at.query_params[k] = v
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def html(at, cls) -> str:
    return next(m.value for m in at.markdown if cls in m.value)


def test_every_built_in_scenario_renders(folder):
    at = start()
    assert at.title[0].value == "Scenario A · base case"
    for k, c in CASES.items():
        at.selectbox(key="p3_plan_key").set_value(k).run()
        assert not at.exception, [e.message for e in at.exception]
        assert at.title[0].value == c.name
        assert [t.label for t in at.tabs] == ["Build Plans", "Summarized Plan", "Plan by SKU"]
        assert html(at, "p3-builds") and html(at, "p3-summary") and html(at, "p3-skus") and html(at, "p3-checks")
        assert at.query_params.get("scenario") in (k, [k])
        assert any("p3-chip" in m.value for m in at.markdown) == bool(c.changes)
        assert not any(b.label.startswith("Ask") for b in at.button)                # no Ask on this page


def test_page_shows_the_numbers_of_the_scenario_on_screen(folder, views):
    at = start()
    assert "6 Sep 2027" in html(at, "p3-verdict") and "94,429" in html(at, "p3-kpis")
    assert "Targets: Road 8 weeks (10 from 3 Jan 2028) · MTB base 12 weeks · MTB carbon 15 weeks" in html(at, "p3-note")
    at.selectbox(key="p3_plan_key").set_value("E1").run()
    assert "4 Oct 2027" in html(at, "p3-verdict")
    assert "Event · MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027 · set to 0" in html(at, "p3-chip")
    n = len(views["E1"]["checks"])
    assert f"{n} of {n} pass" in html(at, "p3-kpis") and html(at, "p3-checks").count("✓") == n


def test_a_link_opens_its_scenario(folder):
    at = start(scenario="B")
    assert at.title[0].value == CASES["B"].name and at.selectbox(key="p3_plan_key").value == "B"
    at = start(scenario="nonsense")
    assert at.title[0].value == CASES["A"].name


def test_tables_follow_their_controls(folder):
    at = start()
    at.selectbox(key="p3_scope_A").set_value("line:mtb-carbon").run()
    t = html(at, "p3-summary")
    assert "Capacity used" in t and "SKUs at target" in t and "of 3" in t
    at.radio(key="p3_gran_A").set_value("Month").run()
    assert "Sep 2026" in html(at, "p3-summary")
    at.selectbox(key="p3_scope_A").set_value("RW-4418").run()
    assert "Weeks of supply" in html(at, "p3-summary")
    at.radio(key="p3_bk_A").set_value("months").run()
    assert "Sep 26" in html(at, "p3-builds") and "Dec 28" in html(at, "p3-builds") and "12 weeks" not in html(at, "p3-builds")
    assert not at.exception


def test_a_saved_scenario_is_listed_and_planned(folder):
    store.save(sc.Case("C", "Scenario C · test", sc.CASE_B.priors, "a test", "B"), folder)
    at = start()
    at.selectbox(key="p3_plan_key").set_value("C").run()
    assert at.title[0].value == "Scenario C · test" and "27 Sep 2027" in html(at, "p3-verdict")


def test_a_scenario_that_cannot_be_planned_shows_why(folder):
    bad = priors.apply_changes(sc.CASE_A.priors, [{"prior": "decides", "applies_to": "make", "new": "no"}])
    store.save(sc.Case("C", "Scenario C · broken", bad, "edited by hand", "A"), folder)
    at = start(scenario="C")
    assert not at.exception and any("can't be planned" in e.value for e in at.error)
