"""Model: how the plan is computed. The object in numbers, one bike drawn as the object sees it, and where every number
in it comes from."""
import streamlit as st

from planner2 import reading as rd
from ui import H, ORDER, network_figure, obj, sku_label

st.title("Model")
c = st.columns(5)
for col, (label, value) in zip(c, [("Locations", len(obj.locations)), ("Resources", len(obj.resources)),
                                   ("Tasks", len(obj.tasks)), ("Edges", len(obj.arrows)), ("Weeks", H)]):
    col.metric(label, f"{value:,}", border=True)

st.subheader("One bike, as the model sees it")
s = st.selectbox("Bike", ORDER, index=ORDER.index("RW-4418"), key="model_sku", format_func=sku_label)
st.plotly_chart(network_figure(s), key=f"net_{s}", config={"displayModeBar": False})
st.caption("Circles: resources, level at the snapshot. Squares: tasks. Black: adds; grey: takes.")

st.subheader("Where each number comes from")
st.table(rd.sources(obj).set_index("From"))
