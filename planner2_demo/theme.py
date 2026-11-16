"""Style rules on top of the Streamlit theme: page width, headings, the measures and settings strips, the change lines,
the scenario summary and its picker."""
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
div[data-testid="stTabs"] button p {font-size: 0.98rem; font-weight: 500;}
/* Scenario Summary: the summary rows, and the panel that picks the scenario */
.rw-sum {display: grid; grid-template-columns: 6.6rem 1fr; gap: 0.6rem 1.2rem; align-items: baseline;
         margin: 0.2rem 0 0.8rem 0; font-size: 0.93rem; line-height: 1.45;}
.rw-sum > .k {color: #6b6a66; font-size: 0.72rem; letter-spacing: 0.07em; text-transform: uppercase;}
.rw-sum .sub {color: #4a4946; font-size: 0.86rem; margin-top: 0.15rem;}
.rw-sum .rw-strip {margin: 0;}
.rw-sum .lead {font-size: 1.0rem; color: #1f1f1d;}
.rw-delta {margin-top: 0.45rem; padding: 0.4rem 0.7rem; background: #fff6e8; border-left: 3px solid #e0a43a;
           border-radius: 4px; font-size: 0.9rem;}
.rw-delta > span {display: block; color: #8a5a12; font-size: 0.72rem; letter-spacing: 0.06em; text-transform: uppercase;}
.rw-tiles {display: grid; grid-template-columns: repeat(auto-fill, minmax(12.5rem, 1fr)); gap: 0.45rem;}
.rw-tiles > div {background: #f6f6f4; border-radius: 6px; padding: 0.35rem 0.6rem; font-size: 0.9rem; line-height: 1.3;}
.rw-tiles span {display: block; color: #6b6a66; font-size: 0.72rem; letter-spacing: 0.03em;}
.rw-chips {display: flex; flex-wrap: wrap; gap: 0.35rem; align-items: center;}
.rw-chips .chip {background: #edf3fb; color: #104281; border-radius: 1rem; padding: 0.1rem 0.6rem;
              font-size: 0.88rem;}
.rw-chips .note {color: #6b6a66; font-size: 0.8rem; margin-left: 0.2rem;}
.rw-steps {margin: 0.1rem 0 0 1.1rem; padding: 0; font-size: 0.9rem; color: #33322f;}
.rw-steps li {margin: 0;}
.st-key-scen_pick div[role="radiogroup"] {gap: 0.15rem;}
.st-key-scen_pick label[data-baseweb="radio"] {padding: 0.35rem 0.5rem; border-radius: 6px; margin: 0;}
.st-key-scen_pick label[data-baseweb="radio"]:has(input:checked) {background: #edf3fb;}
.st-key-scen_pick [data-testid="stCaptionContainer"] p {font-size: 0.82rem; line-height: 1.3;}
</style>
"""


def inject():
    st.html(CSS)
