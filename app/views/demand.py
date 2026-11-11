"""Page 2 — demand sources: which channels, places and customers the demand comes from."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from ui import (CHANNELS, CHANNEL_COLOR, CHANNEL_NAME, INK, LINES, LINE_NAME, MUTED, SITE_NAME, SNAP, demand_src,
                fmt_date, style)

st.title("Demand Sources")
d = demand_src
ch = d["by_channel"].loc[CHANNELS]
total = d["total"]
st.markdown(f"Orders received in the 52 weeks to the {fmt_date(SNAP)} snapshot, and the forecast that follows.")

site_units = d["by_state"].assign(units=d["by_state"][["dealer", "dtc"]].sum(axis=1)).groupby("site")["units"].sum()
located = int(site_units.sum())
c = st.columns(5)
c[0].metric("Bicycles ordered, 52 weeks", f"{total:,}")
c[1].metric("Dealers", f"{ch.at['dealer', 'orders_last_52'] / total:.0%}", help=f"{len(d['dealers'])} dealers")
c[2].metric("Direct-to-consumer", f"{ch.at['dtc', 'orders_last_52'] / total:.0%}")
c[3].metric("Commercial", f"{ch.at['commercial', 'orders_last_52'] / total:.0%}",
            help=f"{d['commercial_accounts']} accounts")
c[4].metric("Located demand nearer Columbus", f"{site_units['CMH'] / located:.0%}",
            help="Dealer and direct-to-consumer orders, by ship-to state")

# ---------------- by channel over time ----------------
st.subheader("Demand by channel")
fig = go.Figure()
for k in CHANNELS:
    fig.add_scatter(x=d["weekly_orders"].index, y=d["weekly_orders"][k], name=CHANNEL_NAME[k], legendgroup=k,
                    line=dict(color=CHANNEL_COLOR[k], width=1.6), hovertemplate="%{y:,.0f}<extra>" + CHANNEL_NAME[k] + "</extra>")
    fig.add_scatter(x=d["weekly_forecast"].index, y=d["weekly_forecast"][k], name=CHANNEL_NAME[k], legendgroup=k,
                    showlegend=False, line=dict(color=CHANNEL_COLOR[k], width=2.2),
                    hovertemplate="%{y:,.0f}<extra>" + CHANNEL_NAME[k] + " forecast</extra>")
fig.add_vline(x=SNAP, line=dict(color=MUTED, width=1, dash="dot"))
fig.add_annotation(x=SNAP, y=1, yref="y domain", text=" orders ◀  ▶ forecast", showarrow=False, xanchor="center",
                   yanchor="bottom", font=dict(size=11, color=MUTED))
st.plotly_chart(style(fig, 340, ytitle="bicycles per week"), key="dem_time")

tbl = pd.DataFrame({
    "Channel": [CHANNEL_NAME[k] for k in CHANNELS],
    "Orders · last 52 weeks": ch["orders_last_52"].values,
    "Share": (ch["orders_last_52"] / total).values,
    "Forecast · next 52 weeks": ch["forecast_next_52"].values,
    "Forecast vs orders": (ch["forecast_next_52"] / ch["orders_last_52"] - 1).values,
    "Order lines": ch["order_lines"].values,
    "Bicycles per order line": (ch["orders_last_52"] / ch["order_lines"]).values,
})
st.dataframe(tbl.style.format({"Orders · last 52 weeks": "{:,.0f}", "Share": "{:.0%}",
                               "Forecast · next 52 weeks": "{:,.0f}", "Forecast vs orders": "{:+.0%}",
                               "Order lines": "{:,.0f}", "Bicycles per order line": "{:.1f}"}),
             hide_index=True, width="stretch")

# ---------------- by place ----------------
st.subheader("Demand by ship-to state")
bs = d["by_state"].assign(units=d["by_state"][["dealer", "dtc"]].sum(axis=1))
sites = ["RENO", "CMH"]
fig = make_subplots(rows=1, cols=2, shared_xaxes=True, horizontal_spacing=0.08, subplot_titles=[
    f"Nearer {SITE_NAME[s]} · {site_units[s]:,} bicycles ({site_units[s] / located:.0%})" for s in sites])
xmax = bs["units"].max() * 1.15
for j, s in enumerate(sites):
    part = bs[bs["site"] == s].sort_values("units")
    for k in ["dealer", "dtc"]:
        fig.add_bar(y=part.index, x=part[k], orientation="h", name=CHANNEL_NAME[k], legendgroup=k,
                    showlegend=j == 0, marker_color=CHANNEL_COLOR[k], marker_line_width=0,
                    hovertemplate="%{y}: %{x:,.0f}<extra>" + CHANNEL_NAME[k] + "</extra>", row=1, col=j + 1)
    fig.add_scatter(y=part.index, x=part["units"], mode="text", text=[f" {v:,}" for v in part["units"]],
                    textposition="middle right", textfont=dict(size=11, color=INK), showlegend=False,
                    hoverinfo="skip", row=1, col=j + 1)
    fig.update_xaxes(range=[0, xmax], row=1, col=j + 1)
fig.update_layout(barmode="stack", bargap=0.25, hovermode="closest")
fig = style(fig, 420)
fig.update_layout(hovermode="closest")
fig.update_yaxes(showgrid=False)
fig.update_xaxes(showgrid=True, gridcolor="#e7e6e2")
st.plotly_chart(fig, key="dem_state")
st.caption(f"Dealer and direct-to-consumer orders ({located:,} bicycles, {located / total:.0%} of demand); commercial "
           f"orders ({ch.at['commercial', 'orders_last_52']:,}) carry no location. Each state is assigned to the nearer "
           "site by straight-line distance (an assumption; not used by the base plan).")

# ---------------- by line ----------------
st.subheader("Channel mix by production line")
lc = d["line_by_channel"].loc[LINES, CHANNELS]
share = lc.div(lc.sum(axis=1), axis=0)
fig = go.Figure()
for k in CHANNELS:
    fig.add_bar(y=[LINE_NAME[ln] for ln in LINES], x=share[k], orientation="h", name=CHANNEL_NAME[k],
                marker_color=CHANNEL_COLOR[k], marker_line_width=0, text=[f"{v:.0%}" for v in share[k]],
                textposition="inside", insidetextanchor="middle", textfont=dict(color="white" if k != "dtc" else INK),
                customdata=lc[k], hovertemplate="%{y}: %{customdata:,.0f} bicycles<extra>" + CHANNEL_NAME[k] + "</extra>")
fig.update_layout(barmode="stack", bargap=0.3)
fig = style(fig, 250)
fig.update_layout(hovermode="closest")
fig.update_xaxes(tickformat=".0%", range=[0, 1])
fig.update_layout(legend_traceorder="normal")
fig.update_yaxes(autorange="reversed", showgrid=False)
st.plotly_chart(fig, key="dem_line")

# ---------------- by customer ----------------
left, right = st.columns(2)
with left:
    st.subheader("Largest dealers")
    top = d["dealers"].head(10)
    dealer_total = d["dealers"]["qty"].sum()
    dt = pd.DataFrame({"Dealer": top["party_name"], "State": top["state"], "Bicycles": top["qty"],
                       "Share of dealer demand": top["qty"] / dealer_total})
    st.dataframe(dt.style.format({"Bicycles": "{:,.0f}", "Share of dealer demand": "{:.1%}"}),
                 hide_index=True, width="stretch")
    st.caption(f"Top 10 of {len(d['dealers'])} dealers: {top['qty'].sum() / dealer_total:.0%} of dealer demand.")
with right:
    st.subheader("Commercial accounts by type")
    ct = d["commercial_types"]
    cdf = pd.DataFrame({"Account type": ct.index, "Bicycles": ct["units"].values,
                        "Share of commercial demand": (ct["units"] / ct["units"].sum()).values,
                        "Order lines": ct["order_lines"].values})
    st.dataframe(cdf.style.format({"Bicycles": "{:,.0f}", "Share of commercial demand": "{:.0%}",
                                   "Order lines": "{:,.0f}"}), hide_index=True, width="stretch")
    st.caption(f"{d['commercial_accounts']} accounts.")
