"""Shared state and helpers for the planner UI: the cached plan run, styling, formatting."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from redwheel import aux_fns, rtn
from redwheel.utils import DQ

# Colour follows the entity: bike size. Black, bronze and gold differ by lightness, so they stay
# distinguishable without colour vision; every chart also carries a legend.
SIZE_COLOR = {"S": "#262420", "M": "#8f6b16", "L": "#d9b44a"}
GOOD_BG, BAD_BG = "#e3f1e7", "#fbe4e1"          # status tints, always paired with a text marker
INK, MUTED, GRID = "#0b0b0b", "#6b6a66", "#e7e6e2"
HISTORY, FORECAST, CAPACITY, TARGET = "#a3a29c", "#2a78d6", "#0b0b0b", "#0b0b0b"
LINES = ["road-base", "road-carbon", "mtb-base", "mtb-carbon"]
LINE_NAME = {"road-base": "Road · base", "road-carbon": "Road · carbon",
             "mtb-base": "MTB · base", "mtb-carbon": "MTB · carbon"}
GROUP_NAME = {"road": "Road (8 weeks; 10 from Jan 2028)", "mtb_base": "MTB base (12 weeks)",
              "mtb_carbon": "MTB carbon (15 weeks)"}


@st.cache_resource(show_spinner="Running the plan: master data → network → optimisation → whole bikes …")
def load():
    r = aux_fns.run_plan()
    return r, aux_fns.plan_checks(r), dict(DQ), aux_fns.compare_plans(r)


r, checks, dq_log, compare = load()
m, obj = r["m"], r["obj"]
H = len(obj.weeks)
WEEKS = obj.weeks.set_index("t")["week_start"]
SNAP = WEEKS.iloc[0]
SKU = m["dim_sku"].set_index("sku")
SKUS_BY_LINE = {ln: list(SKU.index[SKU["line_id"] == ln]) for ln in LINES}
ORDER = [s for ln in LINES for s in sorted(SKUS_BY_LINE[ln], key=lambda x: "SML".index(SKU.at[x, "size"]))]
CAP = {ln: obj.arrivals.loc[f"capacity||RENO/{ln}", 1:H].to_numpy() for ln in LINES}
BUILD = {s: r["builds"].loc[f"make|{s}|RENO/{SKU.at[s, 'line_id']}"].to_numpy() for s in SKU.index}
# At target in a week = net position >= the next N weeks of forecast, in units (as in the plan).
AT_TARGET = r["net"].loc[ORDER, 1:H] >= r["target_units"].loc[ORDER] - 1e-6

# Fiscal quarters (FY runs September-August; a week belongs to the month of its Monday).
_fy = WEEKS.dt.year - (WEEKS.dt.month < 9)
_q = (WEEKS.dt.month - 9) % 12 // 3 + 1
FQ = ("FY" + (_fy % 100).astype(str) + " Q" + _q.astype(str))             # week t -> 'FY26 Q1'
FQ_ORDER = list(dict.fromkeys(FQ))
FQ_SPAN = {q: f"{WEEKS[FQ == q].iloc[0].strftime('%b %y')}–{WEEKS[FQ == q].iloc[-1].strftime('%b %y')}"
           for q in FQ_ORDER}
FQ_END = {q: int(FQ.index[FQ == q].max()) for q in FQ_ORDER}             # last week of each quarter


def sku_label(s):
    return f"{s} — {LINE_NAME[SKU.at[s, 'line_id']]}, size {SKU.at[s, 'size']}"


def style(fig, height, ytitle=None, legend=True):
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=40, b=8), plot_bgcolor="white",
                      paper_bgcolor="white", font=dict(color=INK, size=12), hovermode="x unified",
                      showlegend=legend, legend=dict(orientation="h", y=1.06, x=0, yanchor="bottom"))
    fig.update_xaxes(showgrid=False, linecolor=GRID, ticks="outside", tickcolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor="#c9c8c2", title_text=ytitle, title_font=dict(color=MUTED))
    fig.update_annotations(font=dict(size=13, color=INK))
    return fig


def line_grid():
    return make_subplots(rows=2, cols=2, subplot_titles=[LINE_NAME[ln] for ln in LINES],
                         shared_xaxes=True, vertical_spacing=0.12, horizontal_spacing=0.06)


def cell(i):
    return dict(row=i // 2 + 1, col=i % 2 + 1)


def fmt_date(d):
    return pd.Timestamp(d).strftime("%-d %b %Y")


def table(df, ints=(), dec1=(), height=None):
    """Thousands separators on whole numbers, one decimal on weeks of supply."""
    fmt = {c: "{:,.0f}" for c in ints}
    fmt.update({c: "{:,.1f}" for c in dec1})
    kw = dict(hide_index=True, width="stretch")
    if height:
        kw["height"] = height
    st.dataframe(df.style.format(fmt), **kw)


def status_table(df, ints=(), dec1=(), good=None, height=None, right=()):
    """Like table(), plus status shading: good = {column: boolean array}, True -> green tint, False -> red.
    right: text columns holding numbers, to be right-aligned."""
    fmt = {c: "{:,.0f}" for c in ints}
    fmt.update({c: "{:,.1f}" for c in dec1})
    if right:
        df = df.copy()
        df[list(right)] = right_align(df[list(right)])
    sty = df.style.format(fmt)
    for col, ok in (good or {}).items():
        css = [f"background-color: {GOOD_BG if v else BAD_BG}" for v in ok]
        sty = sty.apply(lambda _, css=css: css, subset=[col], axis=0)
    kw = dict(hide_index=True, width="stretch")
    if height:
        kw["height"] = height
    st.dataframe(sty, **kw)


SIZE_RANK = {"S": 1, "M": 2, "L": 3}


def network_figure(s):
    """Two lanes: Reno on top, Columbus below, the transfer between them; customers on the right."""
    ln = SKU.at[s, "line_id"]
    g = rtn.to_networkx(obj)
    sg = g.subgraph([n for n, d in g.nodes(data=True) if d.get("item") == s or n == f"capacity||RENO/{ln}"])
    cust = ["WEB", "DEALERS", "COMMERCIAL"]
    cust_name = {"WEB": "DTC", "DEALERS": "dealers", "COMMERCIAL": "commercial"}

    def place(n):
        d = sg.nodes[n]
        if d["node"] == "resource":
            if d["kind"] == "capacity":
                return 0, 1.2
            if d["kind"] == "order":
                return 7.6, 0.7 - 0.7 * cust.index(d["location"])
            return {"RENO": (2, 1.2), "RENO>CMH": (4, 0), "CMH": (5, -1.2), "DEALERS": (7.6, -2.5)}[d["location"]]
        if d["kind"] == "make":
            return 1, 1.2
        if d["kind"] == "move":
            return 3, 0
        site, c = n.split("|")[2].split(">")
        k = cust.index(c)
        return 6.2, (2.3 - 0.6 * k) if site == "RENO" else (-1.1 - 0.6 * k)

    pos = {n: place(n) for n in sg.nodes}
    fig = go.Figure()
    for u, v, d in sg.edges(data=True):
        (x0, y0), (x1, y1) = pos[u], pos[v]
        if sg.has_edge(v, u):                       # move <-> in transit: draw the pair side by side
            off = 0.09 if d["amount"] > 0 else -0.09
            y0, y1 = y0 + off, y1 + off
        col = INK if d["amount"] > 0 else HISTORY
        fig.add_annotation(x=x1, y=y1, ax=x0, ay=y0, xref="x", yref="y", axref="x", ayref="y", showarrow=True,
                           arrowhead=2, arrowsize=1, arrowwidth=1.4, arrowcolor=col, standoff=13, startstandoff=13)
        if d["delay"]:
            fig.add_annotation(x=(x0 + x1) / 2, y=(y0 + y1) / 2, text=f"+{d['delay']} wk", showarrow=False,
                               yshift=-11, font=dict(size=10, color=MUTED))
    name = {"RENO": "Reno stock", "CMH": "Columbus stock", "RENO>CMH": "in transit", "DEALERS": "dealer stock"}
    res = [n for n in sg.nodes if sg.nodes[n]["node"] == "resource"]
    txt = []
    for n in res:
        d = sg.nodes[n]
        if d["kind"] == "capacity":
            txt.append(f"{LINE_NAME[ln]} line capacity")
        elif d["kind"] == "order":
            txt.append(f"{cust_name[d['location']]} orders ({obj.opening[n]:,.0f})")
        else:
            txt.append(f"{name[d['location']]} ({obj.opening[n]:,.0f})")
    right = [sg.nodes[n]["location"] in ("WEB", "DEALERS", "COMMERCIAL") or
             (sg.nodes[n]["kind"] == "inventory" and sg.nodes[n]["location"] == "DEALERS") for n in res]
    fig.add_scatter(x=[pos[n][0] for n in res], y=[pos[n][1] for n in res], mode="markers+text",
                    marker=dict(size=22, color="white", line=dict(color=FORECAST, width=2.5)),
                    text=txt, textposition=["middle right" if rt else "bottom center" for rt in right],
                    hovertext=res, hoverinfo="text")
    ts = [n for n in sg.nodes if sg.nodes[n]["node"] == "task"]
    tlabel = [("fulfil · " + cust_name[n.split(">")[1]]) if n.startswith("fulfil") else n.split("|")[0] for n in ts]
    fig.add_scatter(x=[pos[n][0] for n in ts], y=[pos[n][1] for n in ts], mode="markers+text",
                    marker=dict(size=13, color=INK, symbol="square"), text=tlabel, textposition="top center",
                    textfont=dict(size=11), hovertext=ts, hoverinfo="text")
    for x, y, t in [(4.1, 2.75, "Reno"), (4.1, -2.75, "Columbus")]:
        fig.add_annotation(x=x, y=y, text=t, showarrow=False, font=dict(size=12, color=MUTED))
    fig.update_layout(height=560, margin=dict(l=8, r=8, t=8, b=8), plot_bgcolor="white", paper_bgcolor="white",
                      showlegend=False, xaxis=dict(visible=False, range=[-0.7, 9.6]),
                      yaxis=dict(visible=False, range=[-3.0, 3.0]), font=dict(color=INK, size=12))
    return fig


# ---------------- planning grid (page 1 hero view) ----------------
GRANULARITY = ["Month", "Quarter", "Fiscal year"]


def periods(gran: str) -> pd.Series:
    """Week t -> period label, in time order. Fiscal year = September-August; a week counts in its Monday's month."""
    if gran == "Month":
        return WEEKS.dt.strftime("%b %Y")
    if gran == "Quarter":
        return FQ
    fy = WEEKS.dt.year - (WEEKS.dt.month < 9)
    n = fy.map(fy.value_counts())
    return fy.map(lambda y: f"FY{y}") + n.map(lambda k: "" if k >= 52 else " (Sep–Dec)")


HIGHLIGHT_BG = "#f6edd4"                          # neutral emphasis: the plan's output and its net result
HIGHLIGHT_ROWS = ("Builds", "Net inventory")


def plan_grid(skus: list, gran: str):
    """Rows = measures, columns = start + periods. Returns (display table, per-cell good/bad flags for shading).
    Builds and demand are period totals; on hand, open orders and net inventory are at the period end."""
    f = r["flows"]
    per = periods(gran)
    labels = list(dict.fromkeys(per))
    weeks_in = {p: per.index[per == p] for p in labels}
    last = {p: int(weeks_in[p].max()) for p in labels}
    lines = sorted({SKU.at[s, "line_id"] for s in skus})
    whole_lines = all(set(SKUS_BY_LINE[ln]) <= set(skus) for ln in lines)
    start = "Start · " + SNAP.strftime("%-d %b %Y")
    cols = [start] + labels

    def at_end(df):
        return {start: df.loc[skus, 0].sum(), **{p: df.loc[skus, last[p]].sum() for p in labels}}

    def in_period(df):
        return {start: None, **{p: df.loc[skus, weeks_in[p]].values.sum() for p in labels}}

    rows = {"Forecast demand": in_period(f["demand"]), "Builds": in_period(f["built"]),
            "On hand": at_end(f["on_hand"]), "Open orders": at_end(f["open_orders"]),
            "Net inventory": at_end(r["net"])}
    if whole_lines:
        cap = {p: sum(obj.arrivals.loc[f"capacity||RENO/{ln}", weeks_in[p]].sum() for ln in lines) for p in labels}
        rows["Capacity (used)"] = {start: None, **{p: f"{cap[p]:,.0f} ({rows['Builds'][p] / cap[p]:.0%})" for p in labels}}
    ok0 = (r["wos"].loc[skus, 0] >= r["target_wos"].loc[skus, 1])
    rows["% SKUs @ nominal inv."] = {start: f"{ok0.mean():.0%}",
                                     **{p: f"{AT_TARGET.loc[skus, last[p]].mean():.0%}" for p in labels}}
    flags = {"% SKUs @ nominal inv.": {start: bool(ok0.all()),
                                       **{p: bool(AT_TARGET.loc[skus, last[p]].all()) for p in labels}}}

    def fmt(v):
        return "" if v is None else v if isinstance(v, str) else f"{v:,.0f}"

    out = pd.DataFrame({c: [fmt(rows[k][c]) for k in rows] for c in cols}, index=list(rows))
    return out.rename_axis("Measure"), flags


def grid_view(table, flags, height=None):
    def shade(col):
        css = []
        for row in col.index:
            if row in flags:
                css.append(f"background-color: {GOOD_BG if flags[row][col.name] else BAD_BG}")
            elif row in HIGHLIGHT_ROWS:
                css.append(f"background-color: {HIGHLIGHT_BG}; font-weight: 600")
            else:
                css.append("")
        return css
    st.dataframe(right_align(table).style.apply(shade, axis=0), width="stretch", height=height or "auto")


FIGURE_SPACE = "\u2007"     # as wide as a digit: left-padding with it right-aligns numbers shown as text


def right_align(df):
    """The interactive table left-aligns text; pad each text column on the left to its longest entry."""
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == object:
            w = out[c].astype(str).str.len().max()
            out[c] = out[c].astype(str).map(lambda v: v.rjust(w, FIGURE_SPACE) if v else v)
    return out
