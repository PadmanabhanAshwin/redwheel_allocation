"""Shared pieces of the planner UI: page headers, scenario settings in plain words (read-only and editable), and
change lists a person can read.

The settings editor shows a scenario's planning priors as a planner thinks about them (where each channel's orders
ship from, lead times, targets, what the plan decides) and turns the controls back into the priors table exactly as
set. It decides nothing: `priors.validate` says what is wrong with a table."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from redwheel import priors
from redwheel.config import LINES, PLAN_END, PLAN_START
from ui import LINE_NAME

CUSTOMERS = {"WEB": "Web orders", "DEALERS": "Dealer orders", "COMMERCIAL": "Commercial orders"}
SITES = {"RENO": "Reno", "CMH": "PDC"}
SHIP = {"Reno": ("RENO",), "PDC": ("CMH",), "Either site": ("RENO", "CMH")}
GROUPS = {"road": "Road", "mtb_base": "MTB base", "mtb_carbon": "MTB carbon"}
START = PLAN_START.date()


def wk(n) -> str:
    n = float(n)
    n = int(n) if n.is_integer() else n
    return "same week" if n == 0 else f"{n:g} week" + ("" if n == 1 else "s")


def fdate(d) -> str:
    return pd.Timestamp(d).strftime("%-d %b %Y")


def header(title: str, eyebrow: str = "", subtitle: str = ""):
    if eyebrow:
        st.markdown(f"<div class='rw-eyebrow'>{eyebrow}</div>", unsafe_allow_html=True)
    st.title(title)
    if subtitle:
        st.markdown(f"<div class='rw-sub'>{subtitle}</div>", unsafe_allow_html=True)


# ---------------- reading a priors table ----------------

def _rows(t, prior):
    return t[t["prior"] == prior]


def _val(t, prior, applies_to, from_date=""):
    r = t[(t["prior"] == prior) & (t["applies_to"] == applies_to) & (t["from_date"] == from_date)]["value"]
    return r.iloc[0] if len(r) else None


def ship_from(t, cust) -> str:
    sites = tuple(s for s in SITES if _val(t, "route", f"{s}>{cust}") == "yes")
    return next((k for k, v in SHIP.items() if v == sites), "nowhere")


def targets(t) -> dict:
    """{group: [(from_date, weeks), ...]} in date order."""
    out = {}
    for _, r in _rows(t, "target_weeks").sort_values("from_date").iterrows():
        out.setdefault(r["applies_to"], []).append((r["from_date"], r["value"]))
    return out


def target_text(steps) -> str:
    parts = []
    for i, (d, w) in enumerate(steps):
        parts.append(wk(w) if i == 0 and d and pd.Timestamp(d) <= PLAN_START else f"{wk(w)} from {fdate(d)}")
    return ", then ".join(parts)


# ---------------- changes in plain words ----------------

def describe_changes(old: pd.DataFrame, new: pd.DataFrame, reasons: dict | None = None) -> pd.DataFrame:
    """Setting | From | To | Why, one row per thing a planner would call a change (routes grouped per channel)."""
    old, new = priors.normalise(old), priors.normalise(new)
    reasons = reasons or {}
    changes = priors.diff(old, new)

    def why(cs):
        return " · ".join(dict.fromkeys(reasons[k] for k in
                                         ((c["prior"], c["applies_to"], c["from_date"], c["new"]) for c in cs)
                                         if k in reasons))

    rows = []
    routed = {c["applies_to"].split(">")[1] for c in changes if c["prior"] == "route"}
    for cust in [c for c in CUSTOMERS if c in routed]:
        cs = [c for c in changes if c["prior"] == "route" and c["applies_to"].endswith(">" + cust)]
        rows.append((f"{CUSTOMERS[cust]} ship from", ship_from(old, cust), ship_from(new, cust), why(cs)))
    for c in changes:
        p, a = c["prior"], c["applies_to"]
        if p == "route":
            continue
        o, n = c["old"], c["new"]
        if p == "build_weeks":
            rows.append((f"Build time · {LINE_NAME.get(a, a)}", wk(o) if o else "—", wk(n) if n else "—", why([c])))
        elif p == "transfer_weeks":
            rows.append(("Transfer time · Reno → PDC", wk(o) if o else "—", wk(n) if n else "—", why([c])))
        elif p == "target_weeks":
            when = "" if c["from_date"] and pd.Timestamp(c["from_date"]) <= PLAN_START else f" from {fdate(c['from_date'])}"
            rows.append((f"Target · {GROUPS.get(a, a)}{when}", wk(o) if o else "—", wk(n) if n else "removed", why([c])))
        elif p == "decides":
            what = "builds" if a == "make" else "transfers to the PDC"
            yes = {"yes": "yes", "no": "no", None: "—"}
            rows.append((f"Plan decides {what}", yes.get(o, o), yes.get(n, n), why([c])))
    return pd.DataFrame(rows, columns=["Setting", "From", "To", "Why"])


def show_changes(table: pd.DataFrame, empty: str = "No changes."):
    if table.empty:
        st.caption(empty)
        return
    cols = ["Setting", "From", "To"] + (["Why"] if table["Why"].str.len().any() else [])
    st.dataframe(table[cols], hide_index=True, width="stretch",
                 column_config={"Setting": st.column_config.TextColumn(width="large"),
                                "Why": st.column_config.TextColumn(width="large")})


# ---------------- settings, read-only ----------------

def settings_view(t: pd.DataFrame, compare: pd.DataFrame | None = None):
    """A scenario's settings as four cards. With `compare`, settings that differ from it are marked."""
    t = priors.normalise(t)
    c = priors.normalise(compare) if compare is not None else None
    mark = lambda same: "" if same else " ◆"
    left, right = st.columns(2, gap="medium")
    with left.container(border=True):
        st.markdown("**Where orders ship from**")
        st.dataframe(pd.DataFrame({
            "Channel": [CUSTOMERS[k] for k in CUSTOMERS],
            "Ships from": [ship_from(t, k) + (mark(ship_from(t, k) == ship_from(c, k)) if c is not None else "")
                           for k in CUSTOMERS]}), hide_index=True, width="stretch")
        move = _val(t, "decides", "move") == "yes"
        st.markdown(f"Transfers Reno → PDC: **{'planned by the optimiser' if move else 'not planned'}**"
                    + (mark(_val(c, 'decides', 'move') == _val(t, 'decides', 'move')) if c is not None else ""))
    with right.container(border=True):
        st.markdown("**Lead times**")
        rows = [(f"Build · {LINE_NAME[ln]}", wk(_val(t, "build_weeks", ln))
                 + (mark(_val(c, "build_weeks", ln) == _val(t, "build_weeks", ln)) if c is not None else ""))
                for ln in LINES]
        rows.append(("Transfer · Reno → PDC", wk(_val(t, "transfer_weeks", "RENO>CMH"))
                     + (mark(_val(c, "transfer_weeks", "RENO>CMH") == _val(t, "transfer_weeks", "RENO>CMH"))
                        if c is not None else "")))
        st.dataframe(pd.DataFrame(rows, columns=["Lead time", "Weeks"]), hide_index=True, width="stretch")
    with st.container(border=True):
        st.markdown("**Weeks-of-supply targets**")
        tg, tc = targets(t), (targets(c) if c is not None else None)
        st.dataframe(pd.DataFrame({
            "Group": [GROUPS.get(g, g) for g in tg],
            "Target": [target_text(s) + (mark(tc.get(g) == s) if tc is not None else "") for g, s in tg.items()]}),
            hide_index=True, width="stretch")
    if c is not None:
        st.caption("◆ differs from the scenario it is compared with.")


# ---------------- settings, editable ----------------

def _steps_key(key, g):
    return f"steps_{key}_{g}"


def _add_step(key, g, default_weeks):
    lst = st.session_state[_steps_key(key, g)]
    nid = max([s["id"] for s in lst], default=0) + 1
    last = max([s["date"] for s in lst], default=START)
    d = min(max(last + dt.timedelta(weeks=26), START + dt.timedelta(weeks=1)), PLAN_END.date())
    d -= dt.timedelta(days=d.weekday())                        # targets start on a Monday, like plan weeks
    lst.append({"id": nid, "date": d, "weeks": default_weeks})


def _remove_step(key, g, sid):
    st.session_state[_steps_key(key, g)] = [s for s in st.session_state[_steps_key(key, g)] if s["id"] != sid]


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def settings_editor(t: pd.DataFrame, key: str) -> pd.DataFrame:
    """Controls for every setting, seeded from table t; returns the table as set (not validated).
    `key` must change to re-seed the controls from a new table."""
    t = priors.normalise(t)
    left, right = st.columns([1, 1], gap="medium")

    with left.container(border=True):
        st.markdown("**Where orders ship from**")
        st.caption("Sites that serve a common channel share their stock; each pool of stock is counted against the "
                   "demand it serves.")
        ship = {}
        for cust, label in CUSTOMERS.items():
            cur = ship_from(t, cust)
            ship[cust] = st.radio(label, list(SHIP), index=list(SHIP).index(cur) if cur in SHIP else None,
                                  horizontal=True, key=f"ship_{cust}_{key}")
        move = st.toggle("Plan transfers from Reno to the PDC", value=_val(t, "decides", "move") == "yes",
                         key=f"move_{key}", help="Needed when the PDC serves a channel on its own. Not allowed when "
                                                 "Reno and the PDC serve the same channel (moving stock between "
                                                 "them would gain nothing).")

    with right.container(border=True):
        st.markdown("**Lead times** (whole weeks)")
        cols = st.columns(2)
        build = {}
        for i, ln in enumerate(LINES):
            build[ln] = cols[i % 2].number_input(f"Build · {LINE_NAME[ln]}", min_value=0, max_value=priors.MAX_WEEKS,
                                                 step=1, value=int(_num(_val(t, "build_weeks", ln))),
                                                 key=f"build_{ln}_{key}")
        transfer = st.number_input("Transfer · Reno → PDC", min_value=0, max_value=priors.MAX_WEEKS, step=1,
                                   value=int(_num(_val(t, "transfer_weeks", "RENO>CMH"), 1)), key=f"transfer_{key}")
        st.caption("Build time: from using line capacity to a bike in Reno stock. Same week = 0.")

    with st.container(border=True):
        st.markdown("**Weeks-of-supply targets**")
        st.caption("Each group's target from the start of the plan. Add a step to change it from a date.")
        W = [1.2, 1.1, 1.4, 0.45]
        h = st.columns(W)
        for col, txt in zip(h, ["Group", "Weeks", "From", ""]):
            col.caption(txt)
        tg = targets(t)
        target_rows = []
        for g, label in GROUPS.items():
            steps = tg.get(g, [])
            base = [s for s in steps if s[0] and pd.Timestamp(s[0]) <= PLAN_START]
            later = [s for s in steps if not (s[0] and pd.Timestamp(s[0]) <= PLAN_START)]
            target_rows += [(g, d, w) for d, w in base[:-1]]       # extra rows before the start: kept as they are
            sk = _steps_key(key, g)
            if sk not in st.session_state:
                st.session_state[sk] = [{"id": i + 1, "date": pd.Timestamp(d).date() if d else START + dt.timedelta(weeks=1),
                                         "weeks": _num(w, 1)} for i, (d, w) in enumerate(later)]
            r = st.columns(W, vertical_alignment="center")
            r[0].markdown(f"**{label}**")
            bw = r[1].number_input(f"{label} · weeks from the start", min_value=0.0, max_value=52.0, step=1.0,
                                   format="%g", value=_num(base[-1][1], 1) if base else 1.0, key=f"tbase_{g}_{key}",
                                   label_visibility="collapsed")
            r[2].markdown("<span class='rw-muted'>start of the plan</span>", unsafe_allow_html=True)
            target_rows.append((g, base[-1][0] if base else START.isoformat(), bw))
            for s in st.session_state[sk]:
                r = st.columns(W, vertical_alignment="center")
                r[0].markdown("<span class='rw-muted'>&nbsp;&nbsp;then</span>", unsafe_allow_html=True)
                w = r[1].number_input(f"{label} · step weeks", min_value=0.0, max_value=52.0, step=1.0, format="%g",
                                      value=s["weeks"], key=f"tw_{g}_{s['id']}_{key}", label_visibility="collapsed")
                d = r[2].date_input(f"{label} · step from", value=s["date"], min_value=START + dt.timedelta(days=1),
                                    max_value=PLAN_END.date(), key=f"td_{g}_{s['id']}_{key}", format="YYYY-MM-DD",
                                    label_visibility="collapsed")
                r[3].button("", key=f"trm_{g}_{s['id']}_{key}", icon=":material/close:", help="Remove this step",
                            on_click=_remove_step, args=(key, g, s["id"]))
                target_rows.append((g, d.isoformat() if d else "", w))
            r = st.columns(W)
            r[1].button("Add a step", key=f"tadd_{g}_{key}", icon=":material/add:", type="tertiary",
                        on_click=_add_step, args=(key, g, bw))
        extra = [g for g in tg if g not in GROUPS]                 # groups the editor does not know: keep as they are
        for g in extra:
            target_rows += [(g, d, w) for d, w in tg[g]]

    rows = []
    for s in SITES:
        for cust in CUSTOMERS:
            rows.append(("route", f"{s}>{cust}", "yes" if ship.get(cust) and s in SHIP[ship[cust]] else "no", ""))
    rows += [("build_weeks", ln, build[ln], "") for ln in LINES]
    rows += [("transfer_weeks", "RENO>CMH", transfer, "")]
    rows += [("target_weeks", g, w, d) for g, d, w in target_rows]
    rows += [("decides", "make", "yes", ""), ("decides", "move", "yes" if move else "no", "")]
    return priors.normalise(pd.DataFrame(rows, columns=priors.COLUMNS))
