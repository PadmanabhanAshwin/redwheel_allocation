"""Compare: scenarios side by side against one reference — results, settings that differ, when each line reaches
target, how stock and builds move — and ask why they differ."""
import pandas as pd
import streamlit as st

from planner2 import charts
from planner2 import events
from planner2 import facts
from planner2 import state
from planner2.components import CUSTOMERS, GROUPS, describe_changes, header, ship_from, target_text, targets, wk
from redwheel import llm, priors
from redwheel.config import LINES
from ui import fmt_date, right_align

ss = state.init()
NAMES = state.names()
SHORT = state.short_names()
keys = list(ss.cases)

header("Compare scenarios", eyebrow="Side by side",
       subtitle="Pick a reference and the scenarios to set against it. Differences are always against the "
                "reference.")


def pick(field):
    ss[field] = ss[f"_{field}"]


def fill(widget_key, text):
    ss[widget_key] = text


ss.setdefault("cmp_ref", state.BASE)
ss.setdefault("cmp_others", [k for k in keys if k != state.BASE][:4])
ss["cmp_others"] = [k for k in ss.cmp_others if k in ss.cases and k != ss.cmp_ref]
if ss.cmp_ref not in ss.cases:
    ss.cmp_ref = state.BASE
c = st.columns([2, 5], vertical_alignment="bottom")
ss["_cmp_ref"] = ss.cmp_ref
c[0].selectbox("Reference", keys, key="_cmp_ref", format_func=SHORT.get, on_change=pick, args=("cmp_ref",))
ss["_cmp_others"] = [k for k in ss.cmp_others if k != ss.cmp_ref]
c[1].multiselect("Compare with", [k for k in keys if k != ss.cmp_ref], key="_cmp_others", format_func=SHORT.get,
                 on_change=pick, args=("cmp_others",), max_selections=len(charts.PALETTE) - 1)
ref, others = ss.cmp_ref, [k for k in ss.cmp_others if k != ss.cmp_ref]
if not others:
    st.info("Pick at least one scenario to compare with the reference.")
    st.stop()

slot = st.empty()
picked = [ref] + others
planned = {k: state.safe_view(k, slot) for k in picked}
broken = [k for k, (v, _) in planned.items() if v is None]
if broken:
    st.warning("Left out because they can't be planned: " + ", ".join(NAMES[k] for k in broken))
picked = [k for k in picked if k not in broken]
if ref in broken or len(picked) < 2:
    st.stop()
others = [k for k in others if k in picked]
views = {k: planned[k][0] for k in picked}
label = {k: state.short(k) for k in picked}
colors = {label[k]: charts.PALETTE[i] for i, k in enumerate(picked)}

# ---------------- results ----------------
st.subheader("Results")
M = [("All targets held from", "All targets held from"), ("Open orders cleared", "Open orders cleared from"),
     ("On-time fill rate", "On-time fill rate"), ("Weeks below target", "Position-weeks below target"),
     ("Bikes built", "Bikes built"), ("Transferred to the PDC", "Bikes transferred to the PDC"),
     ("Average bikes in transit", "Average bikes in transit")]


def show(k, v):
    if v is None:
        return "never"
    if isinstance(v, pd.Timestamp):
        return fmt_date(v)
    return f"{v:.1%}" if "rate" in k else f"{v:,.0f}"


def delta(k, a, b):
    if a is None or b is None or a == b:
        return ""
    if isinstance(a, pd.Timestamp):
        w = round((b - a).days / 7)
        return f"  ({w:+d} wk)" if w else ""
    if "rate" in k:
        return f"  ({(b - a) * 100:+.1f} pts)" if abs(b - a) >= 5e-4 else ""
    return f"  ({b - a:+,.0f})" if round(b - a) else ""


c0 = views[ref]["card"]
res = pd.DataFrame({label[k]: [show(f, views[k]["card"][f]) + ("" if k == ref else delta(f, c0[f], views[k]["card"][f]))
                               for _, f in M] for k in picked}, index=pd.Index([m for m, _ in M], name="Measure"))
st.dataframe(right_align(res), width="stretch")
st.caption("In brackets: the change against the reference. Weeks below target are summed over SKU-site positions, so a "
           "scenario that splits stock between Reno and the PDC counts two positions per SKU.")

# ---------------- settings that differ ----------------
st.subheader("Settings that differ")


def setting_values(t):
    t = priors.normalise(t)
    out = {f"{v} ship from": ship_from(t, k) for k, v in CUSTOMERS.items()}
    move = t[(t["prior"] == "decides") & (t["applies_to"] == "move")]["value"]
    out["Transfers Reno → PDC"] = "planned" if (len(move) and move.iloc[0] == "yes") else "not planned"
    for ln in LINES:
        v = t[(t["prior"] == "build_weeks") & (t["applies_to"] == ln)]["value"]
        out[f"Build time · {charts.LINE_WORDS[ln]}"] = wk(v.iloc[0]) if len(v) else "—"
    v = t[t["prior"] == "transfer_weeks"]["value"]
    out["Transfer time · Reno → PDC"] = wk(v.iloc[0]) if len(v) else "—"
    for g, steps in targets(t).items():
        out[f"Target · {GROUPS.get(g, g)}"] = target_text(steps)
    return out


vals = {label[k]: {**setting_values(ss.cases[k].priors),
                   "Events": "; ".join(events.title(c) for c in ss.cases[k].changes) or "none"} for k in picked}
side = pd.DataFrame(vals)
side = side[side.nunique(axis=1) > 1].rename_axis("Setting")
if side.empty:
    st.caption("All picked scenarios have the same settings and events.")
else:
    st.dataframe(side, width="stretch")

# ---------------- when each line reaches target ----------------
st.subheader("When each line holds its targets")
rd = {k: charts.plan_reading(views[k]) for k in picked}
rows = []
for ln in LINES:
    row = {"Line": charts.LINE_WORDS[ln]}
    d0 = rd[ref]["lines"][ln]["held_from"]
    for k in picked:
        d = rd[k]["lines"][ln]["held_from"]
        row[label[k]] = (fmt_date(d) if d is not None else "never") + (
            "" if k == ref or d is None or d0 is None or d == d0 else f"  ({round((d - d0).days / 7):+d} wk)")
    rows.append(row)
st.dataframe(right_align(pd.DataFrame(rows).set_index("Line")), width="stretch")
st.caption("First week from which every SKU on the line is at target, at every stock site, to the end of the plan.")

# ---------------- over time ----------------
st.subheader("Week by week")
charts.compare_charts({label[k]: views[k] for k in picked}, colors, key="cmp")

# ---------------- ask ----------------
st.subheader("Ask why they differ")
with st.container(border=True):
    st.caption("Answers come only from these scenarios' settings and computed results — nothing else.")
    q = st.text_area("Question", key="cmp_q", height=80, label_visibility="collapsed",
                     placeholder=f"e.g. Why does {others[0]} hold its targets later than {ref}? Which setting matters "
                                 "most?")
    with st.container(horizontal=True):
        for i, ex in enumerate([f"Why does {others[0]} hold its targets later than {ref}?",
                                "Which settings explain most of the difference?",
                                "Which scenario clears open orders first, and why?"]):
            st.button(ex, key=f"cmpex_{i}", width="content", on_click=fill, args=("cmp_q", ex))
    if st.button("Ask", icon=":material/auto_awesome:", key="cmp_ask", type="primary"):
        if q.strip():
            try:
                with st.spinner("Thinking …"):
                    out = llm.explain(q.strip(), facts.facts([(k, ss.cases[k], views[k]) for k in picked]))
                ss.cmp_ans = ("ok", q.strip(), out["answer"])
            except Exception as e:
                ss.cmp_ans = ("error", q.strip(), f"The question did not go through ({type(e).__name__}: {e}).")
        else:
            ss.cmp_ans = ("error", "", "Type a question first.")
    ans = ss.get("cmp_ans")
    if ans:
        if ans[0] == "ok":
            st.markdown(f"<div class='rw-muted'>Q: {ans[1]}</div>", unsafe_allow_html=True)
            st.markdown(ans[2])
        else:
            st.warning(ans[2])
