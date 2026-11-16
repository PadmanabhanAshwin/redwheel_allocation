"""Try a change: change one tunable of a featured scenario (by its form, or in words through Claude), run it, and
read it against the scenario it started from. The live set on R+ is listed ready to read."""
import streamlit as st

from planner2_demo import state, views
from planner2_demo.components import delete_control
from redwheel import llm, tunables as tu

ss = state.init()
SHORT = state.short_names()
NAMES = {k: t.name for k, t in tu.TUNABLES.items()}
st.title("Try a change")


def run(base, edits, summary: str):
    name = tu.name_hint(edits[0]) + (f" and {len(edits) - 1} more" if len(edits) > 1 else "")
    ss.run = state.add(tu.apply(base, edits, key="new", name=name, summary=summary, parent=base.key))
    ss.prop = None
    st.rerun()


def field_widget(t, f):
    k, help_ = f"tc_{t.key}_{f.key}", None
    if f.kind == "choice":
        opts, labels = [v for v, _ in f.choices], dict(f.choices)
        return st.selectbox(f.label, opts, index=opts.index(f.default) if f.default in opts else 0,
                            format_func=labels.get, key=k, help=help_)
    if f.kind == "date":
        return st.date_input(f.label, value=f.default, min_value=f.min, max_value=f.max, key=k, help=help_,
                             format="YYYY-MM-DD")
    if f.kind == "int":
        return int(st.number_input(f.label, min_value=f.min, max_value=f.max, value=int(f.default), step=1, key=k,
                                   help=help_))
    if f.kind == "number":
        return float(st.number_input(f.label, min_value=f.min, max_value=f.max, value=float(f.default), key=k,
                                     help=help_))
    return st.text_input(f.label, value=f.default or "", key=k, help=help_)


left, right = st.columns([1, 2.6], gap="large")
with left:
    base = ss.cases[st.selectbox("Start from", list(state.FEATURED), format_func=SHORT.get, key="tc_base")]
    tk = st.selectbox("Change", list(tu.TUNABLES), index=list(tu.TUNABLES).index("line_capacity"),
                      format_func=NAMES.get, key="tc_tunable")
    t = tu.TUNABLES[tk]
    values = {f.key: ("" if f.key == "why" else field_widget(t, f)) for f in t.fields}   # 'why' is optional
    try:
        edit = tu.make(tk, **values)
        problems = tu.check(base, [edit])
    except ValueError as e:
        edit, problems = None, [str(e)]
    for x in problems:
        st.caption(f":red[{x}]")
    if st.button("Run", type="primary", key="tc_run", width="stretch", disabled=bool(problems)):
        run(base, [edit], tu.describe(edit))

    with st.expander("Describe the change", icon=":material/edit_note:"):
        st.text_input("Change", key="tc_req", label_visibility="collapsed",
                      placeholder="the MTB carbon line is down for three weeks from 1 March 2027")
        if st.button("Propose", key="tc_propose", width="stretch"):
            req = ss.get("tc_req", "").strip()
            try:
                with st.spinner("Reading the change …"):
                    ss.prop = ("ok", llm.propose_edits(req, base)) if req else ("warn", "Type a change first.")
            except Exception as e:                           # shown, never raised
                ss.prop = ("warn", f"The request did not go through ({type(e).__name__}: {e}).")
        prop = ss.get("prop")
        if prop and prop[0] == "warn":
            st.warning(prop[1])
        elif prop:
            p = prop[1]
            if p.question:
                st.info(p.question)
            for w in p.words:
                st.markdown(f"- {w}")
            for u in p.unsupported:
                st.caption(f"Not possible: {u}")
            if p.errors:
                st.warning("; ".join(p.errors))
            if p.ok and st.button(f"Run on {p.case.key}", type="primary", key="tc_prop_run", width="stretch"):
                run(p.case, p.edits, p.request)

    runs = list(state.EXAMPLES) + [k for k in ss.cases if not state.locked(k)]
    if ss.run not in runs:
        ss.run = runs[0]

    def pick():
        ss.run = ss["_run"]

    ss["_run"] = ss.run
    st.radio("Runs", runs, key="_run", format_func=SHORT.get, on_change=pick)
    delete_control(ss.run, key="tc")

with right:
    case = ss.cases[ss.run]
    k0 = case.parent if case.parent in ss.cases else state.BASE
    slot = st.empty()
    V, e = state.safe_view(ss.run, slot)
    V0, e0 = state.safe_view(k0, slot)
    st.subheader(f"{state.short(ss.run)}, against {k0}")
    if V is None or V0 is None:
        st.error(f"Cannot be planned: {e or e0}", icon=":material/error:")
    else:
        views.differences(V, V0, key=f"tc_{k0}_{ss.run}")
