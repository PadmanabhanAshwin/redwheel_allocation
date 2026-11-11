"""Planner UI. Run: streamlit run app/app.py"""
import streamlit as st

from redwheel.config import PLAN_END, PLAN_START, POLICY

st.set_page_config(page_title="Redwheel build plan", layout="wide")
st.title("Redwheel build plan")
st.caption(f"Horizon {PLAN_START.date()} → {PLAN_END.date()}")
st.subheader("Targets (weeks of supply)")
st.table([{"group": g, "from": d, "target_wos": n} for g, d, n in POLICY])
