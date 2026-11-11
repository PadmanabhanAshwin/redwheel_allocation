"""Page 4 — the balance behind the plan, every SKU: a summary table, then one waterfall per SKU."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from ui import (AT_TARGET, BAD_BG, BUILD, GOOD_BG, H, HIGHLIGHT_BG, INK, LINE_NAME, ORDER, SIZE_COLOR, SKU, WEEKS,
                fmt_date, m, r, style)

st.title("Inventory Balance by SKU")
st.markdown("Each SKU: **opening net position + built − forecast = closing net position**, compared with its target.")

op = m["opening_position"].set_index("sku")
fy = WEEKS.dt.year - (WEEKS.dt.month < 9)

# ---------------- every SKU, one row each ----------------
st.subheader("Balance for every SKU, snapshot to end of horizon")
rows = []
for s in ORDER:
    rows.append({"SKU": s, "Line · size": f"{LINE_NAME[SKU.at[s, 'line_id']]} · {SKU.at[s, 'size']}",
                 "On hand": op.at[s, "on_hand_nettable"], "Backlog": -op.at[s, "backlog"],
                 "= Opening net": r["net"].at[s, 0], "+ Built": BUILD[s].sum(),
                 "− Forecast": -r["demand"].loc[s, 1:H].sum(), "= Closing net": r["net"].at[s, H],
                 "Target": r["target_units"].at[s, H],
                 "Status": "at target" if AT_TARGET.at[s, H] else "below target"})
bal = pd.DataFrame(rows)
num = ["On hand", "Backlog", "= Opening net", "+ Built", "− Forecast", "= Closing net", "Target"]
tot = bal[num].sum()
bal = pd.concat([bal, pd.DataFrame([{"SKU": "All SKUs", "Line · size": "", **tot.to_dict(),
                                     "Status": f"{int(AT_TARGET[H].sum())} of {len(ORDER)} at target"}])],
                ignore_index=True)
ok = list(AT_TARGET[H].loc[ORDER].values) + [bool(AT_TARGET[H].all())]


def look(col):
    if col.name in ("= Opening net", "= Closing net"):
        return [f"background-color: {HIGHLIGHT_BG}; font-weight: 600"] * len(col)
    if col.name == "Status":
        return [f"background-color: {GOOD_BG if g else BAD_BG}" for g in ok]
    return [""] * len(col)


st.dataframe(bal.style.format({c: "{:,.0f}" for c in num}).apply(look, axis=0),
             hide_index=True, width="stretch", height=(len(bal) + 1) * 35 + 3)
st.caption(f"Bicycles, {fmt_date(WEEKS.iloc[0])} to {fmt_date(WEEKS.iloc[-1])}. Read left to right: on hand − backlog "
           "= opening net; + built − forecast = closing net. Target: forecast of the N weeks after the closing week "
           "(N = the SKU's weeks-of-supply target).")

# ---------------- one waterfall per SKU ----------------
st.subheader("One SKU in detail")
steps = [("Opening", "absolute")]
for y in sorted(fy.unique()):
    tag = "Sep–Dec 28" if (fy == y).sum() < 52 else f"FY{y % 100}"
    steps += [(f"Built<br>{tag}", "relative"), (f"Forecast<br>{tag}", "relative")]
steps.append(("Closing", "total"))
xcat = [lbl for lbl, _ in steps]

titles = []
for s in ORDER:
    mark = "at target" if AT_TARGET.at[s, H] else "below target"
    titles.append(f"<b>{s}</b> · {LINE_NAME[SKU.at[s, 'line_id']]} {SKU.at[s, 'size']} · closing {mark}")
fig = make_subplots(rows=5, cols=2, subplot_titles=titles, vertical_spacing=0.07, horizontal_spacing=0.06)
for i, s in enumerate(ORDER):
    rr, cc = i // 2 + 1, i % 2 + 1
    built = pd.Series(BUILD[s], index=WEEKS.index)
    fc = r["demand"].loc[s, 1:H]
    vals = [r["net"].at[s, 0]]
    for y in sorted(fy.unique()):
        wk = fy.index[fy == y]
        vals += [built[wk].sum(), -fc[wk].sum()]
    vals.append(0)
    closing = r["net"].at[s, H]
    text = [f"{v:,.0f}" for v in vals[:-1]] + [f"{closing:,.0f}"]
    fig.add_trace(go.Waterfall(
        x=xcat, y=vals, measure=[k for _, k in steps], text=text, textposition="outside", cliponaxis=False,
        textfont=dict(size=10), connector=dict(line=dict(color="#c9c8c2", width=1)),
        increasing=dict(marker=dict(color=SIZE_COLOR["L"])), decreasing=dict(marker=dict(color=SIZE_COLOR["S"])),
        totals=dict(marker=dict(color=SIZE_COLOR["M"])), hoverinfo="skip", showlegend=False), row=rr, col=cc)
    tgt = r["target_units"].at[s, H]
    fig.add_scatter(x=["Closing"], y=[tgt], mode="markers", showlegend=i == 0, name="target",
                    marker=dict(symbol="line-ew-open", size=34, color=INK, line=dict(color=INK, width=3)),
                    hovertemplate=f"target: {tgt:,.0f}<extra></extra>", row=rr, col=cc)
    level = pd.Series(vals[:-1]).cumsum()                 # running position after each bar
    lo, hi = min(0, level.min()), max(level.max(), tgt)
    pad = (hi - lo) * 0.16                                # room for labels above rises and below falls
    fig.update_yaxes(range=[lo - pad, hi + pad], row=rr, col=cc)
fig.update_xaxes(tickfont=dict(size=10))
fig.update_annotations(font=dict(size=12))
st.plotly_chart(style(fig, 1400), key="waterfalls")
st.caption("Gold: built. Black: forecast. Bronze: opening and closing net position. Black bar on Closing: the target. "
           "FY = September–August.")
