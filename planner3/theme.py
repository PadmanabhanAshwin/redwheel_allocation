"""The look of the planner, shared with the deck (docs/deck): one palette, one type face, and the few HTML pieces
Streamlit has no element for (page header, headline numbers, chart legend).

Colour carries meaning, the same everywhere:
  INK     the plan                       ACCENT  the target (dashed), and what sets a date
  REF     the scenario compared with     FULL    weeks a line builds at full capacity
  EVENT   weeks an event changes numbers"""
from __future__ import annotations

import html

import streamlit as st

INK, MUTED, FAINT, GRID, AXIS = "#1F2933", "#5F6B7A", "#9AA3AE", "#E4E7EB", "#C5CBD3"
ACCENT = "#D9480F"
FULL = "#E6EAF0"            # band: the line builds at full capacity
EVENT = "#FBE3D6"           # band: an event changes numbers in these weeks
REF = "#AEB6C1"             # the scenario a plan is compared with
TINT = "#F4F5F7"            # neutral emphasis in tables
BELOW = "#FBE3D6"           # a table cell below target (always with a ▼)
FONT = '"Helvetica Neue", Helvetica, Arial, sans-serif'

CSS = f"""
<style>
html, body, [class*="st-"], .stMarkdown, .stDataFrame, button, input, textarea, select {{font-family: {FONT};}}
[data-testid="stIconMaterial"] {{font-family: "Material Symbols Rounded" !important;}}
h1, h2, h3, h4 {{font-family: {FONT} !important; color: {INK};}}
.block-container {{padding-top: 3.6rem; padding-bottom: 4rem; max-width: 1320px;}}
h1 {{font-size: 2.05rem !important; font-weight: 500 !important; letter-spacing: -0.02em; padding: 0 0 0.1rem 0 !important;}}
h3 {{font-size: 1.12rem !important; font-weight: 600 !important; padding-top: 0.6rem !important;}}
.p3-q {{color: {ACCENT}; font-size: 0.86rem; font-weight: 500; letter-spacing: 0.01em; margin-bottom: -0.5rem;}}
.p3-sub {{color: {MUTED}; font-size: 0.95rem; line-height: 1.45; margin-top: -0.3rem; max-width: 96ch;}}
.p3-rules {{color: {FAINT}; font-size: 0.8rem; margin-top: 0.15rem;}}
.p3-verdict {{font-size: 1.12rem; line-height: 1.55; color: {INK}; max-width: 100ch; margin: 0.4rem 0 0.2rem 0;}}
.p3-chip {{display: inline-block; background: {EVENT}; color: {INK}; border-radius: 4px; padding: 0.12rem 0.5rem;
          font-size: 0.82rem; margin: 0.3rem 0.4rem 0 0;}}
.p3-kpis {{display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.8rem; margin: 0.9rem 0 0.4rem 0;}}
.p3-kpi {{border: 1px solid {GRID}; border-radius: 8px; padding: 0.75rem 0.95rem 0.7rem 0.95rem;}}
.p3-kpi .l {{color: {MUTED}; font-size: 0.8rem;}}
.p3-kpi .v {{color: {INK}; font-size: 1.65rem; font-weight: 500; letter-spacing: -0.01em; line-height: 1.25;
            margin-top: 0.15rem;}}
.p3-kpi .s {{color: {MUTED}; font-size: 0.78rem; line-height: 1.35; margin-top: 0.2rem;}}
.p3-kpi .bad {{color: {ACCENT};}}
.p3-note {{color: {MUTED}; font-size: 0.84rem; line-height: 1.45; max-width: 110ch;}}
div[data-testid="stTabs"] button p {{font-size: 0.98rem; font-weight: 500;}}
.p3-tw {{overflow-x: auto; border: 1px solid {GRID}; border-radius: 8px; margin: 0.3rem 0 0.5rem 0;}}
.p3-t {{border-collapse: separate; border-spacing: 0; width: 100%; font-size: 0.84rem; color: {INK};
       font-variant-numeric: tabular-nums;}}
.p3-t th {{color: {MUTED}; font-weight: 500; text-align: right; padding: 0.45rem 0.5rem; white-space: nowrap;
          border-bottom: 1px solid {GRID}; background: white;}}
.p3-t td {{text-align: right; padding: 0.34rem 0.5rem; white-space: nowrap; border-bottom: 1px solid #F1F2F4;
          background: white;}}
.p3-t .l {{text-align: left;}}
.p3-t th:first-child, .p3-t td:first-child {{position: sticky; left: 0; z-index: 1;}}
.p3-t thead tr.grp th {{color: {INK}; font-weight: 600; text-align: center; border-bottom: 1px solid {GRID};
                       padding-bottom: 0.2rem;}}
.p3-t thead tr.grp th.blank {{border-bottom: none;}}
.p3-t tr.section td {{color: {MUTED}; font-size: 0.74rem; font-weight: 600; letter-spacing: 0.06em;
                     text-transform: uppercase; padding-top: 0.7rem; border-bottom: none;}}
.p3-t tr.cap td {{color: {MUTED}; font-size: 0.8rem; border-top: 1px solid {GRID};}}
.p3-t tr.cap td:first-child {{color: {INK}; font-weight: 600; font-size: 0.84rem;}}
.p3-t tr.total td {{font-weight: 600; border-top: 1px solid {AXIS};}}
.p3-t tr.grand td {{font-weight: 700; border-top: 2px solid {INK};}}
.p3-t tr.em td {{background: {TINT}; font-weight: 600;}}
.p3-t td.full {{background: {FULL};}}
.p3-t td.below {{background: {BELOW};}}
.p3-t td.sub {{padding-left: 1.5rem;}}
.p3-t td.muted {{color: {MUTED};}}
.p3-t td.accent {{color: {ACCENT}; font-weight: 700;}}
.p3-t td.wrap {{white-space: normal; min-width: 18rem;}}
.p3-t td.wraps {{white-space: normal; min-width: 9rem;}}
.p3-t td.bad {{color: {ACCENT}; font-weight: 600;}}
.p3-key {{display: flex; flex-wrap: wrap; gap: 0.35rem 1.3rem; color: {MUTED}; font-size: 0.8rem; margin: 0.2rem 0 0 0;}}
.p3-key span {{display: inline-flex; align-items: center; gap: 0.4rem;}}
.p3-key i {{display: inline-block; width: 16px; height: 12px; border-radius: 2px;}}
</style>
"""


def inject():
    st.html(CSS)


def esc(text) -> str:
    return html.escape(str(text), quote=True)


def header(title: str, question: str, sub: str = "", rules: str = ""):
    """The page's question (accent), the title, a line under it and, smaller, the rules it runs under."""
    st.markdown(f"<div class='p3-q'>{esc(question)}</div>", unsafe_allow_html=True)
    st.title(title)
    if sub:
        st.markdown(f"<div class='p3-sub'>{esc(sub)}</div>", unsafe_allow_html=True)
    if rules:
        st.markdown(f"<div class='p3-rules'>{esc(rules)}</div>", unsafe_allow_html=True)


def kpis(cards: list):
    """cards: [(label, value, sub, bad)]; bad marks the sub-line in the accent colour."""
    cells = "".join(f"<div class='p3-kpi'><div class='l'>{esc(label)}</div><div class='v'>{esc(value)}</div>"
                    f"<div class='s{' bad' if bad else ''}'>{esc(sub)}</div></div>" for label, value, sub, bad in cards)
    st.markdown(f"<div class='p3-kpis'>{cells}</div>", unsafe_allow_html=True)


def key(items: list):
    """The grid's colour key: [(colour, label)], or (colour, label, outline) for an outlined swatch."""
    sw = []
    for it in items:
        color, label = it[0], it[1]
        border = f"border: 2px solid {it[2]};" if len(it) > 2 else ""
        sw.append(f"<span><i style='background:{color}; {border}'></i>{esc(label)}</span>")
    st.markdown("<div class='p3-key'>" + "".join(sw) + "</div>", unsafe_allow_html=True)


def table(df, left: int = 1, rows=None, cells=None, key: str = "", groups=None):
    """A table of display text in the deck's style: the first `left` columns are labels (left-aligned; the first
    stays in view when the table scrolls sideways), the rest right-aligned.
    rows: a class per row: 'section' (a heading across the table, from the first column), 'cap' (a line's capacity),
    'total', 'grand', 'em' (emphasis). cells: a frame of the same shape with a class per cell: 'full', 'below',
    'sub' (indented), 'muted', 'accent', 'wrap'. groups: [(label, number of columns)] for a header row above the
    column names. key: a class on the wrapper, so tests can find the table."""
    rows = rows or [""] * len(df)
    head = ""
    if groups:
        head += "<tr class='grp'>" + "".join(f"<th colspan='{n}' class='{'' if g else 'blank'}'>{esc(g)}</th>"
                                             for g, n in groups) + "</tr>"
    head += "<tr>" + "".join(f"<th class='{'l' if j < left else ''}'>{esc(c.strip())}</th>"
                             for j, c in enumerate(df.columns)) + "</tr>"
    body = []
    for i in range(len(df)):
        if rows[i] == "section":
            body.append(f"<tr class='section'><td class='l' colspan='{len(df.columns)}'>{esc(df.iat[i, 0])}</td></tr>")
            continue
        tds = []
        for j, c in enumerate(df.columns):
            cls = " ".join(x for x in ["l" if j < left else "", "" if cells is None else str(cells.iat[i, j])] if x)
            tds.append(f"<td class='{cls}'>{esc(df.iat[i, j])}</td>")
        body.append(f"<tr class='{rows[i]}'>{''.join(tds)}</tr>")
    st.markdown(f"<div class='p3-tw {key}'><table class='p3-t'><thead>{head}</thead>"
                f"<tbody>{''.join(body)}</tbody></table></div>", unsafe_allow_html=True)


def note(text: str):
    st.markdown(f"<div class='p3-note'>{text}</div>", unsafe_allow_html=True)
