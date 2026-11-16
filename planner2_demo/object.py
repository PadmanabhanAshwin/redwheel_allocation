"""Object: the object in numbers, and one bike drawn as the object sees it."""
import streamlit as st

from planner2_demo.views import strip
from ui import H, ORDER, network_figure, obj, sku_label

st.title("Object")
c1, c2 = st.columns([3, 1.4], vertical_alignment="bottom")
with c1:
    strip([(label, f"{value:,}") for label, value in [
        ("Locations", len(obj.locations)), ("Resources", len(obj.resources)), ("Tasks", len(obj.tasks)),
        ("Edges", len(obj.arrows)), ("Weeks", H)]])
s = c2.selectbox("Bike", ORDER, index=ORDER.index("RW-4418"), key="model_sku", format_func=sku_label,
                 label_visibility="collapsed")
st.plotly_chart(network_figure(s), key=f"net_{s}", config={"displayModeBar": False})
