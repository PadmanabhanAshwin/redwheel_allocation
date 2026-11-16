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
div[data-testid="stTabs"] button p {font-size: 0.98rem; font-weight: 500;}
</style>
"""


def inject():
    st.html(CSS)
