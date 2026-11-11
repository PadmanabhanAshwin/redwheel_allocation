"""Supply–demand context: the position at the snapshot, and the demand and capacity every scenario plans against."""
import pandas as pd
import streamlit as st

from ui import CAP, CAPACITY, FORECAST, H, HISTORY, LINES, MUTED, SKU, SKUS_BY_LINE, SNAP, WEEKS, cell, fmt_date, \
    line_grid, m, obj, r, style

st.title("Supply–Demand Context")
st.markdown(
    "Redwheel builds ten bicycle SKUs on four production lines at Reno and ships from Reno and the Columbus "
    "distribution centre to three channels (direct-to-consumer, dealers, commercial). Position at the "
    f"**{fmt_date(SNAP)} snapshot**, and the demand and capacity every scenario plans against "
    f"({fmt_date(SNAP)} – {fmt_date(WEEKS.iloc[-1])}, {H} weeks).")

on_hand = int(obj.opening[[f"inventory|{s}|{l}" for s in SKU.index for l in ("RENO", "CMH")]].sum())
backlog = int(m["opening_position"]["backlog"].sum())
c = st.columns(5)
c[0].metric("Finished goods on hand", f"{on_hand:,}", help="Reno plant + Columbus DC, all SKUs")
c[1].metric("Open orders (backlog)", f"{backlog:,}", help="Ordered and not yet delivered at the snapshot")
c[2].metric("Net position", f"{on_hand - backlog:,}", help="On hand − open orders")
c[3].metric(f"Forecast demand, {H} weeks", f"{int(r['demand'].loc[:, 1:H].values.sum()):,}")
c[4].metric(f"Build capacity, {H} weeks", f"{int(sum(v.sum() for v in CAP.values())):,}")

# ---------------- demand and capacity by line ----------------
st.subheader("Weekly demand and build capacity by production line")
st.caption("Grey: orders, last 52 weeks. Blue: forecast. Dashed: capacity. Bicycles per week.")
o = m["fact_orders"]
o = o.assign(week=o["order_date"] - pd.to_timedelta(o["order_date"].dt.dayofweek, unit="D"))
fig = line_grid()
for i, ln in enumerate(LINES):
    skus_ln = SKUS_BY_LINE[ln]
    hist = o[o["sku"].isin(skus_ln)].groupby("week")["qty"].sum()
    first = i == 0
    fig.add_scatter(x=hist.index, y=hist.values, name="orders (history)", line=dict(color=HISTORY, width=1.5),
                    legendgroup="h", showlegend=first, **cell(i))
    fig.add_scatter(x=WEEKS.values, y=r["demand"].loc[skus_ln, 1:H].sum().values, name="forecast",
                    line=dict(color=FORECAST, width=2), legendgroup="f", showlegend=first, **cell(i))
    fig.add_scatter(x=WEEKS.values, y=CAP[ln], name="capacity", line=dict(color=CAPACITY, width=1.5, dash="dash"),
                    line_shape="hv", legendgroup="c", showlegend=first, **cell(i))
    fig.add_vline(x=SNAP, line=dict(color=MUTED, width=1, dash="dot"), **cell(i))
fig.add_annotation(x=SNAP, y=1, yref="y domain", text="snapshot", showarrow=False, xanchor="left",
                   yanchor="top", xshift=4, font=dict(size=11, color=MUTED))
st.plotly_chart(style(fig, 560), key="ctx")
st.markdown(
    "- **MTB carbon**: forecast rises from about 250 to about 380 per week between FY2026 and FY2027; "
    "capacity steps 375 → 580 → 875 per week each September.\n"
    "- **Road carbon**: forecast spikes to 554 per week for three weeks from 5 July 2027, against 230 of capacity.\n"
    "- **MTB base**: RW-9324's forecast for the next 52 weeks is 81% below its orders in the last 52, "
    "with 1,900 units on hand.\n"
    "- **Road**: forecast and capacity both decline over the horizon on both lines.\n"
    "- **Near term**: on every line the forecast for the next 13 weeks is below orders received in the last 13 "
    "(per week: road base 78 vs 142, road carbon 114 vs 191, MTB base 57 vs 140, MTB carbon 137 vs 202). "
    "The plan uses the forecast as given; if near-term demand follows recent orders, targets are reached later.")
