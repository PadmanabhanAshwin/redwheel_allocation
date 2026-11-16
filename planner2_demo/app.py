"""Redwheel build planner.   Run:  streamlit run planner2_demo/app.py --client.toolbarMode=viewer

Scenario Summary (every scenario in one template, the landing page) · Compare (any two, one read against the other) · Try a
change (change a tunable, run, read it against its start; the live set on R+)."""
import sys
from pathlib import Path

import streamlit as st

HERE = Path(__file__).parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "app")]   # the planner2_demo package, then the first UI's shared module

st.set_page_config(page_title="Redwheel planner", layout="wide", page_icon=":material/pedal_bike:",
                   initial_sidebar_state="collapsed")

from planner2_demo import state   # noqa: E402
from planner2_demo import theme   # noqa: E402

theme.inject()
state.init()
st.navigation({"": [st.Page("scenarios.py", title="Scenario Summary", icon=":material/bar_chart:", default=True),
                     st.Page("compare.py", title="Compare", icon=":material/compare_arrows:"),
                     st.Page("whatif.py", title="Try a change", icon=":material/tune:")],
               "Context": [st.Page("context.py", title="Supply & demand", icon=":material/show_chart:"),
                           st.Page("object.py", title="Object", icon=":material/hub:")]},
              position="top").run()
