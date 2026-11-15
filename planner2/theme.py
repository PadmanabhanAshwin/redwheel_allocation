"""A few style rules on top of the Streamlit theme: page width and rhythm, eyebrow and subtitle text, card spacing."""
import streamlit as st

CSS = """
<style>
.block-container {padding-top: 4.4rem; padding-bottom: 4rem; max-width: 1380px;}
h1 {font-size: 2.15rem !important; letter-spacing: -0.01em; padding-bottom: 0.15rem !important;}
h2 {font-size: 1.45rem !important; letter-spacing: -0.005em;}
h3 {font-size: 1.15rem !important;}
.rw-eyebrow {font-size: 0.76rem; letter-spacing: 0.07em; text-transform: uppercase; color: #6b6a66;
             font-weight: 600; margin-bottom: -0.55rem; min-height: 1rem;}
.rw-sub {color: #45443f; font-size: 1.0rem; line-height: 1.5; margin-top: -0.35rem; margin-bottom: 0.4rem;
         max-width: 92ch; min-height: 0.2rem;}
.rw-muted {color: #6b6a66; font-size: 0.9rem;}
.rw-step {font-size: 0.78rem; font-weight: 700; color: #2a78d6; letter-spacing: 0.05em; text-transform: uppercase;}
div[data-testid="stMetric"] {padding: 0.6rem 0.8rem;}
div[data-testid="stMetricValue"] {font-size: 1.65rem;}
div[data-testid="stTabs"] button p {font-size: 0.98rem; font-weight: 500;}
/* cards on Home: name, badges, summary, numbers, actions */
.rw-nums {display: flex; gap: 1.2rem; margin: 0.2rem 0 0.4rem 0;}
.rw-nums div {font-size: 0.82rem; color: #6b6a66; line-height: 1.25;}
.rw-nums b {display: block; font-size: 1.02rem; color: #0b0b0b; font-weight: 600; margin-top: 0.15rem;}
/* What-if: the review panel stays in view while the settings scroll */
div[data-testid="stColumn"]:has(.st-key-review) {align-self: stretch;}
.st-key-review {position: sticky; top: 4.2rem; z-index: 2; max-height: calc(100vh - 5rem); overflow-y: auto;}
.rw-clamp {display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
           color: #6b6a66; font-size: 0.88rem; line-height: 1.45; min-height: 3.9rem; margin-bottom: 0.3rem;}
</style>
"""


def inject():
    st.html(CSS)
