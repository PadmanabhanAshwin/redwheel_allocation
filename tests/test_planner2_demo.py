"""The demo planner (planner2_demo/): the final scenario set (A, R, R+; R+C26, R+E4, R+E5, R+P1 on R+). What each view
shows is checked against the engine computed independently and against the solver session's final numbers
(docs/SOLVER_NOTE_TO_DECK_AND_UI.md §7, the deck's scorecards); every flow is run with fakes standing in for Claude.
Runs are saved to a scratch folder."""
import json
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
from planner2_demo import charts, pivot, reading as rd, state  # noqa: E402
from redwheel import llm, priors, scenarios as sc, store, tunables as tu  # noqa: E402

APP = str(ROOT / "planner2_demo" / "app.py")
CASES = {"A": sc.CASE_A, **sc.R_CASES}
KEYS = list(CASES)
H, W = ui.H, ui.WEEKS


@pytest.fixture(scope="module")
def views():
    return {k: ui.view_of(sc.run_case(c)) for k, c in CASES.items()}


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "FOLDER", tmp_path)
    return tmp_path


def date(s) -> pd.Timestamp:
    return pd.Timestamp(s)


def short(k) -> str:
    return f"{k} · {CASES[k].name.split(' · ', 1)[1]}"


# ---------------- the set and its numbers ----------------

def test_the_set_is_the_solver_sessions():
    assert list(state.BUILT_IN) == ["A", "R", "R+", "R+C26", "R+E4", "R+E5", "R+P1"]         # the deck's order
    assert state.FEATURED == ("R+", "R") and state.EXAMPLES == ("R+C26", "R+E4", "R+E5", "R+P1")
    assert all(CASES[k].parent == "R+" for k in state.EXAMPLES)


def test_acceptance_numbers(views):
    """The solver's final table: bikes built, every target held from, on-time fill; position-weeks from the deck."""
    want = {"A": ("94,429", "278", "6 Sep 2027", "96.4%"), "R": ("94,429", "349", "20 Sep 2027", "95.5%"), "R+": ("94,429", "367", "4 Oct 2027", "94.8%"),
            "R+C26": ("94,429", "394", "25 Oct 2027", "93.8%"), "R+E4": ("94,729", "370", "11 Oct 2027", "94.0%"),
            "R+E5": ("94,462", None, "4 Oct 2027", "94.8%"), "R+P1": ("94,429", None, "4 Oct 2027", "94.8%")}
    for k, w in want.items():
        got = tuple(v for _, v, _, _ in rd.kpis(views[k]))
        assert got[0] == w[0] and got[2:] == w[2:] and (w[1] is None or got[1] == w[1]), k
    assert [label for label, *_ in rd.kpis(views["R+"])] == ["Bikes built", "Position-weeks below target",
                                                              "All targets held from", "On-time fill"]
    cleared = {"R": "2026-12-28", "R+": "2027-01-11", "R+C26": "2027-02-08", "R+E4": "2027-01-25", "R+E5": "2027-01-18"}
    for k, d in cleared.items():
        assert views[k]["card"]["Open orders cleared from"] == date(d), k
    p1 = rd.bike_dates(views["R+P1"])
    assert [p1[s][1] for s in ("RW-9304", "RW-4418", "RW-6416")] == [date("2027-05-31"), date("2027-09-13"),
                                                                    date("2027-10-04")]


def test_the_scorecard_changes_read_as_the_decks(views):
    def change(k, k0):
        return [(d, t) for _, _, d, t in rd.kpis(views[k], views[k0])]
    assert change("R+", "R") == [("same", "same"), ("+18", "bad"), ("+2 wk", "bad"), ("−0.7 pt", "bad")]
    assert change("R+C26", "R+") == [("same", "same"), ("+27", "bad"), ("+3 wk", "bad"), ("−1.0 pt", "bad")]
    assert change("R+E4", "R+") == [("+300", "neutral"), ("+3", "bad"), ("+1 wk", "bad"), ("−0.8 pt", "bad")]
    assert change("R+E5", "R+")[0] == ("+33", "neutral") and change("R+E5", "R+")[2] == ("same", "same")
    assert change("R", "R+")[1] == ("−18", "good") and change("R+P1", "R+")[2:] == [("same", "same")] * 2
    assert all(d is None for _, _, d, _ in rd.kpis(views["R+"]))


def test_change_lines_one_line_each(views):
    def lines(k, k0="R+"):
        return rd.change_lines(CASES[k0], CASES[k], views[k])
    assert lines("R+", "R") == [("Build time", "Road carbon, MTB carbon", "1 week", "2 weeks")]
    assert lines("R+C26") == [("Line capacity", "All lines' capacity · weeks of 21 Dec to 28 Dec 2026", "1,770 bikes",
                               "0 bikes")]
    assert lines("R+E4") == [("One-off order", "Commercial orders for RW-4418 · week of 9 Nov 2026", "7 bikes",
                              "307 bikes")]
    assert lines("R+E5") == [("Lot size", "RW-9304 builds", "any whole number", "in lots of 50")]   # the whole plan
    assert lines("R+P1") == [("Priority order", "", "even rule",
                              "past-due > open orders > target; MTB carbon: RW-9304 > RW-4418 > RW-6416")]
    assert lines("R+", "R+") == [] and rd.same_plan(views["R+"], views["R+"])


# ---------------- the phases ----------------

def _states(R, keys) -> list:
    """Independently, from the run's own positions: 'w' if any position has an order waiting, else 'b' if any is
    below target, else 'a'."""
    oo = R["flows"]["open_orders"].loc[keys, 1:H].sum() > 0.5
    ok = R["at_target"].loc[keys, 1:H].all()
    return ["w" if oo[t] else ("a" if ok[t] else "b") for t in range(1, H + 1)]


@pytest.mark.parametrize("key", KEYS)
def test_phases_are_the_runs_own(views, key):
    V, R = views[key], views[key]["R"]
    dates, lines = rd.bike_dates(V), rd.plan_reading(V)["lines"]
    for ln in ui.LINES:
        skus = ui.SKUS_BY_LINE[ln]
        for group in [skus] + [[s] for s in skus]:
            runs = rd.phase_runs(V, group)
            assert runs[0][1] == 1 and runs[-1][2] == H and all(a[2] + 1 == b[1] for a, b in zip(runs, runs[1:]))
            assert all(a[0] != b[0] for a, b in zip(runs, runs[1:]))                    # each run as long as it goes
            flat = [p for p, a, b in runs for _ in range(a, b + 1)]
            keys = [k for k in R["at_target"].index if k[0] in group]
            assert flat == _states(R, keys), (ln, group)
        held = rd.held_from_runs(rd.phase_runs(V, skus))
        assert (W[held] if held else None) == lines[ln]["held_from"], ln                 # the date the chart shows
        for s in skus:
            runs = rd.phase_runs(V, [s])
            h = rd.held_from_runs(runs)
            assert (W[h] if h else None) == dates[s][1], s
            waits = [b for p, a, b in runs if p == "w"]
            assert W[max(waits) + 1 if waits else 1] == dates[s][0], s                   # orders cleared the week after


def test_no_week_is_at_target_while_customers_wait(views):
    """Why 'customers waiting' may be read first: orders ship as soon as stock exists, so a bike with an order waiting
    has none in stock and is below any target."""
    for V in views.values():
        waiting = V["open_orders"].loc[:, 1:H] > 0.5
        assert not (waiting & V["at_target"].loc[:, 1:H]).values.any()


@pytest.mark.parametrize("key", KEYS)
def test_supply_is_the_engines_target_and_waiting(views, key):
    """The comparison chart's line, week by week: at or above its target exactly when the engine has every bike at
    target, below zero exactly when a customer waits; for every line and every bike."""
    V = views[key]
    for ln in ui.LINES:
        for group in [ui.SKUS_BY_LINE[ln]] + [[s] for s in ui.SKUS_BY_LINE[ln]]:
            y, t = rd.supply(V, group)
            at = V["at_target"].loc[group, 1:H].all().to_numpy()
            waiting = (V["open_orders"].loc[group, 1:H] > 0.5).any().to_numpy()
            assert np.array_equal(y >= t - 1e-6, at), (ln, group)
            assert np.array_equal(y < -1e-9, waiting), (ln, group)


def test_supply_reads_a_bike_at_its_worst_stock_site():
    """With two stock sites (scenario B: web orders from the PDC), a bike is at target only when both sites are."""
    V = ui.view_of(sc.run_case(sc.CASE_B))
    for s in ui.ORDER:
        y, t = rd.supply(V, [s])
        assert np.array_equal(y >= t - 1e-6, V["R"]["at_target"].loc[[k for k in V["R"]["at_target"].index
                                                                       if k[0] == s], 1:H].all().to_numpy()), s


@pytest.mark.parametrize("key", KEYS)
def test_the_supply_map_is_the_runs_own(views, key):
    """Every bike in line order; a cell is red (below 1) exactly when a customer waits, green (2 and up) exactly when
    the bike is at target, grey otherwise; the date on the right is the bike's own at-target date."""
    V = views[key]
    rows = rd.supply_map(V, H)
    assert [r["sku"] for r in rows] == [s for ln in ui.LINES for s in ui.ORDER if s in ui.SKUS_BY_LINE[ln]]
    dates = rd.bike_dates(V)
    for r in rows:
        s = r["sku"]
        waiting = (V["open_orders"].loc[s, 1:H] > 0.5).to_numpy()
        at = V["at_target"].loc[s, 1:H].to_numpy(bool)
        assert np.array_equal(r["z"] < 1, waiting) and np.array_equal(r["z"] >= 2, at), s
        assert ((r["z"] >= 0) & (r["z"] < 3)).all()
        assert (W[r["held"]] if r["held"] else None) == dates[s][1], s
    assert rd.map_end(V) == 70                                                            # every bike held by Oct 2027


def test_the_map_runs_to_the_last_date_held(views):
    e = tu.make("line_capacity", line="mtb-carbon", first=pd.Timestamp("2026-09-07").date(), weeks=121, percent=40,
                why="")
    never = ui.view_of(sc.run_case(tu.apply(CASES["R+"], [e], key="T", name="T", summary="", parent="R+")))
    assert rd.map_end(never) == H and rd.map_end(views["R+"], never) == H                   # a bike never at target


def test_two_maps_one_above_the_other(views):
    def fig(k, k0="R+"):
        return charts.supply_map_figure(views[k], views[k0])

    def right(f):                                                     # the dates and shifts written on the right
        return [a.text for a in f.layout.annotations if a.xref == "paper" and a.xanchor == "left"]
    f = fig("R+C26")
    maps = [t for t in f.data if t.type == "heatmap"]
    end = rd.map_end(views["R+C26"], views["R+"])
    for t, k in zip(maps, ("R+C26", "R+")):                                               # the scenario above
        z = [row for row in t.z if row[0] is not None]
        assert np.allclose(np.array(z, float), np.array([r["z"] for r in rd.supply_map(views[k], end)]))
    assert [a.text for a in f.layout.annotations][:2] == ["<b>R+C26</b> · closed for Christmas 2026",
                                                         "<b>R+</b> · build time by model"]
    shifts = right(f)[:10]
    assert sum("+3 wk" in x for x in shifts) == 3 and sum("+4 wk" in x for x in shifts) == 3      # MTB and road carbon
    assert sum("+6 wk" in x for x in shifts) == 1 and right(f)[10:] == [x.split("  ")[0] for x in right(f)[10:]]
    assert len([s_ for s_ in f.layout.shapes if s_.type == "rect"]) == 4                  # the closure on every line
    assert "weeks changed" in {t.name for t in f.data}
    p1 = right(fig("R+P1"))
    assert "31 May 2027  <span style='color:#1e7b3a'><b>−18 wk</b></span>" in p1
    assert len([s_ for s_ in fig("R+E4").layout.shapes if s_.type == "rect"]) == 1          # MTB carbon, one week
    assert not [s_ for s_ in fig("R+E5").layout.shapes if s_.type == "rect"]               # lots: no period
    one = charts.supply_map_figure(views["R+C26"], against=views["R+"])
    assert len([t for t in one.data if t.type == "heatmap"]) == 1 and len(one.layout.shapes) == 4
    assert len([t for t in charts.supply_map_figure(views["A"]).data if t.type == "heatmap"]) == 1


# ---------------- the scenario template ----------------

def test_the_scenario_chart_is_the_decks(views):
    for k in ("R+", "R"):
        V = views[k]
        fig = charts.plan_figure(V)
        n = charts.months_shown(V)
        assert n == 16 and str(rd.MONTHS[n - 1]) == "2027-12"                            # Sep 2026 – Dec 2027
        bars = [t for t in fig.data if t.type == "bar"]
        assert [t.hovertemplate.split(":")[0] for t in bars] == ui.ORDER
        for ln in ui.LINES:
            d = rd.monthly_stack(V, ln)
            for s, y in d["built"].items():
                bar = next(t for t in bars if t.hovertemplate.startswith(s + ":"))
                assert np.array_equal(np.array(bar.y), y[:n])
        held = rd.plan_reading(V)["lines"]
        lines_ = [s_ for s_ in fig.layout.shapes if s_.type == "line"]
        assert sorted(pd.Timestamp(s_.x0) for s_ in lines_) == sorted(held[ln]["held_from"] for ln in ui.LINES)
        bw = CASES[k].build_weeks
        assert [a.text for a in fig.layout.annotations] == [
            f"<b>{rd.LINE_WORDS[ln]}</b>   build time {bw[ln]:g} wk · target held {rd.fdate(held[ln]['held_from'])}"
            for ln in ui.LINES]
    assert "build time 2 wk · target held 4 Oct 2027" in charts.plan_figure(views["R+"]).layout.annotations[3].text


def test_each_scenario_reads_as_its_slide(views):
    """The chart shades the months in which a change of the scenario's own applies (none for a setting, a lot size or a
    priority order); the base scenario's chart shades nothing."""
    def shaded(k, k0):
        fig = charts.plan_figure(views[k], views[k0] if k0 else None)
        rects = [s_ for s_ in fig.layout.shapes if s_.type == "rect"]
        return sorted({(pd.Timestamp(r.x0) + pd.Timedelta(days=15)).strftime("%Y-%m") for r in rects}), len(rects), \
            any(t.name == "weeks changed" for t in fig.data)
    assert shaded("R+C26", "R+") == (["2026-12"], 4, True)                                   # every line, December
    assert shaded("R+E4", "R+") == (["2026-11"], 1, True)                                    # MTB carbon, November
    assert shaded("R+E5", "R+") == ([], 0, False) and shaded("R+P1", "R+") == ([], 0, False)
    assert shaded("R+", "R") == ([], 0, False) and shaded("A", None) == ([], 0, False)


def test_scenarios_reads_each_against_the_one_it_is_built_on(folder):
    at = start("scenarios.py")
    at.radio(key="scen_pick").set_value("R+C26").run()
    assert ok(at).subheader[0].value == f"{short('R+C26')}, against R+"
    assert md(at, "<b>Line capacity</b> · All lines&#x27; capacity · weeks of 21 Dec to 28 Dec 2026: 1,770 bikes → "
                  "<b>0 bikes</b>") and md(at, "<em class='bad'>+3 wk</em>")
    one = json.loads(at.get("plotly_chart")[1].proto.spec)                                   # its own supply map
    assert len([t for t in one["data"] if t.get("type") == "heatmap"]) == 1
    assert len(one["layout"]["shapes"]) == 4 and not one["layout"].get("annotations", [{}])[0].get("text", "").startswith("<b>")
    at.radio(key="scen_pick").set_value("A").run()
    assert ok(at).subheader[0].value == "A · base case" and not any("rw-change" in m.value for m in at.markdown)
    assert not any("<em" in m.value for m in at.markdown)                                   # no changes to show
    store.save(sc.Case("F", "Scenario F · a run on R+", CASES["R+"].priors, "", "R+", sc.CASE_RP_C26.changes), folder)
    at = start("scenarios.py")
    assert at.radio(key="scen_pick").options == KEYS + ["F"]                                # the user's runs after
    at.radio(key="scen_pick").set_value("F").run()
    assert ok(at).subheader[0].value == "F · a run on R+, against R+" and md(at, "+3 wk")


def test_assumptions_in_technical_shorthand(views):
    a = dict(rd.assumptions(views["R+"]))
    assert a["Build lead time"] == "carbon lines 2 wk, base lines 1 wk"
    assert a["Sourcing"] == "pooled (Reno + PDC)" and a["Priority"] == "even rule" and a["Decisions"] == "builds"
    assert dict(rd.assumptions(views["R"]))["Build lead time"] == "1 wk"
    assert dict(rd.assumptions(views["A"]))["Build lead time"] == "0 wk"
    assert dict(rd.assumptions(views["R+P1"]))["Priority"] == \
        "past-due > open orders > target; MTB carbon: RW-9304 > RW-4418 > RW-6416"


def test_the_build_plan_table_periods_cover_each_week_once():
    cols = rd.period_tree()
    for level in "YQM":
        assert sorted(w for c in cols if c["level"] == level for w in c["weeks"]) == list(range(1, H + 1)), level
    assert [c["id"] for c in cols if c["level"] == "Y"] == ["FY26", "FY27", "FY28"]


@pytest.mark.parametrize("key", ["R+", "R+C26", "R+P1"])
def test_the_build_plan_table_is_the_runs_numbers(views, key):
    V, R = views[key], views[key]["R"]
    d = rd.pivot_data(V)
    cols = rd.period_tree()
    rows = {(r["line"], r["sku"], r["metric"]): r for r in d["rows"]}
    flows = {"build": V["built"], "forecast": V["demand"], "shipped": V["shipped"]}
    levels = {"open": V["open_orders"], "net": V["net"], "on_hand": V["on_hand"] + V["transit"]}
    for s in ui.ORDER:
        ln = ui.SKU.at[s, "line_id"]
        for m, df in flows.items():
            v = rows[(ln, s, m)]["values"]
            assert v["start"] is None and all(v[c["id"]] == df.loc[s, c["weeks"]].sum() for c in cols[1:])
        for m, df in levels.items():
            v = rows[(ln, s, m)]["values"]
            assert all(v[c["id"]] == df.at[s, max(c["weeks"])] for c in cols[:-1])
        keys = [k for k in R["wos"].index if k[0] == s]
        w = rows[(ln, s, "wos")]
        for c in cols[1:-1]:
            assert w["values"][c["id"]] == R["wos"].loc[keys, max(c["weeks"])].min()
    for ln in ui.LINES:
        cap = rows[(ln, None, "capacity")]["values"]
        assert all(cap[c["id"]] == R["obj"].arrivals.loc[f"capacity||RENO/{ln}", c["weeks"]].sum() for c in cols[1:])
    assert rows[(None, None, "build")]["values"]["total"] == V["card"]["Bikes built"]


@pytest.mark.parametrize("key", ["R+C26", "R+E4", "R+P1"])
def test_the_difference_table_is_b_minus_a_cell_by_cell(views, key):
    V, V0 = views[key], views["R+"]
    c = rd.pivot_compare(V, V0)
    a = {(r["line"], r["sku"], r["metric"]): r for r in rd.pivot_data(V0)["rows"]}
    b = {(r["line"], r["sku"], r["metric"]): r for r in rd.pivot_data(V)["rows"]}
    for r in c["rows"]:
        k = (r["line"], r["sku"], r["metric"])
        for cid, v in r["values"].items():
            x, y = a[k]["values"].get(cid), b[k]["values"].get(cid)
            assert v == (None if x is None and y is None else (y or 0) - (x or 0)), (k, cid)
    assert c["labels"] == {"diff": f"{key} − R+", "a": "R+", "b": key}
    if key == "R+E4":
        assert {ln for ln, s, m in [(r["line"], r["sku"], r["metric"]) for r in c["rows"] if r["changed"]]} == \
            {"mtb-carbon", None}                                                           # one line, and all lines


def test_the_tables_fit_their_rows(views):
    page = pivot.html(rd.pivot_compare(views["R+E4"], views["R+"]), 640)
    assert "MAX_H = 640" in page and "__MAX_H__" not in page and "Or click" not in page
    assert '"no change"' in page and "no change by ${by}" in page and "same as" not in page   # no key to look up
    assert "function heat(" in page and "if (D.modes) scales(D.modes.diff, vis);" in page        # cells shaded by size
    assert 'let mode = D.modes ? "b" : null;' in page and "let changedOnly = false;" in page   # the plan, every row


def test_the_weekly_csv_is_the_whole_plan(views):
    for V in views.values():
        csv = pd.read_csv(pd.io.common.StringIO(rd.build_csv(V)))
        assert csv["units"].sum() == V["card"]["Bikes built"] and len(csv) == 10 * H


# ---------------- state ----------------

def test_saved_runs_show_only_on_the_set(folder):
    store.save(sc.Case("C", "Scenario C · copy of B", sc.CASE_B.priors, "", "B"), folder)          # an older run
    store.save(sc.Case("F", "Scenario F · a run on R+", CASES["R+"].priors, "", "R+"), folder)
    store.save(sc.Case("G", "Scenario G · a run on F", CASES["R+"].priors, "", "F"), folder)
    shown = state._rooted(store.load_all(folder))
    assert sorted(shown) == ["F", "G"]
    at = start("whatif.py")
    assert at.radio(key="_run").options == [short(k) for k in state.EXAMPLES] + \
        ["F · a run on R+", "G · a run on F"]
    at.button(key="tc_run").click().run()
    ok(at)
    assert at.radio(key="_run").value == "D"                                                  # the next free letter
    assert store.load_all(folder)["C"].name == "Scenario C · copy of B"                           # C is never written over


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
    assert at.title[0].value == "Model" and md(at, "Resources")
    assert not at.table and not at.dataframe and not at.caption                          # no tables, no notes
    at.switch_page("scenarios.py").run()
    pick = at.radio(key="scen_pick")
    assert ok(at).title[0].value == "Scenarios" and pick.options == KEYS and pick.value == "R+"   # every scenario
    assert at.subheader[0].value == f"{short('R+')}, against R" and md(at, "carbon lines 2 wk, base lines 1 wk")
    assert len(at.get("iframe")) == 1 and len(at.get("plotly_chart")) == 2
    at.radio(key="scen_pick").set_value("R").run()
    assert ok(at) and md(at, "<span>Build lead time</span>1 wk") and at.subheader[0].value == f"{short('R')}, against A"
    at.switch_page("compare.py").run()
    assert ok(at).title[0].value == "Compare" and at.selectbox(key="_k").value == "R+"
    assert at.selectbox(key="_k0").value == "R" and md(at, "+2 wk") and md(at, "<b>Build time</b>")
    assert not at.table and not at.dataframe
    at.switch_page("whatif.py").run()
    assert ok(at).title[0].value == "Try a change" and at.radio(key="_run").value == "R+C26" and md(at, "+3 wk")


def test_compare_any_pair(folder):
    at = start("compare.py")
    at.selectbox(key="_k").set_value("R+P1").run()
    at.selectbox(key="_k0").set_value("R+").run()
    assert ok(at) and md(at, "RW-9304 &gt; RW-4418 &gt; RW-6416") and md(at, "−21")
    at.selectbox(key="_k").set_value("R+").run()
    assert any("Pick two different scenarios" in c.value for c in at.caption)


def test_every_live_scenario_reads_against_r_plus(folder):
    at = start("whatif.py")
    for k in state.EXAMPLES:
        at.radio(key="_run").set_value(k).run()
        ok(at)
        assert at.subheader[0].value == f"{short(k)}, against R+"
    assert md(at, "Priority order")


def test_a_change_by_form_runs_and_reads_against_its_start(folder):
    at = start("whatif.py")
    assert at.selectbox(key="tc_base").value == "R+" and at.selectbox(key="tc_tunable").value == "line_capacity"
    assert not any(t.key and t.key.endswith("_why") for t in at.text_input)                  # the optional note is off
    at.button(key="tc_run").click().run()
    ok(at)
    new = at.radio(key="_run").value
    assert new not in state.BUILT_IN and (folder / f"{new}.json").exists()
    assert at.subheader[0].value.endswith("against R+") and md(at, "<b>Line capacity</b>")
    saved = store.load_all(folder)[new]
    assert saved.parent == "R+" and tu.same_changes(saved.changes, sc.CASE_E1.changes)        # the form's defaults
    at.button(key="tc_remove").click().run()
    assert ok(at) and not (folder / f"{new}.json").exists()


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
    assert seen == [("A fleet order of 300 RW-4418 lands in November", "R+")] and md(at, "+300 bikes")
    at.button(key="tc_prop_run").click().run()
    ok(at)
    assert at.radio(key="_run").value not in state.BUILT_IN and md(at, "+300")


def test_claude_asking_back_or_failing_changes_nothing(folder, monkeypatch):
    monkeypatch.setattr(llm, "propose_edits", lambda r, c, client=None: llm.EditProposal(
        request=r, case=c, question="Which line is down?", unsupported=["a rule that depends on the weather"]))
    at = start("whatif.py")
    at.text_input(key="tc_req").input("A line is down").run()
    at.button(key="tc_propose").click().run()
    assert any(i.value == "Which line is down?" for i in at.info) and not any(b.key == "tc_prop_run" for b in at.button)

    def down(*a, **k):
        raise ConnectionError("no network")
    monkeypatch.setattr(llm, "propose_edits", down)
    at.button(key="tc_propose").click().run()
    assert not at.exception and any("did not go through" in w.value for w in at.warning)


def test_ask_answers_from_the_pair_on_screen(folder, monkeypatch):
    seen = []
    monkeypatch.setattr(llm, "explain", lambda q, f, client=None: seen.append((q, f)) or {"answer": "Build time."})
    at = start("compare.py")
    at.button(key="ask_R_R+_ex0").click().run()
    at.button(key="ask_R_R+_go").click().run()
    assert seen[0][0] == "Why does R+ differ from R?" and "SCENARIO R+" in seen[0][1] and md(at, "Build time.")


def test_a_saved_run_that_cannot_be_planned_does_not_break_the_app(folder):
    bad = priors.apply_changes(CASES["R+"].priors, [{"prior": "decides", "applies_to": "make", "new": "no"}])
    store.save(sc.Case("C", "Scenario C · broken", bad, "edited by hand", "R+"), folder)
    at = start("whatif.py")
    at.radio(key="_run").set_value("C").run()
    assert not at.exception and any("Cannot be planned" in e.value for e in at.error)


# ---------------- words ----------------

def test_no_ai_words_or_sparkles():
    banned = re.compile(r"auto_awesome|insights|✨|\b(insight\w*|seamless\w*|leverag\w*|unlock\w*|powerful|magic\w*|"
                        r"smart|AI-powered|delve|robust|cutting-edge|game-changer)\b", re.I)
    for p in (ROOT / "planner2_demo").glob("*.py"):
        hits = [m.group(0) for m in banned.finditer(p.read_text())]
        assert not hits, (p.name, hits)


def test_the_pages_draw_the_pairs_own_data(folder, views):
    """Compare draws the comparison chart of the pair picked and its table; Scenarios the table of the one picked."""
    at = start("compare.py")
    at.selectbox(key="_k").set_value("R+C26").run()
    at.selectbox(key="_k0").set_value("R+").run()
    frames = [f.proto.srcdoc for f in ok(at).get("iframe")]
    assert len(frames) == 1
    assert json.dumps(rd.pivot_compare(views["R+C26"], views["R+"])) in frames[0] and "MAX_H = 640" in frames[0]
    import base64

    def array(v):                                                 # plotly's binary arrays: {"dtype", "bdata"}
        return np.frombuffer(base64.b64decode(v["bdata"]), v["dtype"]) if isinstance(v, dict) else np.array(v)
    spec = json.loads(at.get("plotly_chart")[0].proto.spec)
    end = rd.map_end(views["R+C26"], views["R+"])
    maps = [t for t in spec["data"] if t.get("type") == "heatmap"]
    assert len(maps) == 2
    for t, k in zip(maps, ("R+C26", "R+")):
        z = [row for row in t["z"] if row[0] is not None]
        assert np.allclose(np.array(z, float), np.array([r["z"] for r in rd.supply_map(views[k], end)]))
    at.selectbox(key="_k").set_value("R+E5").run()
    assert ok(at) and len(at.get("plotly_chart")) == 1 and len(at.get("iframe")) == 1         # the same picture, always
    at.switch_page("scenarios.py").run()
    for k in state.FEATURED:
        at.radio(key="scen_pick").set_value(k).run()
        frames = [f.proto.srcdoc for f in ok(at).get("iframe")]
        assert len(frames) == 1 and json.dumps(rd.pivot_data(views[k])) in frames[0], k
        assert len(at.get("plotly_chart")) == 2                                               # the plan, the map
