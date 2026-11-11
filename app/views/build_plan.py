"""A scenario's build plan: what to build each month, against capacity, forecast and the open orders left."""
import pandas as pd
import streamlit as st

from redwheel import aux_fns
from ui import (CAP, CAPACITY, FORECAST, LINES, LINE_NAME, ORDER, SIZE_COLOR, SIZE_RANK, SKU, SKUS_BY_LINE, WEEKS, cell,
                line_grid, obj, scenario_header, style)

BACKLOG_BG = "#bdbbb4"
BAR_W = 26 * 24 * 3600 * 1000            # bar width in ms (date axis): about 26 days
month = pd.Series(WEEKS.dt.to_period("M").values, index=WEEKS.index)
months = month.unique()
X = [p.to_timestamp() for p in months]
MONTH_END = [int(month.index[month == p].max()) for p in months]


def by_month(weekly):
    """Total within each month (a week counts in the month of its Monday)."""
    return pd.Series(weekly, index=WEEKS.index).groupby(month.values).sum().reindex(months).to_numpy()


def render(key: str):
    V = scenario_header(key, "Build Plans")
    moves = "move" in V["case"].decides
    st.markdown("What each line builds, month by month, from the linear programme"
                + (" (which also decides the transfers to the PDC)" if moves else "")
                + ": reach each weeks-of-supply target as early as capacity allows, without building above it.")
    bp = aux_fns.build_plan_table(obj, V["R"]["builds"])
    c = st.columns(6 if moves else 5)
    c[0].metric("Bicycles to build", f"{int(bp['units'].sum()):,}")
    for i, ln in enumerate(LINES):
        c[i + 1].metric(LINE_NAME[ln], f"{int(bp.loc[bp['line'] == ln, 'units'].sum()):,}")
    if moves:
        c[5].metric("Transfers to the PDC", f"{int(V['moved'].values.sum()):,}")

    st.subheader("Builds against capacity and forecast, and the open orders left")
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
    st.plotly_chart(style(fig, 640), key=f"plan_{key}")
    st.caption("Monthly totals; a week counts in the month of its Monday, so 5-week months carry more capacity. "
               "Coloured bars: builds by size. Grey bar behind: open orders still waiting at month end. Black dash: "
               "the month's capacity; builds reaching it mean the line ran full. Blue: forecast.")

    st.download_button("Download the weekly build plan (CSV)", bp.to_csv(index=False),
                       file_name=f"redwheel_build_plan_{key}.csv", mime="text/csv", key=f"dl_build_{key}")
    if moves:
        tp = V["moved"].stack().rename("units").reset_index()
        tp.columns = ["sku", "t", "units"]
        tp = tp[tp["units"] > 0].assign(week_start=lambda d: d["t"].map(WEEKS), units=lambda d: d["units"].astype(int))
        st.download_button("Download the weekly transfers to the PDC (CSV)",
                           tp[["week_start", "sku", "units"]].to_csv(index=False),
                           file_name=f"redwheel_transfers_{key}.csv", mime="text/csv", key=f"dl_moves_{key}")
