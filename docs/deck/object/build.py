"""The object deck: six 1920x1080 slides as SVG in one HTML file.

Usage: python3 build.py OUTDIR  ->  OUTDIR/object.html and OUTDIR/p1..p6.html; print object.html to PDF with Chrome.
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
TOP1, BOT1, RTOP = 222, 800, 586
def stage(x, w, head, sub, rows, red, dy=23):
    g = box(x, TOP1, w, BOT1 - TOP1) + txt(x + 20, TOP1 + 38, head, 26, INK, 700) + txt(x + 20, TOP1 + 64, sub, 17, GREY)
    y = TOP1 + 104
    for r in rows:
        if r.startswith("§"): y += 10; g += meq(x + 20, y, r[1:], 22); y += 10
        elif r.startswith("~"): g += txt(x + 20 + (18 if r[1:].startswith("\t") else 0), y, r[1:].lstrip("\t"), 16, GREY)
        else: g += txt(x + 20 + (18 if r.startswith("\t") else 0), y, r.lstrip("\t"), 17)
        y += dy
    g += f'<rect x="{x+10}" y="{RTOP}" width="{w-20}" height="{BOT1-RTOP-10}" rx="8" fill="#f3f4f6"/>' + txt(x + 22, RTOP + 26, "Redwheel", 15, AMB, 700)
    return g + "".join(txt(x + 22 + (16 if r.startswith("\t") else 0), RTOP + 52 + i * 24, r.lstrip("\t"), 17) for i, r in enumerate(red))
def flow_arrow(x1, x2, y=(TOP1 + BOT1) / 2): return f'<path class="wire" marker-end="url(#a)" d="M{x1} {y} L{x2-3} {y}"/>'
SC = json.load(open(next(f for f in (HERE.parent / "deck_numbers.json", HERE / "deck_numbers.json") if f.exists())))   # the solver session's end-to-end run
A_SC = SC["A"]["scorecard"]; A_HELD = datetime.date.fromisoformat(A_SC["All targets held from"])
N_SCEN = len([k for k in SC if not k.startswith("_") and "+" not in k])
s1 = (
    stage(110, 260, "Data", "inputs",
          ["Part master", "Locations, routes", "Inventory by location", "Open orders, due dates", "Demand forecast", "Capacity", "Lead times, targets"],
          ["10 SKUs on 4 lines", "2 sites, 3 channels", "Routes and lead times", "assumed"])
    + flow_arrow(370, 410)
    + stage(410, 430, "Object  𝒪", "resource–task network",
            [f'{B_("Resource")} r: a quantity with a level X per period', "\tinventory, open orders, capacity",
             f'{B_("Task")} i: an operation with N runs per period. A run', "\tconsumes and yields resources at offsets θ: one", "\tresource into another, or the same one released",
             f'{B_("Edge")} (i, r): amount μ per run (&lt; 0 consumed,', "\t&gt; 0 yielded) at offset θ",
             "§" + f'{v("X", "r,t")} = {v("c", "r")}{v("X", "r,t−1")} + Σ{v("", "i")}Σ{v("", "θ")} μ {v("N", "i,t−θ")} + {v("π", "r,t")},   {v("X")} ≥ 0',
             "c: 1 for stock and orders, 0 for capacity · π: arrivals"],
            [f'{NUM["resources"][0]} resources, {NUM["tasks"][0]} tasks, {NUM["edges"]} edges', f'{NUM["weeks"]} weekly periods from 7 Sep 2026', "Detail on the next slide"])
    + flow_arrow(840, 880)
    + stage(880, 330, "Scenario", "edits to 𝒪, rules, objective",
            [f'{B_("Edits to 𝒪")}: opening levels, arrivals,', "\trun limits, delays θ", f'{B_("Rules")}: permitted routes; task kinds', "\tthe solver decides",
             f'{B_("Objective")}: stock targets; priority', "\torder as ordered steps",
             "~Examples", "~\tline down 3 weeks: capacity = 0", "~\tweb orders from Columbus: route", "~\tRW-9304 first: priority order"],
            [f"{N_SCEN} scenarios", "A: base", "B: web orders from Columbus", "E1–E5: events", "P1: priority order"])
    + flow_arrow(1210, 1250)
    + stage(1250, 290, "Solver", "method by problem structure",
            ["LP: build and transfer plans", "MIP: lot sizes, set-ups,", "\tminimum runs", "Heuristics: dispatch and", "\tallocation rules", "Sampling: safety stock", "\tunder uncertainty"],
            ["LP in HiGHS", "Variables: runs N ≥ 0", "Rows: one balance per", "\tresource and period", "Objective: priority order", "A: 13,068 variables, &lt; 0.2 s", "Lots: by rounding the LP"])
    + flow_arrow(1540, 1580)
    + stage(1580, 230, "Plan", "per scenario", ["Runs N per task and", "\tperiod: the build plan", "Levels X: stock, backlog", "Date each target is met", "Feasibility checks"],
            [f'A: {A_SC["Bikes built"]:,} bikes', "all targets held from", f"{A_HELD.day} {A_HELD:%b %Y}"])
    # planning question
    + box(110, 822, 730, 176) + txt(130, 856, "Planning question", 21, INK, 700)
    + meq(130, 896, "q = (𝒪, σ, Ω),   answer = Ω(𝒪 | σ)", 30)
    + txt(130, 926, "𝒪 object · σ scope: resources, tasks, horizon · Ω operator: project, decide, intervene, diagnose, evaluate", 15, GREY)
    + txt(130, 958, f'{B_("Example")}  E1: “MTB carbon line down 3 weeks from 1 Mar 2027”', 16)
    + txt(130, 982, "𝒪: the network · σ: the line’s 3 SKUs, 121 weeks · Ω: intervene, decide, evaluate against A", 16)
    # LLM interface
    + box(880, 822, 930, 176, stroke=AMB) + txt(900, 856, "LLM interface", 21, AMB, 700)
    + txt(900, 892, f'{B_("Input")}  natural-language request → typed edit forms → validated in code → proposal for approval', 17)
    + txt(900, 922, f'{B_("Output")}  answers stated from computed results only', 17)
    + txt(900, 958, "No free-form model formulation: the LLM fills fixed forms; it does not write constraints or solve.", 16, GREY)
    + txt(900, 982, "No access to orders, stock or forecasts.", 16, GREY)
    + f'<path d="M1045 822 L1045 803" stroke="{AMB}" stroke-width="2.5" stroke-dasharray="5 4" marker-end="url(#g)"/>'
    + f'<path d="M1695 803 L1695 820" stroke="{AMB}" stroke-width="2.5" stroke-dasharray="5 4" marker-end="url(#g)"/>'
)
p1 = page(1, "Planning system", "", s1)

# ================================================================ 2 · Redwheel as an RTN
BREAK = [(NUM["resources"][0], "resources", [("40", "inventory", "10 SKUs × {Reno, Columbus, in transit, dealers}"), ("30", "order", "10 SKUs × {web, dealer, commercial}"), ("4", "capacity", "one per line")]),
         (NUM["tasks"][0], "tasks", [("10", "make", "one per SKU, on its line"), ("10", "move", "10 SKUs × Reno → Columbus"), ("60", "fulfil", "10 SKUs × 2 sites × 3 channels")]),
         (NUM["edges"], "edges", [("20", "make", "2 per task"), ("40", "move", "4 per task"), ("120", "fulfil", "2 per task")])]
def counts():
    g = ""; y = 248
    for n, lab, rows in BREAK:
        g += txt(110, y, f"{n}", 34, INK, 700) + txt(110 + (46 if n < 100 else 66), y, lab, 22, INK, 600)
        for i, (k, name, how) in enumerate(rows):
            yy = y + 33 + i * 26
            g += txt(196, yy, k, 19, INK, 700, "end") + txt(212, yy, name, 19) + txt(330, yy, how, 19, GREY)
        y += 33 + 26 * (len(rows) - 1) + 46
    return g
NODES = [("Inventory", "stock of a SKU at a location", "stock files"), ("Order", "open orders of a SKU in a channel", "order files, forecast"),
         ("Capacity", "builds available per week on a line", "capacity plan")]
TASKS = [("Make", "builds a SKU on its line", "part master"), ("Move", "Reno → Columbus; 1 week in transit", "assumed route"),
         ("Fulfil", "ships a SKU from a site to a channel", "assumed routes")]
def node_defs():
    g = txt(1580, 250, "source", 16, GREY, 700)
    for (head, rows, kind, y0) in [("Resource nodes", NODES, "res", 250), ("Task nodes", TASKS, "task", 420)]:
        g += txt(960, y0, head, 18, INK, 700)
        for i, (name, d, src) in enumerate(rows):
            y = y0 + 40 + i * 34
            g += (f'<rect class="res" x="960" y="{y-17}" width="28" height="20" rx="6" style="stroke-width:2"/>' if kind == "res"
                  else f'<rect class="task" x="960" y="{y-17}" width="28" height="20" rx="3"/>')
            g += txt(1004, y, name, 19, INK, 700) + txt(1120, y, d, 19) + txt(1580, y, src, 18, GREY)
    return g
def nd(x, y, w, kind, name, task_=False, h=80):
    if task_: return f'<rect class="task" x="{x}" y="{y}" width="{w}" height="{h}" rx="8"/>' + txt(x + w / 2, y + h / 2 + 9, name, 24, "#fff", 700, "middle")
    return f'<rect class="res" x="{x}" y="{y}" width="{w}" height="{h}" rx="16"/>' + txt(x + 18, y + 30, kind, 15, GREY) + txt(x + 18, y + 60, name, 21, INK, 700)
U2, M2 = 714, 880          # centre lines: upper (Columbus) and lower (Reno) rows
s2_graph = (
    nd(110, M2 - 40, 230, "capacity", "MTB carbon line") + edge(340, M2, 386, M2, "−1", ly=M2 - 14) + nd(390, M2 - 40, 130, "", "make", True) + edge(520, M2, 566, M2, "+1", ly=M2 - 14)
    + nd(570, M2 - 40, 230, "inventory", "RW-4418, Reno") + edge(800, M2, 1206, M2, "−1", lx=840, ly=M2 - 14) + nd(1210, M2 - 40, 170, "", "fulfil ×3", True) + edge(1500, M2, 1384, M2, "−1", ly=M2 - 14)
    + edge(685, M2 - 40, 685, U2 + 44, "−1", lx=668, ly=(M2 + U2) / 2 + 8, anchor="end") + nd(620, U2 - 40, 130, "", "move", True)
    + edge(750, U2, 896, U2, "+1, 1 wk", ly=U2 - 14) + nd(900, U2 - 40, 240, "inventory", "RW-4418, Columbus") + edge(1140, U2, 1206, U2, "−1", ly=U2 - 14) + nd(1210, U2 - 40, 170, "", "fulfil ×3", True) + edge(1500, U2, 1384, U2, "−1", ly=U2 - 14)
    + f'<rect class="res" x="1500" y="{U2-40}" width="310" height="{M2-U2+80}" rx="16"/>' + txt(1520, U2 - 8, "order ×3", 15, GREY) + txt(1520, U2 + 22, "RW-4418", 21, INK, 700)
    + lines(1520, U2 + 62, ["web", "dealer", "commercial"], 19, INK, 28))
p2 = page(2, "Redwheel resource–task network", "",
          counts() + vrule(920, 224, 600) + node_defs() + rule(624) + txt(110, 664, "Subgraph of one SKU, RW-4418", 18, GREY, 700)
          + s2_graph + txt(110, 974, "Edge label: amount per run; delay 0 unless shown. Each fulfil box stands for three tasks, one per channel.", 18, GREY))

# ================================================================ 3 · network structures
def sres(x, c, kind, name, w, h=60):
    return f'<rect class="res" x="{x}" y="{c-h/2}" width="{w}" height="{h}" rx="12"/>' + txt(x + 13, c - 7, kind, 15, GREY) + txt(x + 13, c + 19, name, 19, INK, 700)
def stk(x, c, name, w, h=54, fs=20):
    return f'<rect class="task" x="{x}" y="{c-h/2}" width="{w}" height="{h}" rx="6"/>' + txt(x + w / 2, c + fs * 0.36, name, fs, "#fff", 700, "middle")
def sar(x1, y1, x2, y2, lab="", lx=None, ly=None, anchor="middle", curve=False):
    d = f"M{x1} {y1} C{x1+30} {y1} {x2-36} {y2} {x2-4} {y2}" if curve else f"M{x1} {y1} L{x2-4} {y2}"
    lx = (x1 + x2) / 2 if lx is None else lx; ly = min(y1, y2) - 10 if ly is None else ly
    return f'<path class="wire" style="stroke-width:2" marker-end="url(#a)" d="{d}"/>' + (txt(lx, ly, lab, 19, AMB, 700, anchor) if lab else "")
def sal(x1, y, x2, lab):   # right to left, arrowhead at x2
    return f'<path class="wire" style="stroke-width:2" marker-end="url(#a)" d="M{x1} {y} L{x2+4} {y}"/>' + txt((x1 + x2) / 2, y - 10, lab, 19, AMB, 700, "middle")
tagA = lambda x, y, s: txt(x, y, s, 18, AMB, 700, "middle")

# the four structures, each alone; every drawing is (width, f(left edge, centre line))
CY, CW = 390, 425
def dA(x, c): return stk(x, c, "make", 74) + sar(x+74, c, x+120, c, "+1") + sres(x+120, c, "inventory", "Reno, 25", 120) + sar(x+240, c, x+286, c, "−1") + stk(x+286, c, "move", 74)
def dB(x, c): return (sres(x, c, "capacity", "MTB carbon", 145) + "".join(sar(x+145, c+d0, x+215, c+d1, curve=True) for d0, d1 in [(-12, -56), (0, 0), (12, 56)])
                      + txt(x+166, c-40, "−1", 19, AMB, 700, "middle") + "".join(stk(x+215, c+dy, f"make {k}", 140, 44, 18) for dy, k in [(-56, "9304"), (0, "4418"), (56, "6416")]))
def dC(x, c): return (sres(x, c-34, "capacity", "line", 130, 54) + sres(x, c+34, "inventory", "frames", 130, 54) + sar(x+130, c-34, x+230, c-9, "−1", ly=c-42, curve=True)
                      + sar(x+130, c+34, x+230, c+9, "−1", ly=c+58, curve=True) + stk(x+230, c, "make", 90))
def dD(x, c): return stk(x, c, "move", 74) + sar(x+74, c, x+204, c, "+1, 1 wk") + sres(x+204, c, "inventory", "Columbus", 150)
ALONE = [("Series", "dependency", dA, 360), ("Shared input", "competition", dB, 355), ("Joint input", "matching", dC, 320), ("Delay", "lag", dD, 354)]
def alone():
    g = ""
    for i, (h, eff, dg, w) in enumerate(ALONE):
        cx = 110 + i * CW + CW / 2
        g += txt(cx, 270, f'{B_(h)} <tspan style="fill:{GREY}">·</tspan> <tspan style="fill:{AMB};font-weight:700">{eff}</tspan>', 26, INK, 400, "middle") + dg(cx - w / 2, CY)
        g += vrule(110 + i * CW, 232, 490) if i else ""
    return g

# derived: kitting and component allocation (bike = 1 frame + 2 wheels; frames bought on a 2-week lead time)
CA, CB = 700, 860
def kitting():
    return (txt(110, 592, "Kitting and component allocation", 24, INK, 700)
            + stk(110, CA, "buy", 80) + sar(190, CA, 320, CA, "+1, 2 wk") + tagA(255, CA + 38, "delay")
            + sres(320, CA, "inventory", "frames", 150) + tagA(395, CA - 44, "series")
            + sres(320, CB, "inventory", "wheels", 150) + tagA(395, CB + 58, "shared input")
            + sar(470, CA - 4, 630, CA - 12) + sar(470, CA + 14, 630, CB - 14) + sar(470, CB - 14, 630, CA + 14) + sar(470, CB + 4, 630, CB + 12)
            + "".join(txt(x, y, l, 19, AMB, 700, "middle") for x, y, l in [(584, CA - 22, "−1"), (622, CA + 52, "−2"), (624, CB - 38, "−1"), (604, CB + 44, "−2")])
            + stk(630, CA, "make A", 120) + tagA(690, CA - 44, "joint input") + stk(630, CB, "make B", 120)
            + sar(750, CA, 820, CA, "+1") + sres(820, CA, "inventory", "bike A", 130) + sar(750, CB, 820, CB, "+1") + sres(820, CB, "inventory", "bike B", 130))

# derived: order fulfilment, on the object (RW-4418 at Reno; each fulfil takes one bike and one open order)
CM = (CA + CB) / 2; FR = [CM - 90, CM, CM + 90]
def fulfilment():
    g = (txt(1010, 592, "Order fulfilment", 24, INK, 700)
         + stk(1010, CM, "make", 80) + sar(1090, CM, 1140, CM, "+1") + sres(1140, CM, "inventory", "RW-4418, Reno", 170)
         + tagA(1225, CM - 44, "series") + tagA(1225, CM + 58, "shared input") + tagA(1475, FR[0] - 41, "joint input"))
    for (y, d0, ly, ch) in zip(FR, (-12, 0, 12), (FR[0] - 16, CM - 10, FR[2] + 30), ("web", "dealer", "commercial")):
        g += (sar(1310, CM + d0, 1420, y, curve=y != CM) + txt(1392, ly, "−1", 19, AMB, 700, "middle")
              + stk(1420, y, "fulfil", 110, 50, 19) + sal(1610, y, 1530, "−1") + sres(1610, y, "order", ch, 160, 56))
    return g

p3 = page(3, "Network structures", "", alone() + rule(520) + kitting() + vrule(980, 560, 930) + fulfilment())

# ================================================================ 5 · linear program
# 1 the network for one week as a matrix (MTB carbon, week 1); 2 what is solved for; 3 the same matrix every week, levels
# carried (engine._build: 74 x 121 = 8,954 balance rows, 10 x 121 = 1,210 runs in scenario A); 4 the objective of
# scenario A (engine docstring, docs/SOLVER.md §2: weights 1, 0.1, 0.001, 1e-6; d = target units / target weeks).
SH = ["9304", "4418", "6416"]; OPEN_STOCK = {"9304": 10, "4418": 25, "6416": 15}
E_ = lambda op: f" {op} "; PL = " + "; MI = " − "; SL = " / "
it_ = lambda s: f'<tspan style="{MF}">{s}</tspan>'
SUMV = lambda sub: f'Σ{v("", sub)} '
def num(x, y, n): return f'<circle cx="{x+15}" cy="{y-8}" r="15" fill="{AMB}"/>' + txt(x + 15, y - 2, n, 17, "#fff", 700, "middle")
def head(x, y, n, h, sub=""):
    return num(x, y, n) + txt(x + 42, y, f'{B_(h)}' + (f'<tspan style="fill:{GREY}"> {sub}</tspan>' if sub else ""), 24)

# --- 1 the network for one week
def rnode(x, c, kind, name, w=196, h=44):
    return f'<rect class="res" x="{x}" y="{c-h/2}" width="{w}" height="{h}" rx="10" style="stroke-width:2"/>' + txt(x + 11, c - 5, kind, 13, GREY) + txt(x + 11, c + 14, name, 17, INK, 700)
def tbox(cx, c, name, w=104, h=36):
    return f'<rect class="task" x="{cx-w/2}" y="{c-h/2}" width="{w}" height="{h}" rx="5"/>' + txt(cx, c + 6, name, 16, "#fff", 700, "middle")
KC = [474, 588, 702]; KY = [388, 440, 492, 544]
def one_week():
    g = head(110, 252, "1", "The network as a matrix", "MTB carbon, week of 7 Sep 2026")
    g += txt(110, 286, "row: resource column: task entry: change in the level per run", 18, GREY)
    g += txt(388, 340, "opening + arrival", 15, GREY, 700, "end") + "".join(tbox(c, 334, f"make {n}") for c, n in zip(KC, SH))
    rows = [("capacity", "MTB carbon", "375", ["−1", "−1", "−1"])] + [("inventory", f"RW-{n}, Reno", str(OPEN_STOCK[n]), ["+1" if j == i else "" for j in range(3)]) for i, n in enumerate(SH)]
    g += f'<path d="M{KC[0]-52} {KY[0]-26} h-8 v{KY[3]-KY[0]+52} h8 M{KC[2]+52} {KY[0]-26} h8 v{KY[3]-KY[0]+52} h-8" fill="none" stroke="{INK}" stroke-width="2"/>'
    for c, (kind, name, st, ent) in zip(KY, rows):
        g += rnode(110, c, kind, name) + txt(388, c + 8, st, 21, INK, 400, "end")
        g += "".join(txt(x, c + 8, e, 22, AMB, 700, "middle") for x, e in zip(KC, ent)) + txt(786, c + 8, "≥ 0", 21)
    g += txt(846, KY[0] + 8, "builds ≤ 375", 18, GREY) + vrule(838, KY[1] - 18, KY[3] + 18) + txt(852, KY[2] - 18, "stock never", 18, GREY) + txt(852, KY[2] + 6, "negative", 18, GREY)
    g += meq(KC[1], 590, "A", 24, "middle", AMB)
    return g

# --- 2 what is solved for
RX = 1090
def solve_for():
    g = vrule(1040, 232, 580) + head(RX, 252, "2", "Find the build plan")
    g += txt(RX, 334, f'Runs {v("N", "i,t")}{E_("≥")}0 for each task {it_("i")} the plan decides and each week {it_("t")},', 21) + txt(RX, 366, "such that", 21)
    g += txt(RX, 420, f'–\u2002every level {v("X", "r,t")}{E_("≥")}0', 21) + txt(RX + 300, 420, "capacity never exceeded, stock never negative", 19, GREY)
    g += txt(RX, 464, "–\u2002the objective in 4 is as small as it can be", 21)
    g += txt(RX, 530, "The runs of the make tasks are the build plan: 10 SKUs × 121 weeks in scenario A.", 19, GREY)
    return g

# --- 3 the same matrix every week, levels carried
def every_week():
    g = rule(612) + head(110, 662, "3", "Every week, the same matrix")
    xs = [110, 300, 490, 760]; labs = ["0", "1", "2", "121"]; cy = 800
    for x, l in zip(xs, labs):
        g += f'<rect class="res" x="{x}" y="{cy-28}" width="96" height="56" rx="12"/>' + meq(x + 48, cy + 9, v("X", l, 17), 26, "middle")
    for (a, b), l in zip(zip(xs, xs[1:]), labs[1:]):
        if l == "121":
            g += txt((a + 96 + b) / 2, cy + 8, "⋯", 26, GREY, 400, "middle")
        else:
            g += f'<path class="wire" style="stroke-width:2" marker-end="url(#a)" d="M{a+96} {cy} L{b-4} {cy}"/>' + meq((a + 96 + b) / 2, cy - 10, "C", 20, "middle", GREY)
    for x, l in zip(xs[1:], labs[1:]):
        g += f'<path class="wire" style="stroke-width:2;stroke:{AMB}" marker-end="url(#g)" d="M{x+48} {cy-78} L{x+48} {cy-32}"/>'
        g += meq(x + 48, cy - 88, f'A{v("N", l, 15)}{PL}{v("π", l, 15)}', 20, "middle", AMB)
    g += meq(110, 900, f'{v("X", "t")}{E_("=")}C{v("X", "t−1")}{PL}A{v("N", "t")}{PL}{v("π", "t")}, {v("X", "t")}{E_("≥")}0, {it_("t")}{E_("=")}1 … 121', 28)
    g += txt(110, 942, "A: the matrix in 1 C: carry, 1 for stock and orders, 0 for capacity π: arrivals", 17, GREY)
    g += txt(110, 970, "74 resources × 121 weeks = 8,954 rows; 10 tasks × 121 weeks = 1,210 runs. An edge with delay θ lands θ weeks later.", 17, GREY)
    return g

# --- 4 the objective, set by the planner
def objective():
    g = vrule(1040, 640, 980) + head(RX, 662, "4", "Objective", "set by the planner")
    g += meq(RX, 734, f'min {SUMV("t")}{SUMV("g")}max{v("", "k∈g")} {v("u", "k,t")}{PL}0.1 {SUMV("t")}{SUMV("k")}{v("u", "k,t")}', 28)
    g += meq(RX, 786, f'{v("u", "k,t")}{E_("=")}max(0, {v("target", "k,t")}{MI}{v("net", "k,t")}){SL}{v("d", "k,t")}', 26)
    g += lines(RX, 840, [f'{it_("u")}: how far SKU {it_("k")} is below its target in week {it_("t")}, in weeks of demand',
                         f'net = stock − open orders\u2003target = the next {it_("n")} weeks of forecast\u2003{it_("d")} = target / {it_("n")}',
                         f'First term: the worst SKU on each line {it_("g")}, every week. Second: all SKUs.',
                         "Both max terms are written as linear rows, so this is an LP.",
                         "Tie-breaks: 0.001 × stock above target, 10⁻⁶ × runs."], 17, GREY, 28)
    return g

p4 = page(4, "Linear program", "", one_week() + solve_for() + every_week() + objective())

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
p5 = page(5, "Priority orders", "Rule B (scenario P1) against rule A (scenario A), MTB carbon line.",
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
p6 = page(6, "Build plans by period", "Eight-week periods. End of period = previous end + built − orders in.",
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

pages = [p1, p2, p3, p4, p5, p6]
head = f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>'
(out / "object.html").write_text(head + "".join(pages) + "</body></html>")
for i, p in enumerate(pages, 1): (out / f"p{i}.html").write_text(head + p + "</body></html>")
