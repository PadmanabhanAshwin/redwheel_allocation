"""Redwheel build planner — scenario-first UI.   Run:  streamlit run planner2/app.py

Pages: Home (what this is, where things stand, the scenarios) · Scenario (one plan in depth) · What-if (make or
change a scenario, in words or directly) · Compare (scenarios side by side) · Reference (data and model pages from
the first UI, unchanged). The engine and its settings are shared with the other UIs (app/, planner/)."""
import sys
from pathlib import Path

import streamlit as st

HERE = Path(__file__).parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "app")]   # the planner2 package, then the first UI's shared module

st.set_page_config(page_title="Redwheel planner", layout="wide", page_icon=":material/pedal_bike:",
                   initial_sidebar_state="collapsed")

from planner2 import state   # noqa: E402
from planner2 import theme   # noqa: E402

theme.inject()
state.init()
st.navigation({
    "": [st.Page("home.py", title="Home", icon=":material/home:", default=True),
                st.Page("scenario.py", title="Scenario", icon=":material/insights:"),
                st.Page("whatif.py", title="What-if", icon=":material/tune:"),
                st.Page("compare.py", title="Compare", icon=":material/compare_arrows:")],
    "Reference": [st.Page("ref_context.py", title="Supply–Demand Context", icon=":material/show_chart:"),
                  st.Page("ref_demand.py", title="Demand Sources", icon=":material/map:"),
                  st.Page("ref_model.py", title="Object Encoding", icon=":material/hub:"),
                  st.Page("ref_validation.py", title="Model Validation", icon=":material/verified:")],
}, position="top").run()
