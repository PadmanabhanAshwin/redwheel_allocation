"""Redwheel planner — three views, one question each.

    streamlit run planner3/app.py --theme.primaryColor=#1F2933 --client.toolbarMode=viewer

Plan (what do we build, and does it hit target?) · What-if (something changes: what moves?) · Model (how was it
computed, and why trust it?). Same engine, scenarios and saved files as planner2/; the look is the deck's."""
import sys
from pathlib import Path

import streamlit as st

HERE = Path(__file__).parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "app")]   # the planner packages, then the first UI's shared module

st.set_page_config(page_title="Redwheel planner", layout="wide", page_icon=":material/pedal_bike:",
                   initial_sidebar_state="collapsed")

from planner2 import state   # noqa: E402
from planner3 import theme   # noqa: E402

theme.inject()
state.init()
st.navigation([st.Page("plan.py", title="Plan", icon=":material/insights:", default=True)], position="top").run()
