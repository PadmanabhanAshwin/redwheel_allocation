"""The object deck: seven 1920x1080 slides as SVG in one HTML file.

Usage: python3 build.py OUTDIR  ->  OUTDIR/object.html and OUTDIR/p1..p7.html; print object.html to PDF with Chrome.
Data, read from this folder: base_mtb.json (dump_base.py, scenario A) and slide5_builds.json (the solver session,
scenarios A and P1). Numbers that are not in those files are in NUM below; refresh them at the final run.

Notation, used on every slide: r resource, i task, k SKU, t week; X level, N runs, mu amount, theta delay,
pi arrivals, c carry; net = stock - open orders; d = weekly demand over the target window; f floor.
Wording: titles name the topic; text states facts. No claims the numbers on the slide do not show.
"""
import sys, json, pathlib, datetime
out = pathlib.Path(sys.argv[1]); HERE = pathlib.Path(__file__).parent

# ---------------------------------------------------------------- data
BD = json.load(open(HERE / "base_mtb.json"))
SB = json.load(open(HERE / "slide5_builds.json"))
SKUS = ["RW-9304", "RW-4418", "RW-6416"]                 # rule B's order
assert all(SB["A"][k][:52] == BD["builds"][k][:52] for k in SKUS), "slide5_builds.json and base_mtb.json disagree on scenario A"
NUM = {   # from the object, scenario A and the other sessions' notes; refresh from docs/deck/deck_numbers.json at the final run
    "resources": (74, "40 inventory · 30 order · 4 capacity"), "tasks": (80, "10 make · 10 move · 60 fulfil"), "edges": 180,
    "weeks": 121, "files": 9, "tunables": 14,
    "rw4418_open": {"reno": 25, "cmh": 0, "orders": 1310, "dealers": 669, "web": 496, "commercial": 145, "fc": 50},
    "rw4418_floors": (-1285, -123, 0, 857),               # net, due, owed, target in week 1 (NOTE_TO_DECK_BOT.md §2)
    "wk3": {"RW-4418": (142, 247, 389), "RW-6416": (89, 128, 217), "RW-9304": (144, 425, 569)},   # runs, Reno before, after
    "frames_test": "3, 0, 9, 4",
    "p1_steps": 6,
}
RANKED_AT_TARGET = {"RW-9304": "2027-02-22", "RW-4418": "2027-07-26", "RW-6416": "2027-09-06"}   # tests/test_engine.py, scenario P1
WEEK = {int(k): v for k, v in BD["weeks"].items()}; WK_OF = {v: k for k, v in WEEK.items()}
def sdate(t): d = datetime.date.fromisoformat(WEEK[t]); return f"{d.day} {d.strftime('%b')}"
T_CLEAR = WK_OF[list(BD["orders_cleared"].values())[0]]; T_TARGET = BD["on_target_week"]
TURN_END = {k: WK_OF[RANKED_AT_TARGET[k]] for k in SKUS}
NEED = {k: (-BD["net"][k][0], BD["target_units"][k][0]) for k in SKUS}     # owed to customers, target stock, at opening
A_BUILDS = {k: BD["builds"][k][:56] for k in SKUS}; B_BUILDS = {k: SB["P1"][k][:56] for k in SKUS}
def net_path(builds):
    return {k: [BD["net_all"][k][0]] + [BD["net_all"][k][0] + sum(builds[k][:t]) - sum(BD["demand_all"][k][:t]) for t in range(1, 57)] for k in SKUS}
A_NET, B_NET = {k: BD["net_all"][k][:57] for k in SKUS}, net_path(B_BUILDS)

# ---------------------------------------------------------------- style
INK, GREY, LIGHT, RULE_C = "#111827", "#6b7280", "#9ca3af", "#e5e7eb"
AMB, RED, GREEN = "#b45309", "#b91c1c", "#15803d"
COL = {"RW-9304": "#b45309", "RW-4418": "#111827", "RW-6416": "#2563eb"}
CSS = f'''@page{{size:1920px 1080px;margin:0}}
html,body{{margin:0;background:#fff}}
svg{{display:block;font-family:"Helvetica Neue",Helvetica,Arial,sans-serif;page-break-after:always}}
.h1{{font-size:50px;font-weight:700;fill:{INK}}}
.sub{{font-size:25px;fill:{GREY}}}
.tag{{font-size:18px;font-weight:700;fill:{GREY}}}
.name{{font-size:26px;font-weight:600;fill:{INK}}}
.num{{font-size:38px;font-weight:700;fill:{INK}}}
.dim{{fill:{LIGHT};font-weight:400}}
.res{{fill:#fff;stroke:{INK};stroke-width:2.5}}
.task{{fill:{INK}}}
.tname{{font-size:24px;fill:#d1d5db}}
.tnum{{font-size:34px;font-weight:700;fill:#fff}}
.wire{{stroke:{INK};stroke-width:2.5;fill:none}}
.amt{{font-size:24px;font-weight:700;fill:{AMB}}}
.cell{{font-family:Menlo,Consolas,monospace;font-size:26px;fill:{INK}}}
.colh{{font-family:Menlo,Consolas,monospace;font-size:18px;fill:{GREY}}}
.pg{{font-size:18px;fill:{LIGHT}}}'''
DEFS = (f'<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto"><path d="M0 0L10 5L0 10z" fill="{INK}"/></marker>'
        f'<marker id="g" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M0 0L10 5L0 10z" fill="{AMB}"/></marker></defs>')

def page(n, title, sub, body):
    s = f'<text x="110" y="164" class="sub">{sub}</text>' if sub else ""
    return (f'<svg width="1920" height="1080" viewBox="0 0 1920 1080">{DEFS}<text x="110" y="112" class="h1">{title}</text>'
            f'{s}{rule(200)}{body}<text x="1810" y="1048" class="pg" text-anchor="end">{n}</text></svg>')
def rule(y, x1=110, x2=1810): return f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{RULE_C}" stroke-width="2"/>'
def vrule(x, y1, y2): return f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2}" stroke="{RULE_C}" stroke-width="2"/>'
def tag(x, y, s, anchor="start"): return f'<text x="{x}" y="{y}" class="tag" text-anchor="{anchor}">{s}</text>'
def txt(x, y, s, size=22, fill=INK, weight=400, anchor="start"):
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" style="font-size:{size}px;fill:{fill};font-weight:{weight}">{s}</text>'
def lines(x, y, rows, size=22, fill=INK, dy=32): return "".join(txt(x, y + i * dy, r, size, fill) for i, r in enumerate(rows))
def tint(hexcol, a): r, g, b = (int(hexcol[i:i + 2], 16) for i in (1, 3, 5)); return f"rgb({int(255-(255-r)*a)},{int(255-(255-g)*a)},{int(255-(255-b)*a)})"
B_ = lambda s: f'<tspan font-weight="700">{s}</tspan>'

# maths: italic Times identifiers with subscripts
MF = "font-family:Times,serif;font-style:italic"
def v(base, sub="", sz=None):
    s = sz or 19
    t = f'<tspan style="{MF}">{base}</tspan>' if base else ""
    return t + (f'<tspan dy="7" dx="1" style="{MF};font-size:{s}px">{sub}</tspan><tspan dy="-7" style="font-size:10px"> </tspan>' if sub else "")
PLUS = '<tspan dy="-11" style="font-size:16px">+</tspan><tspan dy="11"> </tspan>'
def meq(x, y, s, fs=30, anchor="start", fill=INK): return f'<text x="{x}" y="{y}" text-anchor="{anchor}" style="font-size:{fs}px;fill:{fill};font-family:Times,serif">{s}</text>'

# graph pieces
def res(x, y, w, name, val, h=120): return f'<rect class="res" x="{x}" y="{y}" width="{w}" height="{h}" rx="22"/><text x="{x+26}" y="{y+48}" class="name">{name}</text><text x="{x+26}" y="{y+98}" class="num">{val}</text>'
def task(x, y, name, w=180): return f'<rect class="task" x="{x}" y="{y}" width="{w}" height="120" rx="8"/><text x="{x+w/2}" y="{y+72}" class="tnum" text-anchor="middle">{name}</text>'
def edge(x1, y1, x2, y2, lab, lx=None, ly=None, anchor="middle"):
    lx = (x1 + x2) / 2 if lx is None else lx; ly = y1 - 16 if ly is None else ly
    return f'<path class="wire" marker-end="url(#a)" d="M{x1} {y1} L{x2} {y2}"/><text x="{lx}" y="{ly}" class="amt" text-anchor="{anchor}">{lab}</text>'
def rn(x, c, name, val, w=200):
    return f'<rect class="res" x="{x}" y="{c-36}" width="{w}" height="72" rx="16"/><text x="{x+16}" y="{c-6}" class="name" style="font-size:19px">{name}</text><text x="{x+16}" y="{c+24}" class="num" style="font-size:25px">{val}</text>'
def tk(x, c, name, w=130, h=72, val=None):
    if val is None: return f'<rect class="task" x="{x}" y="{c-h/2}" width="{w}" height="{h}" rx="6"/><text x="{x+w/2}" y="{c+9}" class="tnum" style="font-size:25px" text-anchor="middle">{name}</text>'
    return f'<rect class="task" x="{x}" y="{c-h/2}" width="{w}" height="{h}" rx="6"/><text x="{x+14}" y="{c+7}" class="tname" style="font-size:19px;fill:#fff">{name}</text><text x="{x+w-14}" y="{c+8}" class="tnum" style="font-size:22px" text-anchor="end">{val}</text>'
def ar(x1, y1, x2, y2, lab="", curve=False, ly=None):
    d = f"M{x1} {y1} C{x1+45} {y1} {x2-55} {y2} {x2-4} {y2}" if curve else f"M{x1} {y1} L{x2-4} {y2}"
    t = f'<text x="{(x1+x2)/2}" y="{(ly if ly else min(y1,y2)-12)}" class="amt" style="font-size:21px" text-anchor="middle">{lab}</text>' if lab else ""
    return f'<path class="wire" marker-end="url(#a)" d="{d}"/>{t}'
def arrow_big(x, y, w=34): return f'<path d="M{x} {y} h{w}" stroke="{LIGHT}" stroke-width="4" fill="none"/><path d="M{x+w-4} {y-9} l14 9 l-14 9 z" fill="{LIGHT}"/>'
def pill(x, y, h, letter, col, w=26): return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{col}"/><text x="{x+w/2}" y="{y+h/2+6}" text-anchor="middle" style="font-size:16px;font-weight:700;fill:#fff">{letter}</text>'
def box(x, y, w, h, stroke=INK, dash=False, fill="#fff", sw=2.5):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{" stroke-dasharray=" + chr(34) + "6 5" + chr(34) if dash else ""}/>'

# ================================================================ 1 · system
def stage(x, w, head, sub, rows, top=236, h=470):
    g = box(x, top, w, h) + txt(x + 22, top + 40, head, 26, INK, 700) + txt(x + 22, top + 68, sub, 17, GREY)
    return g + lines(x + 22, top + 112, rows, 18, INK, 28)
def subbox(x, y, w, h, head, rows):
    return box(x, y, w, h, sw=1.5, fill="#f9fafb") + txt(x + 16, y + 30, head, 19, INK, 700) + lines(x + 16, y + 58, rows, 17, INK, 25)
def flow_arrow(x1, x2, y=486): return f'<path class="wire" marker-end="url(#a)" d="M{x1} {y} L{x2-3} {y}"/>'
TOP, H = 236, 470
s1 = (
    stage(110, 270, "Data", f'{NUM["files"]} CSV files', ["Open orders, 3 channels", "Forecast, 3 channels", "Stock: plant, dealers", "Line capacity, weekly"], TOP, H)
    + box(126, 448, 238, 242, stroke=LIGHT, dash=True, sw=1.5) + txt(142, 478, "Assumed", 19, GREY, 700)
    + lines(142, 508, ["Sites: Reno, Columbus", "Reno → Columbus: 1 wk", "Any site ships any", "channel", "1 line slot per bike"], 17, GREY, 25)
    + flow_arrow(380, 420)
    + stage(420, 330, "Object", "Resource–task network",
            [f'{NUM["resources"][0]} resources, {NUM["tasks"][0]} tasks, {NUM["edges"]} edges', "Opening levels", "Arrivals: forecast, capacity", "Order due dates", "Run limits per task"], TOP, H)
    + meq(442, 646, f'{v("X", "r,t")} = {v("c", "r")}{v("X", "r,t−1")} + Σ μ{v("N")} + {v("π", "r,t")}', 24)
    + txt(442, 676, "one balance per resource and week", 16, GREY)
    + flow_arrow(750, 790)
    + box(790, TOP, 360, H) + txt(812, TOP + 40, "Scenario", 26, INK, 700) + txt(812, TOP + 68, f'Stored as data; {NUM["tunables"]} edit forms', 17, GREY)
    + subbox(806, 326, 328, 108, "Changes to the object", ["Stock, capacity, demand, orders,", "build and transfer limits"])
    + subbox(806, 446, 328, 108, "Planning priors", ["Routes, build and transfer times,", "targets, tasks the LP decides"])
    + subbox(806, 566, 328, 128, "Priority order", ["Ordered steps: floor, SKUs,", "sharing rule", "Default: one step, target"])
    + flow_arrow(1150, 1190)
    + stage(1190, 340, "Solver", "Linear program, HiGHS",
            ["Variables: task runs N ≥ 0", "Constraints: balance rows", "Objective: priority order,", "one step at a time", "Rounding to whole bikes", "Plan checks"], TOP, H)
    + meq(1212, 600, f'min  objective', 23) + meq(1212, 632, f's.t.  balance rows,  {v("N")} ≥ 0,  {v("X")} ≥ 0', 23)
    + lines(1212, 664, ["Scenario A: 13,068 variables,", "8,954 balance rows"], 16, GREY, 22)
    + flow_arrow(1530, 1570)
    + stage(1570, 240, "Plan", "Per scenario", ["Builds per SKU, week", "Stock and backlog", "Date each target held", "Check results"], TOP, H)
    + lines(1592, 620, ["Viewed and compared", "in the planner UI"], 17, GREY, 25)
    + box(790, 756, 1020, 150, stroke=AMB) + txt(812, 792, "Claude, at the edges", 22, AMB, 700)
    + txt(812, 826, "Request in words → filled forms → checked in code → proposal for the planner", 18)
    + txt(812, 854, "Sees settings and the catalogue only: no orders, stock or forecasts. Does not run the plan.", 17, GREY)
    + txt(812, 884, "Answers questions about a computed plan from its facts sheet.", 17, GREY)
    + f'<path d="M970 756 L970 712" stroke="{AMB}" stroke-width="2.5" stroke-dasharray="6 5" marker-end="url(#g)"/>'
    + f'<path d="M1690 710 L1690 754" stroke="{AMB}" stroke-width="2.5" stroke-dasharray="6 5" marker-end="url(#g)"/>'
    + txt(110, 970, "Every number in a plan comes from the object and the linear program.", 24, INK, 700)
)
p1 = page(1, "Planning system", "", s1)

# ================================================================ 2 · Redwheel as an RTN
GEN = [("Inventory, order resources", "SKU × location with stock or orders", "SKU master; locations"),
       ("Capacity resources", "one per production line", "capacity plan"),
       ("Make tasks", "one per SKU, on its line", "SKU master: class + trim"),
       ("Move, fulfil tasks", "one per SKU and route", "routes, assumed")]
def generation():
    g = txt(110, 244, "Element", 17, GREY, 700) + txt(400, 244, "Rule", 17, GREY, 700) + txt(770, 244, "Source", 17, GREY, 700)
    for i, (el, rl, src) in enumerate(GEN):
        y = 284 + i * 32
        g += txt(110, y, el, 20, INK, 700) + txt(400, y, rl, 20) + txt(770, y, src, 20, GREY)
    for x, n, lab, br in [(1080, NUM["resources"][0], "resources", NUM["resources"][1]), (1380, NUM["tasks"][0], "tasks", NUM["tasks"][1]), (1640, NUM["edges"], "edges", "")]:
        g += txt(x, 300, f"{n}", 48, INK, 700) + txt(x + (66 if n < 100 else 92), 300, lab, 22) + txt(x, 336, br, 17, GREY)
    return g
U, M = 552, 752
o = NUM["rw4418_open"]
s2_graph = (res(110, M-60, 290, "MTB carbon line", "375 / wk") + edge(400, M, 446, M, "−1", ly=M-22) + task(450, M-60, "make") + edge(630, M, 676, M, "+1", ly=M-22)
    + res(680, M-60, 290, "Reno", f'{o["reno"]} bikes') + edge(970, M, 1246, M, "−1", lx=1010, ly=M-22) + task(1250, M-60, "fulfil") + edge(1430, M, 1496, M, "−1", ly=M-22)
    + edge(790, M-60, 790, U+64, "−1", lx=772, ly=(M+U)/2+10, anchor="end") + task(700, U-60, "move")
    + edge(880, U, 1000, U, "+1, 1 wk", ly=U-22) + res(1004, U-60, 200, "Columbus", f'{o["cmh"]} bikes') + edge(1204, U, 1246, U, "−1", ly=U-22) + task(1250, U-60, "fulfil") + edge(1430, U, 1496, U, "−1", ly=U-22)
    + f'<rect class="res" x="1500" y="{U-60}" width="310" height="{M-U+120}" rx="22"/><text x="1526" y="{U-12}" class="name">Open orders</text><text x="1526" y="{U+40}" class="num">{o["orders"]:,}</text>'
    + "".join(txt(1526, U + 98 + i * 38, a, 21, GREY) + txt(1784, U + 98 + i * 38, f"{b:,}", 21, GREY, anchor="end") for i, (a, b) in enumerate([("Dealers", o["dealers"]), ("Web", o["web"]), ("Commercial", o["commercial"])]))
    + rule(U + 196, 1526, 1784) + txt(1526, U + 234, "Forecast", 21, GREY) + txt(1784, U + 234, f'+{o["fc"]} / wk', 21, GREY, anchor="end"))
p2 = page(2, "Redwheel resource–task network", "Scenario A, opening state on 7 Sep 2026.",
          generation() + vrule(1040, 226, 370) + rule(400) + tag(110, 452, "RW-4418")
          + s2_graph + rule(874)
          + f'<rect class="res" x="110" y="906" width="40" height="26" rx="8"/>' + txt(162, 926, "resource: level", 21, GREY)
          + f'<rect class="task" x="380" y="906" width="40" height="26" rx="5"/>' + txt(432, 926, "task: runs per week", 21, GREY)
          + f'<path class="wire" marker-end="url(#a)" d="M680 919 L722 919"/>' + txt(736, 926, "edge: amount per run; delay in weeks, 0 unless shown", 21, GREY)
          + txt(110, 980, "Decided by the solver: make, and move where the scenario allows. Not decided: fulfil; orders ship as stock allows, oldest first.", 21))

# ================================================================ 3 · material balance
def balance():
    E = 46
    g = meq(110, 288, f'{v("X", "r,t", 21)} =', E) + meq(215, 288, f'{v("c", "r", 21)} {v("X", "r,t−1", 21)}', E) + meq(330, 288, "+", E)
    g += meq(368, 288, f'Σ{v("", "i", 20)}Σ{v("", "θ", 18)} {v("μ", "i,r,θ", 21)} {v("N", "i,t−θ", 21)}', E) + meq(612, 288, "+", E)
    g += meq(650, 288, v("π", "r,t", 21) + ",", E) + meq(790, 288, f'{v("X", "r,t", 21)} ≥ 0', E)
    for x, s_ in [(272, "carry-over"), (490, "task runs"), (676, "arrivals"), (850, "non-negativity")]:
        g += txt(x, 338, s_, 19, AMB, 700, "middle")
    g += vrule(1040, 236, 350)
    g += lines(1080, 262, ["c = 1: inventory, orders", "c = 0: capacity", "π: forecast orders, weekly capacity"], 19, GREY, 30)
    return g
def lane(y, k, runs, a, b):
    c = y + 46
    return (f'<rect class="task" x="700" y="{y}" width="320" height="92" rx="8"/>' + txt(724, y + 34, f"make {k}", 20, "#d1d5db") + txt(724, y + 74, f"N = {runs}", 32, "#fff", 700)
            + f'<path class="wire" marker-end="url(#a)" d="M1020 {c} L1216 {c}"/>' + txt(1118, c - 14, "+1", 24, AMB, 700, "middle")
            + f'<rect class="res" x="1220" y="{y}" width="590" height="92" rx="22"/>' + txt(1246, c + 9, f"{k} at Reno", 26, INK, 600)
            + f'<text x="1784" y="{c+13}" class="num" text-anchor="end">{a} <tspan class="dim">→</tspan> {b}</text>')
YL = [436, 544, 652]; CL = [y + 46 for y in YL]
s3_fan = (f'<path class="wire" marker-end="url(#a)" d="M510 {CL[1]-28} C600 {CL[1]-28} 610 {CL[0]} 696 {CL[0]}"/><path class="wire" marker-end="url(#a)" d="M510 {CL[1]} L696 {CL[1]}"/><path class="wire" marker-end="url(#a)" d="M510 {CL[1]+28} C600 {CL[1]+28} 610 {CL[2]} 696 {CL[2]}"/>'
          + txt(640, CL[0] - 18, "−1", 24, AMB, 700, "end") + txt(640, CL[1] - 14, "−1", 24, AMB, 700, "end") + txt(640, CL[2] + 38, "−1", 24, AMB, 700, "end")
          + f'<rect class="res" x="110" y="{CL[1]-80}" width="400" height="160" rx="22"/>' + txt(136, CL[1] - 34, "MTB carbon line", 26, INK, 600)
          + f'<text x="136" y="{CL[1]+18}" class="num">375 <tspan class="dim">→</tspan> 0</text>' + txt(136, CL[1] + 56, "available → unused", 21, GREY))
w3 = NUM["wk3"]
def term_table():
    xs = [980, 1330, 1560, 1790]
    g = "".join(meq(x, 800, h, 24, "end", GREY) for x, h in zip(xs, [f'{v("c")}·{v("X", "t−1")}', f'Σ μ·{v("N")}', v("π", "t"), f'= {v("X", "t")}']))
    runs = " ".join(f"−{w3[k][0]}" for k in ["RW-4418", "RW-6416", "RW-9304"])
    for y, name, kind, vals in [(846, "MTB carbon line", "capacity, c = 0", ["0", runs, "+375", "= 0"]),
                                (892, "RW-4418 at Reno", "inventory, c = 1", [f'{w3["RW-4418"][1]}', f'+{w3["RW-4418"][0]}', "0", f'= {w3["RW-4418"][2]}'])]:
        g += txt(110, y, f'{B_(name)}  <tspan style="fill:{GREY};font-size:20px">{kind}</tspan>', 25)
        g += "".join(f'<text x="{x}" y="{y}" class="cell" text-anchor="end">{s}</text>' for x, s in zip(xs, vals))
    return g
p3 = page(3, "Material balance", "",
          balance() + rule(370) + tag(110, 412, "MTB carbon line, week of 21 Sep 2026, scenario A; Reno stock before orders ship")
          + s3_fan + "".join(lane(y, k, w3[k][0], w3[k][1], w3[k][2]) for y, k in zip(YL, ["RW-4418", "RW-6416", "RW-9304"]))
          + term_table() + rule(926)
          + txt(110, 978, f'{NUM["resources"][0]} resources × {NUM["weeks"]} weeks = {NUM["resources"][0] * NUM["weeks"]:,} balance equations.', 25))

# ================================================================ 4 · network structures
dA = lambda x, c: tk(x, c, "make") + ar(x+130, c, x+200, c, "+1") + rn(x+200, c, "Reno stock", "25") + ar(x+400, c, x+470, c, "−1") + tk(x+470, c, "move")
dB = lambda x, c: (rn(x, c, "MTB carbon line", "375 / wk", w=210) + "".join(ar(x+210, c+d0, x+330, c+d1, curve=True) for d0, d1 in [(-14, -58), (0, 0), (14, 58)])
                   + "".join(tk(x+330, c+dy, f"make {k}", w=250, h=46, val=str(w3[k][0])) for dy, k in [(-58, "RW-4418"), (0, "RW-6416"), (58, "RW-9304")])
                   + f'<text x="{x+270}" y="{c-52}" class="amt" style="font-size:21px" text-anchor="middle">−1</text>')
dC = lambda x, c: (rn(x, c-44, "Line capacity", "available") + rn(x, c+44, "Frames on hand", "3") + ar(x+200, c-44, x+330, c-12, "−1", ly=c-44) + ar(x+200, c+44, x+330, c+12, "−1", ly=c+62) + tk(x+330, c, "make"))
dD = lambda x, c: rn(x, c, "Reno, week t", "−1") + ar(x+200, c, x+270, c) + tk(x+270, c, "move") + ar(x+400, c, x+530, c, "+1, 1 wk") + rn(x+530, c, "Columbus, week t+1", "+1", w=260)
def panel(px, py, shape, effect, diagram, l1, l2):
    return (txt(px, py, f'{B_(shape)}  <tspan style="fill:{GREY}">·</tspan>  <tspan style="fill:{AMB};font-weight:700">{effect}</tspan>', 28)
            + diagram(px, py + 118) + txt(px, py + 232, l1, 22) + txt(px, py + 264, l2, 20, GREY))
ws = " + ".join(str(w3[k][0]) for k in ["RW-4418", "RW-6416", "RW-9304"])
p4 = page(4, "Network structures", "",
          panel(110, 262, "Series", "dependency", dA, "Runs of move are bounded by Reno stock.", "Reno stock: 25 at opening, plus runs of make.")
          + panel(1000, 262, "Shared input", "competition", dB, "Runs of the three make tasks sum to at most 375.", f"Week of 21 Sep 2026: {ws} = 375.")
          + rule(578)
          + panel(110, 640, "Joint input", "matching", dC, "Runs of make are bounded by the scarcer input.", f"Test case, frames on a 2-week lead time: builds {NUM['frames_test']}.")
          + panel(1000, 640, "Delay", "lag", dD, "Output arrives θ weeks after the run.", "Counted as in-transit stock in between.")
          + rule(960) + txt(110, 1010, "Each structure follows from the balance and X ≥ 0; none is a separate constraint.", 24))

# ================================================================ 5 · linear program
SH = ["9304", "4418", "6416"]; OPEN_STOCK = {"9304": 10, "4418": 25, "6416": 15}
def Ns(n): return f'<tspan>N</tspan><tspan dy="6" style="font-size:68%">{n}</tspan><tspan dy="-6"> </tspan>'
def frag(y0=330):
    C = [y0, y0 + 90, y0 + 180]; cy = C[1]
    g = f'<rect class="res" x="110" y="{cy-40}" width="150" height="80" rx="14"/>' + txt(124, cy - 8, "line capacity", 17, INK, 600) + txt(124, cy + 22, "375", 23, INK, 700)
    for c, n in zip(C, SH):
        g += f'<path class="wire" style="stroke-width:2" marker-end="url(#a)" d="M260 {cy+(c-cy)/8} C292 {cy+(c-cy)/8} 282 {c} 312 {c}"/>'
        g += f'<rect class="task" x="316" y="{c-24}" width="140" height="48" rx="6"/>' + txt(386, c + 6, f"make {n}", 17, "#fff", 400, "middle")
        g += f'<path class="wire" style="stroke-width:2" marker-end="url(#a)" d="M456 {c} L492 {c}"/>'
        g += f'<rect class="res" x="496" y="{c-24}" width="146" height="48" rx="12" style="stroke-width:2"/>' + txt(508, c + 6, f"stock {n}", 16, INK, 600) + txt(632, c + 7, OPEN_STOCK[n], 19, INK, 700, "end")
    return g + txt(290, y0 - 12, "−1", 18, AMB, 700, "middle") + txt(474, y0 - 10, "+1", 18, AMB, 700, "middle")
def edgetable(y0=296):
    g = "".join(f'<text x="{x}" y="{y0}" class="colh" style="font-size:17px" text-anchor="{a}">{h}</text>' for x, h, a in [(730, "task", "start"), (880, "resource", "start"), (1090, "μ", "end"), (1160, "θ", "end")])
    y = y0 + 34
    for n in SH:
        for rname, amt in [("line capacity", "−1"), (f"stock {n}", "+1")]:
            g += (f'<text x="730" y="{y}" class="cell" style="font-size:19px">make {n}</text><text x="880" y="{y}" class="cell" style="font-size:19px">{rname}</text>'
                  f'<text x="1090" y="{y}" class="cell" style="font-size:19px;font-weight:700;fill:{AMB}" text-anchor="end">{amt}</text><text x="1160" y="{y}" class="cell" style="font-size:19px" text-anchor="end">0</text>')
            y += 38
    return g
def grid(x, y):
    cols = [x + 300, x + 372, x + 444]; x0 = x + 210
    g = f'<text x="{x0}" y="{y-14}" text-anchor="end" class="colh" style="font-size:16px">start</text><text x="{x+520}" y="{y-14}" class="colh" style="font-size:16px">level</text>'
    g += "".join(f'<text x="{c}" y="{y-14}" text-anchor="middle" class="colh" style="font-size:18px;fill:{AMB}">{Ns(n)}</text>' for c, n in zip(cols, SH))
    rows = [("line capacity", "375", ["−1", "−1", "−1"]), ("stock 9304", "10", ["+1", "", ""]), ("stock 4418", "25", ["", "+1", ""]), ("stock 6416", "15", ["", "", "+1"])]
    g += f'<path d="M{cols[0]-34} {y} h-8 v{46*4} h8 M{cols[2]+34} {y} h8 v{46*4} h-8" fill="none" stroke="{INK}" stroke-width="2"/>'
    for i, (lab, st, ent) in enumerate(rows):
        yy = y + 46 * i + 31
        g += txt(x, yy, lab, 19, INK, 600) + f'<text x="{x0}" y="{yy}" text-anchor="end" class="cell" style="font-size:22px">{st}</text>'
        g += "".join(f'<text x="{c}" y="{yy}" text-anchor="middle" class="cell" style="font-size:22px;font-weight:700">{e}</text>' for c, e in zip(cols, ent))
        g += f'<text x="{x+520}" y="{yy}" class="cell" style="font-size:22px">≥ 0</text>'
    return g
def head_bar(x, y, w, col, s): return f'<rect x="{x}" y="{y}" width="{w}" height="44" rx="12" fill="{col}"/><rect x="{x}" y="{y+30}" width="{w}" height="14" fill="{col}"/>' + txt(x + 22, y + 30, s, 18, "#fff", 700)
SHORT = f'({v("target", "k,t")} − {v("net", "k,t")}){PLUS}÷ {v("d", "k,t")}'
STEP = f'({v("f", "j,k,t")} − {v("net", "k,t")}){PLUS}÷ {v("d", "k,t")}'
def lp_panel():
    g = f'<rect x="110" y="640" width="980" height="300" rx="12" fill="#fff" stroke="{INK}" stroke-width="2.5"/>' + head_bar(110, 640, 980, INK, "Constraints: generated from the object")
    rows = [(738, "Variables", f'{v("N", "k,t")} ≥ 0', "runs of make task k in week t"),
            (812, "Balance", f'{v("X", "line,t")} = 375 − Σ{v("", "k")} {v("N", "k,t")} ≥ 0', "line capacity"),
            (872, "", f'{v("X", "k,t")} = {v("X", "k,t−1")} + {v("N", "k,t")} ≥ 0', "stock")]
    for y, lab, eq, mean in rows:
        g += txt(132, y, lab, 22, INK, 700) + meq(280, y, eq, 29) + txt(760, y, mean, 20, GREY)
    g += rule(764, 132, 1068) + txt(132, 918, "One variable per task node; one row per resource node. Coefficients μ from the edge table.", 17, GREY)
    g += f'<rect x="1120" y="640" width="690" height="300" rx="12" fill="#fff" stroke="{AMB}" stroke-width="2.5"/>' + head_bar(1120, 640, 690, AMB, "Objective: set by the scenario")
    g += txt(1142, 726, "A · today", 19, INK, 700) + meq(1260, 726, f'min  Σ{v("", "t")} max{v("", "k")} {SHORT}', 25)
    g += txt(1142, 790, "B · priority order", 19, INK, 700) + txt(1142, 818, "for j = 1 … J:", 17, GREY)
    g += meq(1290, 818, f'min  Σ{v("", "t")} max{v("", "k∈Sⱼ")} {STEP}', 25)
    g += txt(1290, 848, "subject to steps 1 … j−1 at their optimum", 17, GREY)
    g += lines(1142, 890, ["net: stock − open orders · d: weekly demand over the target window", "f: −(orders not yet due), 0 or target · A = B with one step"], 15, GREY, 22)
    return g
p5 = page(5, "Linear program", "MTB carbon line and its three SKUs, week of 7 Sep 2026.",
          tag(110, 250, "Graph") + frag() + arrow_big(662, 420)
          + tag(730, 250, "Edge table") + edgetable() + arrow_big(1184, 420)
          + tag(1250, 250, "Balance rows") + grid(1250, 330)
          + txt(1250, 556, f'Row 1: 375 − {Ns("9304")}− {Ns("4418")}− {Ns("6416")}≥ 0.', 19, GREY) + txt(1250, 584, "Each ±1 is one row of the edge table.", 19, GREY)
          + lp_panel())

# ================================================================ 6 · priority orders
def stepline(x, y, n, s, col=AMB):
    return f'<circle cx="{x+12}" cy="{y-6}" r="12" fill="{col}"/>' + txt(x + 12, y - 1, n, 14, "#fff", 700, "middle") + txt(x + 34, y, s, 18)
def pipeline():
    top, h = 222, 268
    g = box(110, top, 450, h, stroke=AMB) + txt(130, top + 34, "1  Priority order", 21, INK, 700) + txt(130, top + 58, "on the scenario, as data", 16, GREY)
    for n, (fl, who) in enumerate([("due", "all SKUs · even"), ("owed", "all SKUs · even"), ("target", "RW-9304"), ("target", "RW-4418"),
                                    ("target", "RW-6416"), ("target", "other lines · even")], start=1):
        g += stepline(130, top + 92 + (n - 1) * 26, str(n), f'{B_(fl)} · {who}')
    g += txt(130, top + 254, "Rule A: one step, target · all SKUs · even", 16, GREY)
    g += arrow_big(566, top + h / 2, 28)
    g += box(608, top, 470, h, stroke=INK) + txt(628, top + 34, "2  Floors", 21, INK, 700) + txt(628, top + 58, "read from the object, per SKU and week", 16, GREY)
    g += lines(628, top + 96, [f'{B_("due")} = −(open orders not yet due)', f'{B_("owed")} = 0', f'{B_("target")} = forecast, next 15 weeks'], 18, INK, 30)
    nf = NUM["rw4418_floors"]
    g += txt(628, top + 214, f'RW-4418, week 1: net {nf[0]:,}', 16, GREY) + txt(628, top + 240, f'floors {nf[1]} · {nf[2]} · {nf[3]}; due dates are on the object', 16, GREY)
    g += arrow_big(1084, top + h / 2, 28)
    g += box(1126, top, 684, h, stroke=INK) + txt(1146, top + 34, "3  Linear program, one solve per step", 21, INK, 700)
    g += txt(1146, top + 58, "same variables and balance rows as for rule A", 16, GREY)
    g += txt(1146, top + 100, "add", 17, GREY) + meq(1196, top + 100, f'{v("s", "k,t")} ≥ {v("f", "k,t")} − {v("net", "k,t")},   {v("s", "k,t")} ≥ 0', 25)
    g += txt(1146, top + 142, "solve", 17, GREY) + meq(1206, top + 142, f'min  Σ{v("", "t")} max{v("", "k∈Sⱼ")} {v("s", "k,t")} ÷ {v("d", "k,t")}', 25)
    g += txt(1146, top + 184, "hold", 17, GREY) + txt(1196, top + 184, "add the row: step objective ≤ its optimum; next step", 18)
    g += txt(1146, top + 244, f'Rule B: {NUM["p1_steps"]} steps, {NUM["p1_steps"] + 1} solves (the last trims stock above target)', 16, GREY)
    return g
def context(top):
    g = tag(110, top, "Opening, 7 Sep 2026")
    g += f'<rect x="110" y="{top+20}" width="14" height="14" fill="{RED}"/>' + txt(132, top + 33, "owed to customers", 16, GREY)
    g += f'<rect x="290" y="{top+20}" width="14" height="14" fill="{LIGHT}"/>' + txt(312, top + 33, "target stock", 16, GREY)
    sc = 380 / 2300; tot = 0
    for r, k in enumerate(SKUS):
        y = top + 78 + r * 74; owed, tg = NEED[k]; tot += owed + tg
        g += f'<rect x="110" y="{y-16}" width="16" height="16" fill="{COL[k]}"/>' + txt(134, y, k, 20, INK, 700) + txt(490, y, f'{owed+tg:,.0f}', 19, INK, 700, "end")
        g += f'<rect x="110" y="{y+10}" width="{owed*sc}" height="28" fill="{RED}"/><rect x="{110+owed*sc+2}" y="{y+10}" width="{tg*sc}" height="28" fill="{LIGHT}"/>'
        g += txt(120, y + 30, f"{owed:,.0f}", 15, "#fff", 700) + txt(110 + owed * sc + 10, y + 30, f"{tg:,.0f}", 15, INK, 700)
    g += txt(110, top + 322, f"{tot:,.0f} bikes required", 24, INK, 700) + txt(110, top + 354, "375 built per week", 24, INK, 700)
    return g
BX = lambda j: 680 + j * 87
def blocks(y0, data, hh, ref=None):
    g = ""
    for j in range(13):
        top = y0
        for k in SKUS:
            val = round(sum(data[k][j * 4:j * 4 + 4]) / 4); h = val / 375 * hh; top -= h
            g += f'<rect x="{BX(j)-35}" y="{top}" width="70" height="{h-1.5}" fill="{COL[k]}"/>'
            rv = ref and round(sum(ref[k][j * 4:j * 4 + 4]) / 4)
            if h >= 19 and rv and abs(val - rv) > 0.15 * rv: g += txt(BX(j), top + h / 2 + 6, val, 15, "#fff", 700, "middle")
    return g + f'<line x1="{BX(0)-40}" y1="{y0}" x2="{BX(12)+40}" y2="{y0}" stroke="{INK}" stroke-width="2"/>'
def bracket(j0, j1, y, lab, col):
    x0, x1 = BX(j0) - 35, BX(j1) + 35
    return f'<path d="M{x0} {y} v7 h{x1-x0} v-7" fill="none" stroke="{col}" stroke-width="2.5"/>' + txt((x0 + x1) / 2, y + 26, lab, 16, col, 700, "middle")
def plans(top):
    g = tag(645, top, "Builds per week, four-week average")
    lx = 1090
    for k in SKUS:
        g += f'<rect x="{lx}" y="{top-14}" width="15" height="15" fill="{COL[k]}"/>' + txt(lx + 22, top, k, 16, INK, 600); lx += 120
    g += txt(1810, top, "labels: B differs from A by > 15%", 15, GREY, 400, "end")
    hh = 104; ya = top + 22 + hh; yb = ya + 36 + hh
    g += pill(645 - 44, ya - hh, hh, "A", INK) + blocks(ya, A_BUILDS, hh)
    avg = [round(sum(A_BUILDS[k][1:52]) / 51 / 10) * 10 for k in SKUS]
    g += txt((BX(0) + BX(12)) / 2, ya + 24, f"A: about {avg[0]} / {avg[1]} / {avg[2]} per week; all three at target {sdate(T_TARGET)} 2027", 15, GREY, 400, "middle")
    g += pill(645 - 44, yb - hh, hh, "B", AMB) + blocks(yb, B_BUILDS, hh, ref=A_BUILDS)
    g += "".join(txt(BX(j), yb + 20, sdate(j * 4 + 1), 14, GREY, 400, "middle") for j in range(13))
    j9, j4, jc = (TURN_END["RW-9304"] - 1) // 4, (TURN_END["RW-4418"] - 1) // 4, (T_CLEAR - 1) // 4
    yy = yb + 30
    g += bracket(0, jc - 1, yy, "steps 1–2", GREY) + bracket(jc, j9 - 1, yy, f"step 3 · RW-9304 at target {sdate(TURN_END['RW-9304'])}", COL["RW-9304"])
    g += bracket(j9, j4 - 1, yy, f"step 4 · RW-4418 at target {sdate(TURN_END['RW-4418'])}", COL["RW-4418"]) + bracket(j4, 12, yy, f"step 5 · {sdate(TURN_END['RW-6416'])}", COL["RW-6416"])
    return g
p6 = page(6, "Priority orders", "Rule B (scenario P1) against rule A (scenario A), MTB carbon line.",
          pipeline() + rule(512) + context(548) + vrule(560, 528, 924) + plans(548) + rule(950)
          + txt(110, 998, f"No customer waiting from {sdate(T_CLEAR)} 2026 under both rules. Total built per week identical.", 23))

# ================================================================ 7 · the planner's grid
GX = lambda j: 560 + j * 170; RH = 27
def grid_block(top, k, role):
    g = f'<rect x="110" y="{top-17}" width="18" height="18" fill="{COL[k]}"/>' + txt(138, top, k, 22, INK, 700) + txt(250, top, role, 18, GREY)
    per = lambda arr, j: round(sum(arr[j * 8:j * 8 + 8]))
    rows = [("Orders in (forecast)", [None] + [per(BD["demand_all"][k], j) for j in range(7)], "ctx"),
            ("Target stock", [round(BD["target_all"][k][0])] + [round(BD["target_all"][k][j * 8 + 7]) for j in range(7)], "ctx"),
            ("built", [None] + [per(A_BUILDS[k], j) for j in range(7)], "built"),
            ("end: backlog (−) or stock", [round(A_NET[k][0])] + [round(A_NET[k][j * 8 + 8]) for j in range(7)], "net"),
            ("built", [None] + [per(B_BUILDS[k], j) for j in range(7)], "built"),
            ("end: backlog (−) or stock", [round(B_NET[k][0])] + [round(B_NET[k][j * 8 + 8]) for j in range(7)], "net")]
    tgt = rows[1][1]; y1 = top + 30
    g += pill(110, y1 + 2 * RH - 19, 2 * RH - 4, "A", INK) + pill(110, y1 + 4 * RH - 19, 2 * RH - 4, "B", AMB)
    for r, (lab, vals, kind) in enumerate(rows):
        y = y1 + r * RH; ctx = kind == "ctx"
        g += txt(110 if ctx else 148, y, lab, 17, GREY if ctx else INK, 700 if kind == "net" else 400)
        for j, val in enumerate(vals):
            if val is None: continue
            fill, col, w = None, (GREY if ctx else INK), 400
            if kind == "net":
                if val < 0: fill, col, w = tint(RED, 0.14), RED, 700
                elif val >= tgt[j] - 1: fill, col, w = tint(GREEN, 0.14), GREEN, 700
                else: fill = "#eef0f3"
            if fill: g += f'<rect x="{GX(j)-64}" y="{y-19}" width="128" height="{RH-3}" rx="4" fill="{fill}"/>'
            if kind == "net" and val >= tgt[j] - 1: g += f'<rect x="{GX(j)-64}" y="{y-19}" width="128" height="{RH-3}" rx="4" fill="none" stroke="{GREEN}" stroke-width="2"/>'
            g += f'<text x="{GX(j)+56}" y="{y}" text-anchor="end" class="cell" style="font-size:17px;font-weight:{w};fill:{col}">{val:,}</text>'
    if k == SKUS[-1]:
        vals = rows[5][1]; zs = [j for j, x in enumerate(vals) if x == 0]; y = y1 + 5 * RH
        if zs: g += f'<rect x="{GX(zs[0])-68}" y="{y-23}" width="{GX(zs[-1])-GX(zs[0])+136}" height="{RH+5}" rx="6" fill="none" stroke="{AMB}" stroke-width="2" stroke-dasharray="5 4"/>'
    return g
def grid_head(y):
    return txt(GX(0) + 56, y, "opening", 16, INK, 700, "end") + "".join(txt(GX(j + 1) + 56, y, f"{sdate(j*8+1)} – {sdate(j*8+8)}", 16, INK, 700, "end") for j in range(7))
ROLE = {SKUS[0]: "rule B, step 3", SKUS[1]: "rule B, step 4", SKUS[2]: "rule B, step 5"}
at = {k: datetime.date.fromisoformat(RANKED_AT_TARGET[k]) for k in SKUS}
p7 = page(7, "Build plans by period", "Eight-week periods. End of period = previous end + built − orders in.",
          pill(110, 222, 28, "A", INK) + txt(148, 242, f'{B_("Rule A")} · one step: target, all SKUs, even', 19)
          + pill(760, 222, 28, "B", AMB) + txt(798, 242, f'{B_("Rule B")} · due, owed, then target for RW-9304, RW-4418, RW-6416 in turn', 19)
          + grid_head(284) + "".join(grid_block(318 + i * 196, k, ROLE[k]) + (rule(318 + i * 196 + 176) if i < 2 else "") for i, k in enumerate(SKUS))
          + rule(892)
          + f'<rect x="110" y="910" width="40" height="22" rx="4" fill="{tint(RED, 0.14)}"/>' + txt(160, 927, "backlog", 17)
          + '<rect x="260" y="910" width="40" height="22" rx="4" fill="#eef0f3"/>' + txt(310, 927, "stock below target", 17)
          + f'<rect x="490" y="910" width="40" height="22" rx="4" fill="{tint(GREEN, 0.14)}" stroke="{GREEN}" stroke-width="2"/>' + txt(540, 927, "at target", 17)
          + f'<rect x="680" y="910" width="40" height="22" rx="4" fill="none" stroke="{AMB}" stroke-width="2" stroke-dasharray="5 4"/>' + txt(730, 927, "no stock, no backlog", 17)
          + txt(110, 976, f'{B_("At target")} · A: all three {sdate(T_TARGET)} 2027 · B: RW-9304 {at["RW-9304"].day} {at["RW-9304"]:%b %Y}, RW-4418 {at["RW-4418"].day} {at["RW-4418"]:%b %Y}, RW-6416 {at["RW-6416"].day} {at["RW-6416"]:%b %Y}', 24)
          + txt(110, 1012, f'{B_("Rule B")} · RW-6416 holds no stock from December 2026 to July 2027.', 24))

pages = [p1, p2, p3, p4, p5, p6, p7]
head = f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>'
(out / "object.html").write_text(head + "".join(pages) + "</body></html>")
for i, p in enumerate(pages, 1): (out / f"p{i}.html").write_text(head + p + "</body></html>")
