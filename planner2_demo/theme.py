"""Style rules on top of the Streamlit theme: page width, headings, the headline cards, the assumptions strip, the
change lines."""
import streamlit as st

CSS = """
<style>
.block-container {padding-top: 4.2rem; padding-bottom: 4rem; max-width: 1380px;}
h1 {font-size: 2.0rem !important; letter-spacing: -0.01em; padding-bottom: 0.1rem !important;}
h3 {font-size: 1.12rem !important; padding-top: 0.7rem !important;}
div[data-testid="stMetric"] {padding: 0.55rem 0.8rem;}
.rw-change {margin: 0.15rem 0; font-size: 0.95rem;}
.rw-strip {display: flex; flex-wrap: wrap; gap: 0.4rem 2rem; margin: 0.2rem 0 0.6rem 0; font-size: 0.92rem;}
.rw-strip span {display: block; color: #6b6a66; font-size: 0.75rem; letter-spacing: 0.04em;}
.rw-strip em {font-style: normal; font-size: 0.78rem; border-radius: 1rem; padding: 0.02rem 0.45rem; margin-left: 0.2rem;}
.rw-strip em.bad {background: #fde8e6; color: #b42318;}
.rw-strip em.good {background: #e4f4e8; color: #1e7b3a;}
.rw-strip em.same, .rw-strip em.neutral {background: #f0f0ee; color: #6b6a66;}
.rw-change .n {color: #6b6a66; font-size: 0.85rem;}
.rw-strip.rw-set {font-size: 0.84rem; color: #4a4946; margin-top: -0.1rem;}
.rw-strip.rw-set span {font-size: 0.7rem;}
.st-key-scen_pick + div h3, .st-key-scen_pick ~ div h3 {padding-top: 0.1rem !important;}
div[data-testid="stTabs"] button p {font-size: 0.98rem; font-weight: 500;}
/* the scenario picker on Scenarios, drawn as tabs */
.st-key-scen_pick div[role="radiogroup"] {gap: 0 1.8rem; border-bottom: 1px solid #e6e6e3; width: 100%;
                                          margin-bottom: 0.2rem;}
.st-key-scen_pick label[data-baseweb="radio"] {padding: 0.3rem 0 0.5rem 0; margin: 0 0 -1px 0; cursor: pointer;
                                               border-bottom: 2px solid transparent;}
.st-key-scen_pick label[data-baseweb="radio"] > div:first-child {display: none;}
.st-key-scen_pick label[data-baseweb="radio"]:has(input:checked) {border-bottom-color: #2a78d6;}
.st-key-scen_pick label[data-baseweb="radio"]:has(input:checked) p {color: #2a78d6;}
.st-key-scen_pick label p {font-size: 0.98rem; font-weight: 500;}
</style>
"""


def inject():
    st.html(CSS)
