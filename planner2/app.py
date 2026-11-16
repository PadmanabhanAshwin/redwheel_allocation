"""Redwheel build planner.   Run:  streamlit run planner2/app.py --client.toolbarMode=viewer

Model (the object) · Scenarios (each featured scenario in one template) · Compare (side by side; the differences
between two) · Try a change (change a tunable, run, read it against its start)."""
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
st.navigation([st.Page("model.py", title="Model", icon=":material/hub:", default=True),
               st.Page("scenarios.py", title="Scenarios", icon=":material/insights:"),
               st.Page("compare.py", title="Compare", icon=":material/compare_arrows:"),
               st.Page("whatif.py", title="Try a change", icon=":material/tune:")], position="top").run()
