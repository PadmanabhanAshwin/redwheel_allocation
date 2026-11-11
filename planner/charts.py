"""Charts and tables for the planner, each drawn from one scenario's view (ui.view_of). Kept from the first UI:
the Summarized Plan grid, the build chart, weeks of supply at quarter ends, the balance and its waterfall."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from redwheel import aux_fns
from ui import (BAD_BG, CAP, CAPACITY, FORECAST, FQ_END, FQ_ORDER, GOOD_BG, H, HIGHLIGHT_BG, INK, LINES, LINE_NAME,
                MUTED, ORDER, SIZE_COLOR, SIZE_RANK, SKU, SKUS_BY_LINE, WEEKS, cell, fmt_date, line_grid, m, obj,
                pool_label, status_table, style)

BACKLOG_BG = "#bdbbb4"
BAR_W = 26 * 24 * 3600 * 1000            # bar width in ms (date axis): about 26 days
MONTH = pd.Series(WEEKS.dt.to_period("M").values, index=WEEKS.index)
MONTHS = MONTH.unique()
X = [p.to_timestamp() for p in MONTHS]
MONTH_END = [int(MONTH.index[MONTH == p].max()) for p in MONTHS]
FY = WEEKS.dt.year - (WEEKS.dt.month < 9)


def by_month(weekly):
    return pd.Series(weekly, index=WEEKS.index).groupby(MONTH.values).sum().reindex(MONTHS).to_numpy()


def weeks_between(a, b):
    return round((b - a).days / 7)


# ---------------- headline results ----------------

def kpis(V, V0=None):
    """Headline results; with V0, the change against that scenario under each number."""
    card = V["card"]
    c0 = V0["card"] if V0 is not None else None
    name0 = f"vs {V0['case'].key}" if V0 is not None else ""
    moves = "move" in V["case"].decides
    cols = st.columns(5)

    def dweeks(k):
        if c0 is None or card[k] is None or c0[k] is None:
            return None
        w = weeks_between(c0[k], card[k])
        return f"{w:+d} week{'s' if abs(w) != 1 else ''} {name0}" if w else None

    held, cleared = card["All targets held from"], card["Open orders cleared from"]
    cols[0].metric("All targets held from", fmt_date(held) if held is not None else "never",
                   dweeks("All targets held from"), delta_color="inverse",
                   help="First week from which every SKU is at its weeks-of-supply target to the end of the horizon")
    cols[1].metric("Open orders cleared from", fmt_date(cleared) if cleared is not None else "never",
                   dweeks("Open orders cleared from"), delta_color="inverse", help="First week with no order waiting")
    fill = card["On-time fill rate"]
    df = None if c0 is None or abs(fill - c0["On-time fill rate"]) < 5e-4 else \
        f"{(fill - c0['On-time fill rate']) * 100:+.1f} pts {name0}"
    cols[2].metric("On-time fill rate", f"{fill:.1%}", df, help="Forecast demand shipped in the week it arrives")
    below = card["Position-weeks below target"]
    db = None if c0 is None or below == c0["Position-weeks below target"] else \
        f"{below - c0['Position-weeks below target']:+,} {name0}"
    cols[3].metric("Weeks below target", f"{below:,}", db, delta_color="inverse",
                   help="Summed over SKUs at each stock site (a position is one SKU at one site)")
    cols[4].metric("Transfers to the PDC" if moves else "Bikes built",
                   f"{card['Bikes transferred to the PDC'] if moves else card['Bikes built']:,}",
                   help=(f"About {card['Average bikes in transit']:,.0f} bikes in transit in an average week" if moves
                         else "Over the whole horizon"))


# ---------------- builds ----------------

def build_chart(V, key):
    fig = line_grid()
    shown = set()
    for i, ln in enumerate(LINES):
        sk = SKUS_BY_LINE[ln]
        first = i == 0
        backlog = V["open_orders"].loc[sk, MONTH_END].sum().to_numpy()
        fig.add_bar(x=X, y=backlog, width=BAR_W, name="open orders (month end)", marker_color=BACKLOG_BG,
                    marker_line_width=0, legendgroup="o", legendrank=4, showlegend=first,
                    hovertemplate="open orders: %{y:,.0f}<extra></extra>", **cell(i))
        total = 0
        for s in [k for k in ORDER if k in sk]:
            size = SKU.at[s, "size"]
            y = by_month(V["built"].loc[s].to_numpy())
            fig.add_bar(x=X, y=y, base=total, name=f"size {size}", marker_color=SIZE_COLOR[size], marker_line_width=0,
                        width=BAR_W * 0.6, legendgroup=size, legendrank=SIZE_RANK[size], showlegend=size not in shown,
                        hovertemplate=f"{s} built: %{{y:,.0f}}<extra></extra>", **cell(i))
            total = total + y
            shown.add(size)
        cap = by_month(CAP[ln])
        fc = by_month(V["demand"].loc[sk].sum().to_numpy())
        fig.add_scatter(x=X, y=cap, name="capacity", mode="markers", legendgroup="c", legendrank=5, showlegend=first,
                        marker=dict(symbol="line-ew", size=16, line=dict(color=CAPACITY, width=2)),
                        hovertemplate="capacity: %{y:,.0f}<extra></extra>", **cell(i))
        fig.add_scatter(x=X, y=fc, name="forecast", mode="lines", line=dict(color=FORECAST, width=2), legendgroup="f",
                        legendrank=6, showlegend=first, hovertemplate="forecast: %{y:,.0f}<extra></extra>", **cell(i))
        fig.update_yaxes(range=[0, max(cap.max(), fc.max(), backlog.max(), total.max()) * 1.08], **cell(i))
    fig.update_yaxes(title_text="bicycles per month", col=1)
    fig.update_layout(barmode="overlay")
    st.plotly_chart(style(fig, 600), key=f"build_{key}")
    st.caption("Monthly totals (a week counts in the month of its Monday). Coloured bars: builds by size. Grey bar "
               "behind: open orders still waiting at month end. Black dash: the month's capacity; builds reaching it "
               "mean the line ran full. Blue: forecast.")


def build_downloads(V, key):
    bp = aux_fns.build_plan_table(obj, V["R"]["builds"])
    c = st.columns(2)
    c[0].download_button("Weekly build plan (CSV)", bp.to_csv(index=False), file_name=f"build_plan_{key}.csv",
                         mime="text/csv", key=f"dl_b_{key}")
    if "move" in V["case"].decides:
        tp = V["moved"].stack().rename("units").reset_index()
        tp.columns = ["sku", "t", "units"]
        tp = tp[tp["units"] > 0].assign(week_start=lambda d: d["t"].map(WEEKS), units=lambda d: d["units"].astype(int))
        c[1].download_button("Weekly transfers to the PDC (CSV)", tp[["week_start", "sku", "units"]].to_csv(index=False),
                             file_name=f"transfers_{key}.csv", mime="text/csv", key=f"dl_m_{key}")


# ---------------- targets ----------------

def positions_in_order(V):
    return [(s, p) for s in ORDER for p in sorted(V["pools"], key=lambda p: p == "CMH")]   # Reno before PDC


def wos_table(V):
    R = V["R"]
    rows = positions_in_order(V)
    tw = R["target_wos"]
    wq = pd.DataFrame({
        "SKU": [s for s, _ in rows],
        "Line · size": [f"{LINE_NAME[SKU.at[s, 'line_id']]} · {SKU.at[s, 'size']}" for s, _ in rows],
        "Stock at": [pool_label(p) for _, p in rows],
        "Target (weeks)": [" → ".join(f"{v:g}" for v in dict.fromkeys(tw.loc[k].values)) for k in rows],
        "Start": [R["wos"].at[k, 0] for k in rows],
    })
    ok = {"Start": [bool(R["wos"].at[k, 0] >= tw.at[k, 1]) for k in rows]}
    for q in FQ_ORDER:
        wq[q] = [R["wos"].at[k, FQ_END[q]] for k in rows]
        ok[q] = [bool(R["at_target"].at[k, FQ_END[q]]) for k in rows]
    for col in ["Start"] + FQ_ORDER:
        wq[col] = [f"{v:,.1f}" + ("" if g else " ▼") for v, g in zip(wq[col], ok[col])]
    status_table(wq, good=ok, right=["Start"] + FQ_ORDER, height=min(len(wq) + 1, 21) * 35 + 3)
    st.caption("Weeks of supply at the last week of each fiscal quarter (FY = Sep–Aug): how many weeks of the coming "
               "forecast the net inventory covers" + (", each site's stock against the demand routed to it"
                                                      if V["multi"] else "") + ". ▼ = below target.")


def sku_cover_chart(V, s, key):
    """One SKU, week by week: net inventory against the target at each stock site, and its builds."""
    R = V["R"]
    fig = go.Figure()
    built = V["built"].loc[s]
    fig.add_bar(x=WEEKS.values, y=built.values, name="built", marker_color=SIZE_COLOR["L"], marker_line_width=0,
                opacity=0.55, hovertemplate="built: %{y:,.0f}<extra></extra>")
    dash = {0: "solid", 1: "dot"}
    for i, p in enumerate(sorted(V["pools"], key=lambda p: p == "CMH")):
        lab = pool_label(p)
        fig.add_scatter(x=WEEKS.values, y=R["net"].loc[(s, p), 1:H].values, name=f"net inventory · {lab}",
                        line=dict(color=INK, width=2, dash=dash[i]), line_shape="hv",
                        hovertemplate=f"net {lab}: %{{y:,.0f}}<extra></extra>")
        fig.add_scatter(x=WEEKS.values, y=R["target_units"].loc[(s, p)].values, name=f"target · {lab}",
                        line=dict(color=FORECAST, width=1.5, dash=dash[i]), line_shape="hv",
                        hovertemplate=f"target {lab}: %{{y:,.0f}}<extra></extra>")
    if V["multi"]:
        fig.add_scatter(x=WEEKS.values, y=V["transit"].loc[s, 1:H].values, name="in transit to the PDC",
                        line=dict(color=MUTED, width=1), hovertemplate="in transit: %{y:,.0f}<extra></extra>")
    fig.add_hline(y=0, line=dict(color="#c9c8c2", width=1))
    st.plotly_chart(style(fig, 360, ytitle="bicycles"), key=f"cover_{key}_{s}")
    st.caption("Black: net inventory (stock − open orders) at the end of each week. Blue: target (the coming N weeks "
               "of forecast). Below the blue line = below target. Gold bars: bikes built that week.")


# ---------------- balance ----------------

def balance_table(V):
    AT, NET, TARGET = V["at_target"], V["net"], V["target_units"]
    op = m["opening_position"].set_index("sku")
    rows = [{"SKU": s, "Line · size": f"{LINE_NAME[SKU.at[s, 'line_id']]} · {SKU.at[s, 'size']}",
             "On hand": op.at[s, "on_hand_nettable"], "Backlog": -op.at[s, "backlog"],
             "= Opening net": NET.at[s, 0], "+ Built": V["built"].loc[s].sum(),
             "− Forecast": -V["demand"].loc[s].sum(), "= Closing net": NET.at[s, H], "Target": TARGET.at[s, H],
             "Status": "at target" if AT.at[s, H] else "below target"} for s in ORDER]
    bal = pd.DataFrame(rows)
    num = ["On hand", "Backlog", "= Opening net", "+ Built", "− Forecast", "= Closing net", "Target"]
    bal = pd.concat([bal, pd.DataFrame([{"SKU": "All SKUs", "Line · size": "", **bal[num].sum().to_dict(),
                                         "Status": f"{int(AT[H].sum())} of {len(ORDER)} at target"}])],
                    ignore_index=True)
    ok = list(AT[H].loc[ORDER].values) + [bool(AT[H].all())]

    def look(col):
        if col.name in ("= Opening net", "= Closing net"):
            return [f"background-color: {HIGHLIGHT_BG}; font-weight: 600"] * len(col)
        if col.name == "Status":
            return [f"background-color: {GOOD_BG if g else BAD_BG}" for g in ok]
        return [""] * len(col)

    st.dataframe(bal.style.format({c: "{:,.0f}" for c in num}).apply(look, axis=0),
                 hide_index=True, width="stretch", height=(len(bal) + 1) * 35 + 3)
    st.caption(f"Bicycles, {fmt_date(WEEKS.iloc[0])} to {fmt_date(WEEKS.iloc[-1])}: on hand − backlog = opening net; "
               "+ built − forecast = closing net. Target: forecast of the N weeks after the last week."
               + (" Net counts Reno, PDC and in-transit stock; a SKU is at target only when each site is."
                  if V["multi"] else ""))


def waterfall(V, s, key):
    NET, TARGET = V["net"], V["target_units"]
    steps = [("Opening", "absolute")]
    for y in sorted(FY.unique()):
        tag = "Sep–Dec 28" if (FY == y).sum() < 52 else f"FY{y % 100}"
        steps += [(f"Built<br>{tag}", "relative"), (f"Forecast<br>{tag}", "relative")]
    steps.append(("Closing", "total"))
    vals = [NET.at[s, 0]]
    for y in sorted(FY.unique()):
        wk = FY.index[FY == y]
        vals += [V["built"].loc[s, wk].sum(), -V["demand"].loc[s, wk].sum()]
    vals.append(0)
    text = [f"{v:,.0f}" for v in vals[:-1]] + [f"{NET.at[s, H]:,.0f}"]
    fig = go.Figure(go.Waterfall(
        x=[lbl for lbl, _ in steps], y=vals, measure=[k for _, k in steps], text=text, textposition="outside",
        cliponaxis=False, connector=dict(line=dict(color="#c9c8c2", width=1)),
        increasing=dict(marker=dict(color=SIZE_COLOR["L"])), decreasing=dict(marker=dict(color=SIZE_COLOR["S"])),
        totals=dict(marker=dict(color=SIZE_COLOR["M"])), hoverinfo="skip", showlegend=False))
    tgt = TARGET.at[s, H]
    fig.add_scatter(x=["Closing"], y=[tgt], mode="markers", name="target",
                    marker=dict(symbol="line-ew-open", size=40, color=INK, line=dict(color=INK, width=3)),
                    hovertemplate=f"target: {tgt:,.0f}<extra></extra>")
    level = pd.Series(vals[:-1]).cumsum()
    lo, hi = min(0, level.min()), max(level.max(), tgt)
    fig.update_yaxes(range=[lo - (hi - lo) * 0.14, hi + (hi - lo) * 0.14])
    st.plotly_chart(style(fig, 380), key=f"wf_{key}_{s}")
    st.caption("Gold: built. Black: forecast. Bronze: opening and closing net position. Black bar on Closing: the "
               "target. FY = September–August.")
