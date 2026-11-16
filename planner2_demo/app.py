"""Redwheel build planner.   Run:  streamlit run planner2_demo/app.py --client.toolbarMode=viewer

Model (the object) · Scenario Summary (every scenario in one template) · Compare (any two, one read against the other) · Try a
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
st.navigation([st.Page("model.py", title="Model", icon=":material/hub:", default=True),
               st.Page("scenarios.py", title="Scenario Summary", icon=":material/bar_chart:"),
               st.Page("compare.py", title="Compare", icon=":material/compare_arrows:"),
               st.Page("whatif.py", title="Try a change", icon=":material/tune:")], position="top").run()
