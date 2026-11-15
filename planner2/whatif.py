"""What-if: make a new scenario (or change one of yours) from any scenario's settings.

1 · describe the change in words (Claude proposes settings)  2 · or set them directly  3 · review the changes, checked
against the network, and run. Running creates the scenario (or saves yours) and opens its plan. Step 2 also holds the
scenario's events (a line down, a demand change, a stock correction), which change the data it plans from."""
import streamlit as st

from planner2 import events, state
from planner2.components import describe_changes, header, settings_editor, show_changes
from planner2.event_card import events_card
from redwheel import llm, priors
from ui import fmt_date, obj

ss = state.init()
NAMES = state.names()
if ss.draft is None or ss.draft["base"] not in ss.cases:
    state.new_draft(ss.current if ss.current in ss.cases else state.BASE)
d = ss.draft
base = d["base"]
base_case = ss.cases[base]
d.setdefault("changes", tuple(base_case.changes))     # a draft made before drafts carried events

EXAMPLES = {    # chip label -> request
    "Web orders via the PDC": "Web orders ship only from the PDC; dealer and commercial orders ship straight from "
                              "Reno, and the plan decides the transfers to the PDC.",
    "MTB carbon: 2-week build": "MTB carbon now takes two weeks to build.",
    "MTB carbon target 18 from Sep 2027": "From 6 September 2027, raise the MTB carbon target to 18 weeks.",
    "Everything ships from the PDC": "All orders ship from the PDC, restocked from Reno.",
}

header("Change your scenario" if d["edit"] else "What-if",
       eyebrow=f"Editing {base_case.name}" if d["edit"] else f"New scenario from {base_case.name}",
       subtitle="Describe the change in words or set it directly, or add an event: a line down, a demand change, a "
                "stock correction. Every change is checked against the network before it runs; nothing is saved "
                "until you run it.")


# ---------------- where it starts ----------------
def change_base():
    state.new_draft(ss["_wi_base"], keep_request=True)


def as_new():
    state.new_draft(base)


top = st.columns([3, 5], vertical_alignment="bottom")
if d["edit"]:
    top[0].markdown(f"Changes are saved to **{base_case.name}**.")
    top[1].button("Make a new scenario instead", on_click=as_new, key="wi_as_new", icon=":material/call_split:")
else:
    ss["_wi_base"] = base
    top[0].selectbox("Start from", list(ss.cases), key="_wi_base", format_func=NAMES.get, on_change=change_base,
                     help="Its settings are where the what-if starts; changes are shown against it.")
    top[1].caption("Switching the starting scenario clears changes not yet run.")

left, right = st.columns([7, 4], gap="large")


def short_name(text: str, limit: int = 42) -> str:
    """A scenario name from a request: its first sentence, cut at a word boundary."""
    first = text.strip().split(". ")[0].rstrip(".")
    if len(first) <= limit:
        return first
    cut = first[:limit].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + " …"


# ---------------- 1 · describe it ----------------
def use_example(text):
    ss["wi_req"] = text


with left:
    with st.container(border=True):
        st.markdown("<div class='rw-step'>1 · Describe the change</div>", unsafe_allow_html=True)
        req = st.text_area("Request", key="wi_req", height=90, label_visibility="collapsed",
                           placeholder="e.g. MTB carbon now takes two weeks to build.")
        with st.container(horizontal=True, vertical_alignment="center"):
            st.caption("Try:", width="content")
            for i, (chip, ex) in enumerate(EXAMPLES.items()):
                st.button(chip, key=f"wi_ex_{i}", on_click=use_example, args=(ex,), help=ex, width="content")
        if st.button("Propose settings", type="primary", icon=":material/auto_awesome:", key="wi_propose"):
            if not req.strip():
                d["note"] = ("info", "Describe the change first, or pick an example.")
            else:
                current = ss.get("wi_last", d["seed"])
                try:
                    with st.spinner("Claude is reading the settings …"):
                        p = llm.propose(req.strip(), current, obj)
                except Exception as e:
                    d["note"] = ("error", f"The request did not go through ({type(e).__name__}: {e}).")
                else:
                    if p.ok:
                        d["seed"] = p.table
                        d["reasons"].update({(c["prior"], c["applies_to"], c["from_date"], c["new"]): c["reason"]
                                             for c in p.changes})
                        if not d["edit"] and not d["name"]:
                            d["name"] = short_name(req)
                        if not d["summary"]:
                            d["summary"] = req.strip()
                        n = len(p.changes)
                        msg = f"Claude set {n} setting{'s' if n != 1 else ''}: they are in the controls below and " \
                              "in the review. Adjust anything before you run it."
                        if p.unsupported:
                            msg += "\n\nNot covered by these settings:\n" + "\n".join(f"- {u}" for u in p.unsupported)
                        d["note"] = ("success", msg)
                        ss.wv += 1
                    elif p.changes:
                        d["note"] = ("warning", "Claude's settings failed the checks, so they were not used:\n"
                                     + "\n".join(f"- {e}" for e in p.errors))
                    elif p.question:
                        d["note"] = ("info", f"**Claude asks:** {p.question}")
                    else:
                        d["note"] = ("info", "No settings changed. Not covered by these settings:\n"
                                     + "\n".join(f"- {u}" for u in p.unsupported))
            st.rerun()
        if d["note"]:
            getattr(st, d["note"][0])(d["note"][1])
        st.caption("Claude sees your request, the current settings and the network's structure (sites, channels, "
                   "lines) — no orders, stock or customer data. It proposes settings only: a line down, a demand "
                   "change or a stock correction is an event, added in step 2.")

    # ---------------- 2 · set it directly ----------------
    st.markdown("<div class='rw-step' style='margin-top:0.8rem'>2 · Or set it directly</div>", unsafe_allow_html=True)
    events_card(d, obj)
    draft = settings_editor(d["seed"], key=f"w{ss.wv}")
    ss["wi_last"] = draft


# ---------------- 3 · review and run ----------------
def preview(table, against, changes):
    """Headline results of the settings and events as they stand, against the starting scenario. Planned on the fly
    (about a second, cached), nothing saved."""
    try:
        with st.spinner("Planning a preview …"):
            P = state._run("P", "Preview", "", against, priors.normalise(table).to_csv(index=False),
                           state.changes_text(changes))
    except Exception as e:
        st.warning(f"No preview: {type(e).__name__}: {e}")
        return
    c, c0 = P["card"], state.view(against)["card"]

    def dw(k):
        if c[k] is None or c0[k] is None:
            return None
        w = round((c[k] - c0[k]).days / 7)
        return f"{w:+d} wk vs {against}" if w else None

    st.markdown("**If you run it**")
    m = st.columns(2)
    m[0].metric("Targets held from", fmt_date(c["All targets held from"]) if c["All targets held from"] is not None
                else "never", dw("All targets held from"), delta_color="inverse")
    m[1].metric("Open orders cleared", fmt_date(c["Open orders cleared from"]) if c["Open orders cleared from"] is not None
                else "never", dw("Open orders cleared from"), delta_color="inverse")
    d_fill = c["On-time fill rate"] - c0["On-time fill rate"]
    m[0].metric("On-time fill", f"{c['On-time fill rate']:.1%}",
                f"{d_fill * 100:+.1f} pts vs {against}" if abs(d_fill) >= 5e-4 else None)
    d_below = c["Position-weeks below target"] - c0["Position-weeks below target"]
    m[1].metric("Weeks below target", f"{c['Position-weeks below target']:,}",
                f"{d_below:+,} vs {against}" if d_below else None, delta_color="inverse")
    if not P["checks"]["pass"].all():
        st.warning("A plan check fails on this preview; the Summary tab lists the checks once it is run.")


def start_over():
    state.new_draft(base, edit=d["edit"])


with right:
    with st.container(border=True, key="review"):
        st.markdown("<div class='rw-step'>3 · Review and run</div>", unsafe_allow_html=True)
        setting_changes = describe_changes(base_case.priors, draft, d["reasons"])
        moved = events.moves(base_case.changes, d["changes"])          # events added or removed against the start
        nothing = setting_changes.empty and not moved
        errs = priors.validate(draft, obj)
        bad = events.problem(obj, d["changes"])
        errs = errs + ([f"Events: {bad}"] if bad else [])
        st.markdown(f"**Changes from {base_case.name}**")
        if nothing:
            st.caption("No changes yet. Describe one, or use the controls on the left.")
        if not setting_changes.empty:
            show_changes(setting_changes)
        for what, c in moved:
            st.markdown(f"- **Event {what}:** {events.title(c)}")
        if errs:
            st.error("This can't run yet:\n\n" + "\n".join(f"- {e}" for e in errs), icon=":material/block:")
        elif not nothing:
            st.success("Passes every check against the network.", icon=":material/check_circle:")
            preview(draft, base, d["changes"])
        name = st.text_input("Name", value=d["name"], key=f"wi_name_{ss.wv}",
                             placeholder="e.g. MTB carbon two-week build")
        summary = st.text_area("Description", value=d["summary"], key=f"wi_summ_{ss.wv}", height=80,
                               placeholder="What this scenario tests, in a sentence.")
        d["name"], d["summary"] = name, summary
        label = "Save and re-plan" if d["edit"] else "Create and run scenario"
        run = st.button(label, type="primary", icon=":material/play_arrow:", key="wi_run", width="stretch",
                        disabled=bool(errs) or nothing)
        st.button("Start over", key="wi_reset", width="stretch", on_click=start_over, icon=":material/restart_alt:")
        if run:
            if not summary.strip():                               # describe it by its changes
                summary = f"From {base}: " + "; ".join([f"{r.Setting} {r.To}" for r in setting_changes.itertuples()]
                                                       + [f"event {what}: {events.title(c)}" for what, c in moved])
            if d["edit"]:
                state.update(base, draft, name, summary, d["changes"])
                k, parent = base, ss.cases[base].parent or state.BASE
            else:
                k = state.create(base, draft, name or "what-if", summary, d["changes"])
                parent = base
            ss.toast = f"Planned {ss.cases[k].name}."
            ss.draft = None
            ss.pop("wi_last", None)
            state.open_scenario(k, compare_to=parent)
            st.switch_page("scenario.py")
