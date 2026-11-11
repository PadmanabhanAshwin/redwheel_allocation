"""Shared state and helpers for the planner UI: the cached plan run, styling, formatting."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from redwheel import aux_fns, rtn, scenarios
from redwheel.utils import DQ

# Colour follows the entity: bike size. Black, bronze and gold differ by lightness, so they stay
# distinguishable without colour vision; every chart also carries a legend.
SIZE_COLOR = {"S": "#262420", "M": "#8f6b16", "L": "#d9b44a"}
CHANNELS = ["dealer", "dtc", "commercial"]
CHANNEL_NAME = {"dealer": "Dealers", "dtc": "Direct-to-consumer", "commercial": "Commercial"}
CHANNEL_COLOR = {"dealer": "#262420", "dtc": "#d9b44a", "commercial": "#8f6b16"}
SITE_NAME = {"RENO": "Reno", "CMH": "Columbus"}
GOOD_BG, BAD_BG = "#e3f1e7", "#fbe4e1"          # status tints, always paired with a text marker
INK, MUTED, GRID = "#0b0b0b", "#6b6a66", "#e7e6e2"
HISTORY, FORECAST, CAPACITY, TARGET = "#a3a29c", "#2a78d6", "#0b0b0b", "#0b0b0b"
CASE_COLOR = {"A": "#262420", "B": "#b8860b"}            # scenario A black, scenario B gold
LINES = ["road-base", "road-carbon", "mtb-base", "mtb-carbon"]
LINE_NAME = {"road-base": "Road · base", "road-carbon": "Road · carbon",
             "mtb-base": "MTB · base", "mtb-carbon": "MTB · carbon"}
GROUP_NAME = {"road": "Road (8 weeks; 10 from Jan 2028)", "mtb_base": "MTB base (12 weeks)",
              "mtb_carbon": "MTB carbon (15 weeks)"}


@st.cache_resource(show_spinner="Running the plan: master data → network → optimisation → whole bikes …")
def load():
    r = aux_fns.run_plan()
    return r, aux_fns.plan_checks(r), dict(DQ), aux_fns.compare_plans(r), aux_fns.demand_sources(r["m"])


@st.cache_resource(show_spinner="Running the scenarios …")
def load_cases():
    return {k: scenarios.run_case(c) for k, c in scenarios.CASES.items()}


r, checks, dq_log, compare, demand_src = load()
m, obj = r["m"], r["obj"]
H = len(obj.weeks)
WEEKS = obj.weeks.set_index("t")["week_start"]
SNAP = WEEKS.iloc[0]
SKU = m["dim_sku"].set_index("sku")
SKUS_BY_LINE = {ln: list(SKU.index[SKU["line_id"] == ln]) for ln in LINES}
ORDER = [s for ln in LINES for s in sorted(SKUS_BY_LINE[ln], key=lambda x: "SML".index(SKU.at[x, "size"]))]
CAP = {ln: obj.arrivals.loc[f"capacity||RENO/{ln}", 1:H].to_numpy() for ln in LINES}


# ---------------- scenarios: one control, one shape of results ----------------

def pool_label(pool: str) -> str:
    """'CMH+RENO' -> 'Reno + PDC'."""
    return " + ".join(scenarios.SHORT[s] for s in scenarios.SITES if s in pool.split("+"))


@st.cache_resource(show_spinner=False)
def scenario_view(key: str) -> dict:
    """One scenario's plan per SKU, the same shape for every scenario. A position is one SKU at one stock site
    (scenario A pools both sites); positions plus stock in transit add up to the SKU. A SKU is at target when
    every one of its positions is."""
    R = load_cases()[key]
    f = R["flows"]
    weeks = list(range(1, H + 1))

    def by_sku(df):
        return df.groupby(level="item").sum().reindex(ORDER)

    def by_task(df):
        return df.groupby(df.index.str.split("|").str[1]).sum().reindex(index=ORDER, columns=weeks, fill_value=0)

    prev_open = f["open_orders"][[t - 1 for t in weeks]].set_axis(weeks, axis=1)
    late = f["shipped"].where(f["shipped"] < prev_open, prev_open)        # oldest orders ship first, per position
    transit = R["transit"].reindex(ORDER).fillna(0)
    return {"key": key, "case": R["case"], "R": R, "pools": R["pools"], "multi": len(R["pools"]) > 1,
            "built": by_task(R["builds"]), "moved": by_task(R["moves"]),
            "demand": by_sku(f["demand"]), "shipped": by_sku(f["shipped"]), "late": by_sku(late),
            "on_hand": by_sku(f["on_hand"]), "open_orders": by_sku(f["open_orders"]), "transit": transit,
            "net": by_sku(R["net"]) + transit, "target_units": by_sku(R["target_units"]),
            "at_target": R["at_target"].groupby(level="item").all().reindex(ORDER),
            "start_ok": (R["wos"][0] >= R["target_wos"][1]).groupby(level="item").all().reindex(ORDER),
            "rules": scenarios.rules(R["case"]).set_index("Rule")["Setting"],
            "card": scenarios.scorecard(R), "checks": scenarios.checks(R)}


def scenario_header(key: str, title: str) -> dict:
    """Top of every page inside a scenario: the scenario's name above the page title, its key rules below."""
    V = scenario_view(key)
    st.markdown(f"<div style='color:{MUTED}; font-size:0.9rem; font-weight:600; letter-spacing:0.04em; "
                f"text-transform:uppercase; margin-bottom:-0.6rem'>{V['case'].name}</div>", unsafe_allow_html=True)
    st.title(title)
    rl = V["rules"]
    st.caption(f"Routing: {rl['Routing rule']} · Build time: {rl['Build time']} · Reno → PDC: "
               f"{rl['Reno → PDC transfer']} · The plan decides: {rl['The plan decides']}.")
    return V

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


UNUSED = "#cfcdc6"                                # routes the routing rule does not allow


def network_figure(s, o=None, routes=None, delays=True):
    """Two lanes: Reno on top, Columbus below, the transfer between them; customers on the right.
    o: the scenario's network (default: scenario A's). routes: allowed (site, customer) pairs; the others are drawn
    faded. delays: label edges with their delay (off for the shared view, where each scenario sets its own)."""
    o = obj if o is None else o
    ln = SKU.at[s, "line_id"]
    g = rtn.to_networkx(o)

    def unused(n):
        return (routes is not None and n.startswith("fulfil|")
                and tuple(n.split("|")[2].split(">")) not in set(routes))
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
        col = UNUSED if unused(u) or unused(v) else INK if d["amount"] > 0 else HISTORY
        fig.add_annotation(x=x1, y=y1, ax=x0, ay=y0, xref="x", yref="y", axref="x", ayref="y", showarrow=True,
                           arrowhead=2, arrowsize=1, arrowwidth=1.4, arrowcolor=col, standoff=13, startstandoff=13)
        if delays and d["delay"]:
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
            txt.append(f"{cust_name[d['location']]} orders ({o.opening[n]:,.0f})")
        else:
            txt.append(f"{name[d['location']]} ({o.opening[n]:,.0f})")
    right = [sg.nodes[n]["location"] in ("WEB", "DEALERS", "COMMERCIAL") or
             (sg.nodes[n]["kind"] == "inventory" and sg.nodes[n]["location"] == "DEALERS") for n in res]
    fig.add_scatter(x=[pos[n][0] for n in res], y=[pos[n][1] for n in res], mode="markers+text",
                    marker=dict(size=22, color="white", line=dict(color=FORECAST, width=2.5)),
                    text=txt, textposition=["middle right" if rt else "bottom center" for rt in right],
                    hovertext=res, hoverinfo="text")
    ts = [n for n in sg.nodes if sg.nodes[n]["node"] == "task"]
    tlabel = [("fulfil · " + cust_name[n.split(">")[1]]) if n.startswith("fulfil") else n.split("|")[0] for n in ts]
    fig.add_scatter(x=[pos[n][0] for n in ts], y=[pos[n][1] for n in ts], mode="markers+text",
                    marker=dict(size=13, color=[UNUSED if unused(n) else INK for n in ts], symbol="square"),
                    text=tlabel, textposition="top center",
                    textfont=dict(size=11, color=[MUTED if unused(n) else INK for n in ts]),
                    hovertext=[n + (" (not used: routing rule)" if unused(n) else "") for n in ts], hoverinfo="text")
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


def plan_grid(V: dict, skus: list, gran: str):
    """Rows = measures, columns = start + periods. Returns (display table, per-cell good/bad flags for shading).
    Builds and demand are period totals; on hand, in transit, open orders and net inventory are at the period end."""
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

    rows = {"Forecast demand": in_period(V["demand"]), "Builds": in_period(V["built"]),
            "On hand": at_end(V["on_hand"])}
    if "move" in V["case"].decides:
        rows["In transit to the PDC"] = at_end(V["transit"])
    rows.update({"Open orders": at_end(V["open_orders"]), "Net inventory": at_end(V["net"])})
    if whole_lines:
        cap = {p: sum(obj.arrivals.loc[f"capacity||RENO/{ln}", weeks_in[p]].sum() for ln in lines) for p in labels}
        rows["Capacity (used)"] = {start: None, **{p: f"{cap[p]:,.0f} ({rows['Builds'][p] / cap[p]:.0%})" for p in labels}}
    ok0, ok = V["start_ok"].loc[skus], V["at_target"].loc[skus]
    rows["% SKUs @ nominal inv."] = {start: f"{ok0.mean():.0%}", **{p: f"{ok[last[p]].mean():.0%}" for p in labels}}
    flags = {"% SKUs @ nominal inv.": {start: bool(ok0.all()), **{p: bool(ok[last[p]].all()) for p in labels}}}

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
