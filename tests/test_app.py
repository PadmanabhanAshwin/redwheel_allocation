"""The single button and the UI: the plan's own checks pass, and every page runs through every control."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from redwheel import aux_fns
from redwheel import scenarios as sc

APP_DIR = Path(__file__).resolve().parents[1] / "app"
APP = str(APP_DIR / "app.py")
PAGES = {"views/context.py": "Supply–Demand Context", "views/scenario_list.py": "Scenarios",
         "views/scenario_compare.py": "Scenario Comparison", "views/object_encoding.py": "Object Encoding",
         "views/demand.py": "Demand Sources", "views/validation.py": "Model Validation"}
SCENARIO_PAGES = {"scenario_summary": "Summary", "network": "Network", "build_plan": "Build Plans", "build_score": "Build Score",
                  "balance": "Inventory Balance by SKU"}


def _scenario_page(module, key, app_dir):
    """One page of one scenario, run on its own (pages inside a scenario are functions, not files)."""
    import importlib
    import sys
    sys.path.insert(0, app_dir)
    importlib.import_module(f"views.{module}").render(key)


def scenario_app(module, key):
    return AppTest.from_function(_scenario_page, args=(module, key, str(APP_DIR)), default_timeout=120).run()


def test_run_plan_checks_all_pass():
    checks = aux_fns.plan_checks(aux_fns.run_plan())
    assert len(checks) == 10
    assert checks["pass"].all(), checks[~checks["pass"]].to_string()


@pytest.fixture(scope="module")
def app():
    return AppTest.from_file(APP, default_timeout=120).run()


@pytest.mark.parametrize("page, title", PAGES.items())
def test_page_renders_clean(app, page, title):
    app.switch_page(page).run()
    assert not app.exception, [e.message for e in app.exception]
    assert not app.error and not app.warning
    assert app.title[0].value == title


@pytest.mark.parametrize("key", list(sc.CASES))
@pytest.mark.parametrize("module, title", SCENARIO_PAGES.items())
def test_every_scenario_page_renders_clean(module, title, key):
    at = scenario_app(module, key)
    assert not at.exception, [e.message for e in at.exception]
    assert not at.error and not at.warning
    assert at.title[0].value == title
    assert sc.CASES[key].name in at.markdown[0].value               # the scenario is named above the title


@pytest.mark.parametrize("key", list(sc.CASES))
def test_network_page_every_sku(m, key):
    at = scenario_app("network", key)
    for s in m["dim_sku"]["sku"]:
        next(b for b in at.selectbox if b.label == "SKU").set_value(s).run()
        assert not at.exception, (key, s)


def test_network_settings_read_from_each_scenario():
    """The Network page's settings table comes from the scenario's own network and routing rule."""
    import importlib
    import sys
    sys.path.insert(0, str(APP_DIR))
    net = importlib.import_module("views.network")
    A, B = sc.run_case(sc.CASE_A), sc.run_case(sc.CASE_B)
    a, b = net.settings(A), net.settings(B)
    assert a.iloc[0] == "same week" and b.iloc[0] == "1 week" and a.iloc[1] == b.iloc[1] == "1 week"
    assert (a.iloc[2:] == "used").all()
    assert sorted(b.index[b == "used"]) == ["Ship: PDC → web orders", "Ship: Reno → commercial orders",
                                            "Ship: Reno → dealer orders"]


def test_build_score_planner_rule_on_scenario_a_only():
    at = scenario_app("build_score", "A")
    plan = next(r for r in at.radio if r.label == "Plan")
    for option in plan.options:
        plan.set_value(option).run()
        assert not at.exception, option
    assert not any(r.label == "Plan" for r in scenario_app("build_score", "B").radio)


@pytest.mark.parametrize("page", ["views/object_encoding.py"])
def test_every_sku_on_sku_pages(app, m, page):
    app.switch_page(page).run()
    box = next(b for b in app.selectbox if b.label == "SKU")
    for s in m["dim_sku"]["sku"]:
        box.set_value(s).run()
        assert not app.exception, (page, s)


@pytest.mark.parametrize("key", list(sc.CASES))
def test_planning_grid_every_scope_and_granularity(m, key):
    at = scenario_app("scenario_summary", key)
    scopes = ["All SKUs"] + [f"line:{ln}" for ln in m["dim_line"]["line_id"]] + list(m["dim_sku"]["sku"])
    for gran in ["Month", "Quarter", "Fiscal year"]:
        next(r for r in at.radio if r.label == "Granularity").set_value(gran).run()
        for s in scopes:
            next(b for b in at.selectbox if b.label == "Scope").set_value(s).run()
            assert not at.exception, (key, gran, s)


def test_every_master_table(app):
    app.switch_page("views/object_encoding.py").run()
    box = next(b for b in app.selectbox if b.label == "Table")
    for t in box.options:
        box.set_value(t).run()
        assert not app.exception, t
