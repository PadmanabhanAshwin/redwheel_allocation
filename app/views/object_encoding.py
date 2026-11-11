"""Page 5 — object encoding: the network, its assumptions, and the master data behind it."""
import pandas as pd
import streamlit as st

from ui import H, ORDER, dq_log, m, network_figure, obj, sku_label

st.title("Object Encoding")
st.markdown("A **resource–task network** (Pantelides, 1994). *Resources* have a level each week (inventory, line "
            "capacity, open orders); *tasks* (make, move, fulfil) change them through *edges* with an amount and a "
            "delay. One equation for every level: **carry-over + Σ amount × task runs + arrivals**.")
c = st.columns(5)
for col, (k, v) in zip(c, [("Locations", len(obj.locations)), ("Resources", len(obj.resources)),
                           ("Tasks", len(obj.tasks)), ("Edges", len(obj.arrows)), ("Weeks", H)]):
    col.metric(k, v)

st.subheader("Network for one SKU: every route the network allows")
s = st.selectbox("SKU", ORDER, key="graph_sku", format_func=sku_label)
st.plotly_chart(network_figure(s, delays=False), key="net")
st.caption("Circles: resources (opening level). Squares: tasks. Black edge adds, grey edge takes. "
           "Dealer stock is not Redwheel's, so it has no edges. Each scenario sets the delays and which ship routes "
           "are used: see the Network page in each scenario's section.")

st.subheader("Assumptions and sources")
st.dataframe(pd.DataFrame([
    ("Ten SKUs, each built on the one line matching its class and trim", "Fact", "order files, capacity plan"),
    ("Weekly capacity per line", "Fact", "capacity_plan.csv"),
    ("Stock at Reno and Columbus at the snapshot", "Fact", "plant_inventory_snapshot.csv"),
    ("Backlog = unfulfilled orders, plus 12 orders shipped after the snapshot", "Fact, with rule", "order files"),
    ("Weeks-of-supply targets", "Brief", "case brief"),
    ("Road target of 10 weeks starts 3 January 2028", "Assumption", "brief says 'in 2028'"),
    ("All four lines are at Reno", "Assumption", "no line location in the data"),
    ("Nothing in transit at the snapshot", "Assumption", "no transfer data"),
    ("Build time and Reno → Columbus transfer time are edge delays", "Set per scenario", "no lead-time data"),
    ("Routes from both sites to every channel are in the network; which ones are used is the routing rule",
     "Set per scenario", "no ship-from in order data"),
    ("Dealer-held stock is already sold and not netted", "Assumption", "dealer_stock_report.csv"),
    ("Unmet demand waits as backlog; it is not lost", "Assumption", "consistent with the brief"),
    ("Forecast used as given; each stock site counts the channels routed to it", "Assumption", "forecast files"),
    ("Orders ship as soon as stock exists (on hand and open orders shown over time)", "Assumption",
     "the plan decides builds; shipments are not in the data"),
    ("Objective weights: worst shortfall per line 1, total shortfall 0.1, stock above target 0.001",
     "Modelling choice", "—"),
    ("Scenarios after A add a cost of 0.000001 per bike built or moved, so nothing is built or moved without need",
     "Modelling choice", "—"),
], columns=["Statement", "Status", "Basis"]), hide_index=True, width="stretch", height=17 * 35 + 3)

with st.expander("Master data tables"):
    tables = ["opening_position", "dim_sku", "dim_line", "dim_location", "dim_week", "dim_policy",
              "fact_orders", "fact_inventory", "fact_capacity", "fact_forecast"]
    t = st.selectbox("Table", tables)
    st.caption(f"{len(m[t]):,} rows")
    st.dataframe(m[t], hide_index=True, width="stretch", height=320)
with st.expander("Data-quality decisions"):
    st.dataframe(pd.DataFrame.from_dict(dq_log, orient="index").rename_axis("id").reset_index(),
                 hide_index=True, width="stretch")
