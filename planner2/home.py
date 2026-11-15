"""Home: what the planner does, where things stand at the snapshot, and every scenario with its headline result."""
import streamlit as st

from planner2 import state
from redwheel import priors
from planner2.components import fdate, header
from ui import CAP, H, SKU, SNAP, WEEKS, m, obj, r

ss = state.init()

header("Redwheel build planner", eyebrow=f"Snapshot {fdate(SNAP)} · plan to {fdate(WEEKS.iloc[-1])}",
       subtitle="Plans how many of each bike to build every week on the four Reno lines, so every SKU reaches its "
                "weeks-of-supply target as early as capacity allows, after clearing the orders already waiting. "
                "Change the assumptions in a <b>what-if</b> and compare the plans side by side.")

# ---------------- where things stand ----------------
st.subheader("Where things stand")
on_hand = int(obj.opening[[f"inventory|{s}|{l}" for s in SKU.index for l in ("RENO", "CMH")]].sum())
backlog = int(m["opening_position"]["backlog"].sum())
cols = st.columns(5)
for col, (label, value, help_) in zip(cols, [
        ("Bikes in stock", f"{on_hand:,}", "Reno plant and the Columbus PDC, all ten SKUs"),
        ("Bikes on open orders", f"{backlog:,}", "Ordered and not yet shipped at the snapshot"),
        ("Net position", f"{on_hand - backlog:,}", "Stock minus open orders: the plan starts below zero"),
        ("Forecast demand", f"{int(r['demand'].loc[:, 1:H].values.sum()):,}", f"All three channels, next {H} weeks"),
        ("Build capacity", f"{int(sum(v.sum() for v in CAP.values())):,}", f"Four Reno lines, next {H} weeks")]):
    col.metric(label, value, help=help_, border=True)
st.page_link("ref_context.py", label="Demand and capacity by line, and what to watch in the forecast",
             icon=":material/arrow_forward:")

# ---------------- scenarios ----------------
def whatif_from(k):
    state.new_draft(k)


hc = st.columns([5, 1], vertical_alignment="center")
hc[0].subheader("Scenarios")
if hc[1].button("New what-if", icon=":material/add:", type="primary", key="home_new", width="stretch",
                on_click=whatif_from, args=(ss.current,)):
    st.switch_page("whatif.py")
st.markdown("<div class='rw-muted'>Each scenario is the same data and optimiser under different assumptions. "
            "A is the base case; B tests a distribution-centre policy. Yours appear here too.</div>",
            unsafe_allow_html=True)
slot = st.empty()
planned = {k: state.safe_view(k, slot) for k in ss.cases}
views = {k: v for k, (v, _) in planned.items()}
keys = list(ss.cases)
per_row = 3


def open_(k):
    state.open_scenario(k)


for i in range(0, len(keys), per_row):
    cols = st.columns(per_row, gap="medium")
    for col, k in zip(cols, keys[i:i + per_row]):
        with col.container(border=True):
            c, V = ss.cases[k], views[k]
            if V is None:
                st.markdown(f"**{c.name}**")
                st.error(f"This scenario can't be planned: {planned[k][1]}", icon=":material/error:")
                if not state.locked(k) and st.button("Delete it", key=f"home_del_{k}"):
                    state.delete(k)
                    st.rerun()
                continue
            card = V["card"]
            st.markdown(f"**{c.name}**")
            with st.container(horizontal=True):
                if state.locked(k):
                    st.badge("Built in", icon=":material/lock:", color="gray")
                else:
                    st.badge("Yours", icon=":material/person:", color="blue")
                if c.parent:
                    st.badge(f"From {c.parent}", color="gray")
                same = next((o for o in keys[:keys.index(k)] if priors.diff(ss.cases[o].priors, c.priors) == []), None)
                if same:
                    st.badge(f"Same settings as {same}", icon=":material/content_copy:", color="orange")
                if not V["checks"]["pass"].all():
                    st.badge("Check failed", icon=":material/error:", color="red")
            summ = (c.summary or "No description.").replace("&", "&amp;").replace("<", "&lt;").replace("'", "&#39;")
            st.markdown(f"<div class='rw-clamp' title='{summ}'>{summ}</div>", unsafe_allow_html=True)
            held = card["All targets held from"]
            st.markdown(f"<div class='rw-nums'><div>Targets held<b>{fdate(held) if held is not None else 'never'}</b></div>"
                        f"<div>On-time fill<b>{card['On-time fill rate']:.1%}</b></div>"
                        f"<div>Below target<b>{card['Position-weeks below target']:,} wks</b></div></div>",
                        unsafe_allow_html=True)
            b = st.columns(2)
            if b[0].button("Open", key=f"home_open_{k}", type="primary", width="stretch", on_click=open_, args=(k,)):
                st.switch_page("scenario.py")
            if b[1].button("What-if from this", key=f"home_wi_{k}", width="stretch", on_click=whatif_from,
                           args=(k,)):
                st.switch_page("whatif.py")

# ---------------- how to use it ----------------
st.subheader("How to use it")
steps = [
    ("1 · Read a plan", "Open a scenario: when every SKU reaches target, what limits it, what to build each month, "
                        "and how each SKU's stock moves. Ask questions about it in words."),
    ("2 · Try a what-if", "Change where each channel's orders ship from, build and transfer times, or targets. "
                          "Describe it in words and Claude proposes the settings, or set them yourself. Every change "
                          "is checked against the network before it runs."),
    ("3 · Compare", "Put scenarios side by side: headline results, the settings that differ, and how stock and "
                    "builds move week by week. Ask why they differ."),
]
for col, (title, text) in zip(st.columns(3, gap="medium"), steps):
    with col.container(border=True, height=190):
        st.markdown(f"<div class='rw-step'>{title}</div>", unsafe_allow_html=True)
        st.markdown(text)

with st.expander("Assumptions behind every plan"):
    st.markdown(
        "- **Data:** the nine Redwheel files, snapshot " + fdate(SNAP) + ". Forecast, capacity, stock and open orders "
        "are the same in every scenario; only the scenario's settings differ.\n"
        "- **Targets** (weeks of supply, from the brief): road 8, rising to 10 in 2028 (taken as 3 Jan 2028); MTB base "
        "12; MTB carbon 15. A SKU is at target when its net inventory covers the next N weeks of forecast.\n"
        "- **Open orders** count against stock from day one; nothing waits for a need-by date.\n"
        "- **Shipping** is not planned: orders ship as soon as stock exists, oldest first.\n"
        "- **Dealer-held stock** belongs to dealers and is not counted.\n"
        "- **The optimiser** minimises the worst shortfall against target per line and week, then total shortfall, "
        "then stock above target. Every plan is checked: whole bikes, capacity never exceeded, and a SKU is below "
        "target only while its line runs full.")
    st.page_link("ref_validation.py", label="Model validation", icon=":material/verified:")
