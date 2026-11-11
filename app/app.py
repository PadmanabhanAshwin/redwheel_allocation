"""Redwheel build plan — planner UI.   Run:  streamlit run app/app.py"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))       # pages import the shared ui module

st.set_page_config(page_title="Redwheel build plan", layout="wide")
st.navigation([
    st.Page("views/context.py", title="Supply–Demand Context", default=True),
    st.Page("views/demand.py", title="Demand Sources"),
    st.Page("views/build_plan.py", title="Build Plans"),
    st.Page("views/build_score.py", title="Build Score"),
    st.Page("views/balance.py", title="Inventory Balance by SKU"),
    st.Page("views/scenario_list.py", title="Scenarios"),
    st.Page("views/scenario_compare.py", title="Scenario Comparison"),
    st.Page("views/object_encoding.py", title="Object Encoding"),
    st.Page("views/validation.py", title="Model Validation"),
], position="top").run()
