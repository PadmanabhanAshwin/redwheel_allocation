"""The single button and the UI: the plan's own checks pass, and every page runs through every control."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from redwheel import aux_fns

APP = str(Path(__file__).resolve().parents[1] / "app" / "app.py")
PAGES = {"views/context.py": "Supply–Demand Context", "views/demand.py": "Demand Sources",
         "views/build_plan.py": "Build Plans",
         "views/build_score.py": "Build Score", "views/balance.py": "Inventory Balance by SKU",
         "views/scenario_list.py": "Scenarios", "views/scenario_compare.py": "Scenario Comparison",
         "views/object_encoding.py": "Object Encoding", "views/validation.py": "Model Validation"}


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


def test_build_score_both_methods(app):
    app.switch_page("views/build_score.py").run()
    for option in app.radio[0].options:
        app.radio[0].set_value(option).run()
        assert not app.exception, option


@pytest.mark.parametrize("page", ["views/object_encoding.py"])
def test_every_sku_on_sku_pages(app, m, page):
    app.switch_page(page).run()
    box = next(b for b in app.selectbox if b.label == "SKU")
    for s in m["dim_sku"]["sku"]:
        box.set_value(s).run()
        assert not app.exception, (page, s)


def test_planning_grid_every_scope_and_granularity(app, m):
    app.switch_page("views/context.py").run()
    scopes = ["All SKUs"] + [f"line:{ln}" for ln in m["dim_line"]["line_id"]] + list(m["dim_sku"]["sku"])
    for gran in ["Month", "Quarter", "Fiscal year"]:
        app.radio[0].set_value(gran).run()
        for sc in scopes:
            app.selectbox[0].set_value(sc).run()
            assert not app.exception, (gran, sc)


def test_every_master_table(app):
    app.switch_page("views/object_encoding.py").run()
    box = next(b for b in app.selectbox if b.label == "Table")
    for t in box.options:
        box.set_value(t).run()
        assert not app.exception, t
