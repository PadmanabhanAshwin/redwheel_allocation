"""Edit a scenario's planning priors with plain controls; the result is the priors table the run reads.

Nothing here decides what is allowed: the edits are turned into a table as typed, and `priors.validate` says what
is wrong with it. An LLM will later propose the same table (as a change list) and go through the same check."""
import pandas as pd
import streamlit as st

from redwheel import priors
from redwheel.config import LINES
from ui import LINE_NAME

SITES = {"RENO": "Reno", "CMH": "PDC (Columbus)"}
CUSTOMERS = {"WEB": "Web", "DEALERS": "Dealers", "COMMERCIAL": "Commercial"}
GROUPS = {"road": "Road", "mtb_base": "MTB base", "mtb_carbon": "MTB carbon"}


def _val(t, prior, applies_to):
    r = t[(t["prior"] == prior) & (t["applies_to"] == applies_to)]["value"]
    return r.iloc[0] if len(r) else ""


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def editor(t: pd.DataFrame, locked: bool, key: str) -> pd.DataFrame:
    """Draw the controls for table t; return the table as edited (not yet validated)."""
    t = priors.normalise(t)
    left, right = st.columns([3, 2], gap="large")

    with left:
        st.markdown("**Routing:** which site may ship each channel's orders")
        routes = pd.DataFrame({CUSTOMERS[c]: [_val(t, "route", f"{s}>{c}") == "yes" for s in SITES] for c in CUSTOMERS},
                              index=pd.Index(list(SITES.values()), name="Ship from"))
        routes = st.data_editor(routes, disabled=locked, key=f"routes_{key}", width="stretch",
                                column_config={c: st.column_config.CheckboxColumn(c) for c in CUSTOMERS.values()})
        st.markdown("**The plan decides**")
        c1, c2 = st.columns(2)
        c1.checkbox("Builds", value=True, disabled=True, key=f"make_{key}", help="Every plan decides builds")
        move = c2.checkbox("Transfers Reno → PDC", value=_val(t, "decides", "move") == "yes", disabled=locked,
                           key=f"move_{key}")

    with right:
        st.markdown("**Lead times** (whole weeks)")
        lead = pd.DataFrame({"Weeks": [_num(_val(t, "build_weeks", ln)) for ln in LINES]
                             + [_num(_val(t, "transfer_weeks", "RENO>CMH"))]},
                            index=pd.Index([f"Build · {LINE_NAME[ln]}" for ln in LINES] + ["Transfer · Reno → PDC"],
                                           name="Lead time"))
        lead = st.data_editor(lead, disabled=locked, key=f"lead_{key}", width="stretch",
                              column_config={"Weeks": st.column_config.NumberColumn("Weeks", min_value=0,
                                                                                    max_value=priors.MAX_WEEKS, step=1)})

    st.markdown("**Weeks-of-supply targets** (a row per target and the date it starts; add a row to step a target)")
    tg = t[t["prior"] == "target_weeks"]
    targets = pd.DataFrame({"Group": tg["applies_to"].values, "From": pd.to_datetime(tg["from_date"].values),
                            "Weeks": tg["value"].map(_num).values})
    targets = st.data_editor(targets, disabled=locked, key=f"targets_{key}", num_rows="fixed" if locked else "dynamic",
                             hide_index=True, width="stretch", column_config={
                                 "Group": st.column_config.SelectboxColumn("Group", options=list(GROUPS),
                                                                           format_func=lambda g: GROUPS.get(g, g)),
                                 "From": st.column_config.DateColumn("From", format="D MMM YYYY"),
                                 "Weeks": st.column_config.NumberColumn("Weeks", min_value=0, max_value=52, step=1)})

    # ---- back to the priors table, exactly as typed ----
    rows = [("route", f"{s}>{c}", "yes" if routes.at[SITES[s], CUSTOMERS[c]] else "no", "")
            for s in SITES for c in CUSTOMERS]
    weeks = lead["Weeks"].tolist()
    rows += [("build_weeks", ln, "" if pd.isna(w) else w, "") for ln, w in zip(LINES, weeks[:-1])]
    rows += [("transfer_weeks", "RENO>CMH", "" if pd.isna(weeks[-1]) else weeks[-1], "")]
    for g, d, w in targets[["Group", "From", "Weeks"]].itertuples(index=False):
        rows.append(("target_weeks", "" if pd.isna(g) else g, "" if pd.isna(w) else w,
                     "" if pd.isna(d) else pd.Timestamp(d).strftime("%Y-%m-%d")))
    rows += [("decides", "make", "yes", ""), ("decides", "move", "yes" if move else "no", "")]
    return priors.normalise(pd.DataFrame(rows, columns=priors.COLUMNS))
