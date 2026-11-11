"""Page 2 — build plans: what to build, against capacity and forecast, and the open orders it leaves."""
import pandas as pd
import streamlit as st

from ui import (
    BUILD, CAP, FORECAST, H, INK, LINES, LINE_NAME, ORDER, SIZE_COLOR, SIZE_RANK, SKU, SKUS_BY_LINE,
    WEEKS, cell, line_grid, r, style)

st.title("Build Plans")
st.markdown("Weekly builds per SKU from the linear programme: reach each weeks-of-supply target as early as capacity "
            "allows, without building above it.")
bp, f = r["build_plan"], r["flows"]
c = st.columns(5)
c[0].metric("Bicycles to build", f"{int(bp['units'].sum()):,}")
for i, ln in enumerate(LINES):
    c[i + 1].metric(LINE_NAME[ln], f"{int(bp.loc[bp['line'] == ln, 'units'].sum()):,}")

# ---------------- builds, capacity, forecast, and the open orders left ----------------
st.subheader("Builds against capacity and forecast, and the open orders left")
st.caption("Monthly totals in bicycles (a week counts in the month of its Monday, so 5-week months carry more "
           "capacity). Pale bar: capacity. Coloured bars: builds by size. Blue: forecast. Dotted: open orders at month "
           "end. Diamond: line full that month (hollow: below capacity).")
month = pd.Series(WEEKS.dt.to_period("M").values, index=WEEKS.index)
months = month.unique()
x = [p.to_timestamp() for p in months]
month_end = [int(month.index[month == p].max()) for p in months]


CAP_BG = "#e4e2dc"
BAR_W = 26 * 24 * 3600 * 1000            # bar width in ms (date axis): about 26 days


def by_month(weekly):
    """Total within each month."""
    return pd.Series(weekly, index=WEEKS.index).groupby(month.values).sum().reindex(months).to_numpy()


fig = line_grid()
shown = set()
for i, ln in enumerate(LINES):
    cap = by_month(CAP[ln])
    fig.add_bar(x=x, y=cap, width=BAR_W, name="capacity", marker_color=CAP_BG, marker_line_width=0, legendgroup="c",
                legendrank=4, showlegend=i == 0, hovertemplate="capacity: %{y:,.0f}<extra></extra>", **cell(i))
    total = 0
    for s in [k for k in ORDER if k in SKUS_BY_LINE[ln]]:
        size = SKU.at[s, "size"]
        y = by_month(BUILD[s])
        fig.add_bar(x=x, y=y, base=total, name=f"size {size}", marker_color=SIZE_COLOR[size], marker_line_width=0,
                    width=BAR_W * 0.62, legendgroup=size, legendrank=SIZE_RANK[size], showlegend=size not in shown,
                    hovertemplate=f"{s}: %{{y:,.0f}}<extra></extra>", **cell(i))
        total = total + y
        shown.add(size)
    fc = by_month(r["demand"].loc[SKUS_BY_LINE[ln], 1:H].sum().to_numpy())
    open_end = [f["open_orders"].loc[SKUS_BY_LINE[ln], t].sum() for t in month_end]
    fig.add_scatter(x=x, y=fc, name="forecast", mode="lines", line=dict(color=FORECAST, width=2), legendgroup="f",
                    legendrank=5, showlegend=i == 0, hovertemplate="forecast: %{y:,.0f}<extra></extra>", **cell(i))
    fig.add_scatter(x=x, y=open_end, name="open orders (month end)", mode="lines+markers",
                    line=dict(color=INK, width=1.5, dash="dot"), marker=dict(size=5, color=INK), legendgroup="o",
                    legendrank=6, showlegend=i == 0, hovertemplate="open orders: %{y:,.0f}<extra></extra>", **cell(i))
    fill = total / cap
    for flag, nm in [(True, "line full"), (False, "line below capacity")]:
        sel = (fill > 0.995) == flag
        fig.add_scatter(x=[d for d, k in zip(x, sel) if k], y=(total + cap.max() * 0.04)[sel], mode="markers",
                        name=nm, legendgroup=nm, legendrank=7 if flag else 8, showlegend=i == 0,
                        customdata=fill[sel], hovertemplate="capacity fill: %{customdata:.0%}<extra></extra>",
                        marker=dict(symbol="diamond" if flag else "diamond-open", size=7, color=INK,
                                    line=dict(color=INK, width=1)), **cell(i))
    fig.update_yaxes(range=[0, max(cap.max(), fc.max(), max(open_end)) * 1.12], **cell(i))
fig.update_yaxes(title_text="bicycles", col=1)
fig.update_layout(barmode="overlay")
st.plotly_chart(style(fig, 640), key="plan")

# ---------------- order fulfilment ----------------
st.subheader("Order fulfilment by fiscal year")
fy = WEEKS.dt.year - (WEEKS.dt.month < 9)
prev_open = f["open_orders"].loc[:, 0:H - 1].set_axis(range(1, H + 1), axis=1)
backlog_served = f["shipped"].clip(upper=prev_open)          # oldest orders ship first
on_time = f["shipped"] - backlog_served                        # this week's demand shipped this week
rows = []
for ln in LINES:
    sk = SKUS_BY_LINE[ln]
    for y in sorted(fy.unique()):
        wk = fy.index[fy == y]
        demand = f["demand"].loc[sk, wk].values.sum()
        built = f["built"].loc[sk, wk].values.sum()
        rows.append({"Line": LINE_NAME[ln], "Fiscal year": f"FY{y}" + (" (Sep–Dec)" if len(wk) < 52 else ""),
                     "Open orders · start": f["open_orders"].loc[sk, int(wk.min()) - 1].sum(),
                     "New demand": demand,
                     "Shipped late": backlog_served.loc[sk, wk].values.sum(),
                     "Shipped on time": on_time.loc[sk, wk].values.sum(),
                     "Open orders · end": f["open_orders"].loc[sk, int(wk.max())].sum(),
                     "On-time fill rate": on_time.loc[sk, wk].values.sum() / demand,
                     "Built": built, "Capacity used": built / CAP[ln][wk - 1].sum()})
ft = pd.DataFrame(rows)
st.dataframe(ft.style.format({c: "{:,.0f}" for c in ["Open orders · start", "New demand", "Shipped late",
                                                    "Shipped on time", "Open orders · end", "Built"]} |
                             {"On-time fill rate": "{:.0%}", "Capacity used": "{:.0%}"}),
             hide_index=True, width="stretch", height=(len(ft) + 1) * 35 + 3)
st.caption("Shipped = factory output released to orders as soon as it is available, oldest orders first (an "
           "assumption; the plan decides builds only). Shipped late: orders from an earlier week. On-time fill rate = "
           "shipped on time ÷ new demand. FY = September–August; FY2028 = Sep–Dec 2028.")
st.download_button("Download the weekly build plan (CSV)", bp.to_csv(index=False),
                   file_name="redwheel_build_plan.csv", mime="text/csv")
