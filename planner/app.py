"""Redwheel planner — scenario workbench.   Run:  streamlit run planner/app.py

A second UI, built around scenarios: pick one, change its planning priors, re-plan, compare. The first UI
(app/app.py) is unchanged; this one reuses its shared module (app/ui.py) and four of its pages."""
import runpy
import sys
from pathlib import Path

import streamlit as st

HERE = Path(__file__).parent
FIRST_UI = HERE.parent / "app"
sys.path[:0] = [str(HERE), str(FIRST_UI)]            # planner modules, then the first UI's shared module

st.set_page_config(page_title="Redwheel planner", layout="wide", page_icon=":material/conversion_path:")


def first_ui_page(name: str, title: str, slug: str) -> st.Page:
    """A page from the first UI, run as it is."""
    def page():
        runpy.run_path(str(FIRST_UI / "views" / f"{name}.py"))
    page.__name__ = slug
    return st.Page(page, title=title, url_path=slug)


st.navigation({
    "Plan": [st.Page("workbench.py", title="Workbench", icon=":material/tune:", default=True),
             st.Page("compare.py", title="Compare", icon=":material/compare_arrows:")],
    "Data": [first_ui_page("context", "Supply–Demand Context", "context"),
             first_ui_page("demand", "Demand Sources", "demand")],
    "Model": [first_ui_page("object_encoding", "Object Encoding", "object-encoding"),
              first_ui_page("validation", "Model Validation", "validation")],
}, position="top").run()
