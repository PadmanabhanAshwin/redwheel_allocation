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
# One SKU (RW-4418) walked from network to LP. Edges as rtn.generate_tasks writes them (make: line -1, Reno +1, delay 0;
# move: Reno -1, transit +1 at delay 0, transit -1, Columbus +1 at delay 1). Scenario edits: deck_numbers.json (E1, E3, E4, B),
# tests/test_generality.py (frame). Objective: docs/SOLVER.md §2.
E_ = lambda op: f" {op} "; PL = " + "
it_ = lambda s: f'<tspan style="{MF}">{s}</tspan>'
def num(x, y, n): return f'<circle cx="{x+15}" cy="{y-8}" r="15" fill="{AMB}"/>' + txt(x + 15, y - 2, n, 17, "#fff", 700, "middle")
def head(x, y, n, h, sub=""): return num(x, y, n) + txt(x + 42, y, B_(h) + (f'<tspan style="fill:{GREY}"> {sub}</tspan>' if sub else ""), 23)
A0c, A1c = AMB, "#2563eb"
RES4 = ["line", "Reno", "in transit", "Columbus"]
A0 = [["−1", ""], ["+1", "−1"], ["", "+1"], ["", ""]]; A1 = [["", ""], ["", ""], ["", "−1"], ["", "+1"]]
def network():
    c = 420
    g = head(110, 252, "1", "Network", "RW-4418")
    g += sres(110, c, "capacity", "line", 100) + sar(210, c, 250, c, "−1") + stk(250, c, "make", 78) + sar(328, c, 368, c, "+1")
    g += sres(368, c, "inventory", "Reno", 104) + sar(472, c, 512, c, "−1") + stk(512, c, "move", 78)
    g += f'<path class="wire" style="stroke-width:2;stroke:{A1c}" d="M590 {c} L686 {c}"/><path d="M682 {c-6} l12 6 l-12 6 z" fill="{A1c}"/>' + txt(640, c - 10, "+1, 1 wk", 18, A1c, 700, "middle")
    g += sres(696, c, "inventory", "Columbus", 124)
    return g
def mat(x, y, name, col, M):
    g = meq(x + 190, y - 44, name, 26, "middle", col) + "".join(txt(x + cx, y - 8, t_, 15, GREY, 700, "middle") for cx, t_ in [(150, "make"), (230, "move")])
    g += f'<path d="M{x+112} {y+4} h-8 v{34*4+6} h8 M{x+268} {y+4} h8 v{34*4+6} h-8" fill="none" stroke="{INK}" stroke-width="2"/>'
    for i, r in enumerate(RES4):
        yy = y + 32 + 34 * i
        g += txt(x, yy, r, 17) + "".join(txt(x + cx, yy, M[i][j], 20, col, 700, "middle") for j, cx in enumerate([150, 230]))
    return g
def matrices():
    g = head(900, 252, "2", "Edges by delay")
    return g + mat(900, 352, f'A{v("", "0")}', A0c, A0) + mat(1210, 352, f'A{v("", "1")}', A1c, A1) + txt(900, 520, f'effect in week {it_("t")}', 18, A0c, 700) + txt(1210, 520, f'effect in week {it_("t")} + 1', 18, A1c, 700)
def staircase():
    g = head(1560, 252, "3", "Every week")
    x0, y0, s = 1620, 318, 58
    g += "".join(meq(x0 + s * j + s / 2, y0 - 12, v("N", str(j + 1), 14), 20, "middle") for j in range(3))
    for i in range(3):
        g += txt(x0 - 14, y0 + s * i + s / 2 + 6, f"week {i+1}", 16, GREY, 400, "end")
        for j in range(3):
            col = A0c if i == j else A1c if i == j + 1 else None
            g += f'<rect x="{x0+s*j}" y="{y0+s*i}" width="{s}" height="{s}" fill="{tint(col, .18) if col else "#fff"}" stroke="{RULE_C}" stroke-width="1.5"/>'
            if col: g += meq(x0 + s * j + s / 2, y0 + s * i + s / 2 + 8, f'A{v("", "0" if i == j else "1", 14)}', 22, "middle", col)
    return g + txt(1560, 520, "Constraint matrix of the LP.", 18, GREY)
SUMV = lambda sub: f'Σ{v("", sub)} '
NB = lambda sub: f'<tspan style="{MF};text-decoration:overline">N</tspan><tspan dy="7" dx="1" style="{MF};font-size:19px">{sub}</tspan><tspan dy="-7" style="font-size:10px"> </tspan>'
DYN = f'{v("X", "t")}{E_("=")}C{v("X", "t−1")}{PL}<tspan fill="{A0c}">A{v("", "0")}{v("N", "t")}</tspan>{PL}<tspan fill="{A1c}">A{v("", "1")}{v("N", "t−1")}</tspan>{PL}{v("π", "t")}'
A_ = lambda n: f'A{v("", n, 13)}'
LPROWS = [("minimise", f'{SUMV("t")}{SUMV("g")}max{v("", "k∈g")} {v("u", "k,t")}{PL}0.1 {SUMV("t")}{SUMV("k")}{v("u", "k,t")}',
           [f'Summed over weeks {it_("t")} and production lines {it_("g")}: the largest shortfall {it_("u")} among the',
            f'SKUs {it_("k")} built on {it_("g")}. Second term: 0.1 × the sum of all shortfalls.']),
          ("subject to", DYN,
           [f'State equation. {it_("X")}: resource levels. {it_("N")}: task runs. C: diagonal carry matrix.',
            f'{A_("0")}, {A_("1")}: edge amounts by delay. π: exogenous arrivals.']),
          ("", f'{v("X", "t")}{E_("≥")}0, 0{E_("≤")}{v("N", "t")}{E_("≤")}{NB("t")}',
           [f'{it_("X")} ≥ 0 bounds capacity use (C = 0) and keeps stock non-negative (C = 1).',
            f'<tspan style="{MF};text-decoration:overline">N</tspan>: run limit per task and week.']),
          ("where", f'{v("u", "k,t")}{E_("=")}max(0, {v("target", "k,t")} − {v("net", "k,t")}){E_("/")}{v("d", "k,t")}',
           [f'Shortfall of SKU {it_("k")} below target in week {it_("t")}, in weeks of demand. net: stock minus',
            f'open orders, linear in {it_("X")}. {it_("d")}: mean weekly forecast over the target window.'])]
def dynamics():
    g = rule(556) + txt(110, 604, B_("Formulation"), 23)
    for i, (kw, m, d) in enumerate(LPROWS):
        y = 660 + 92 * i
        g += meq(110, y, kw, 23, "start", GREY) + meq(240, y, m, 27) + lines(240, y + 30, d, 16, GREY, 22)
    return g
PBAR = f'<tspan style="{MF};text-decoration:overline">N</tspan>'
EDITS = [("R", "Build time 1 week, every line", f'{A_("0")}, {A_("1")}', f'output entry of make moved from {A_("0")} to {A_("1")}', "deck"),
         ("R+", "Build time 2 weeks on carbon lines, 1 on base lines", f'{A_("1")}, {A_("2")}', f'output entry of make in {A_("2")} for carbon, {A_("1")} for base', "deck: the plan"),
         ("R+C26", "Plant closed, weeks of 21 and 28 Dec 2026", "π", "capacity arrival set to 0, every line, 2 weeks", "live"),
         ("R+E4", "Commercial order, 300 RW-4418, week of 9 Nov 2026", "π", "order arrival +300 in 1 week", "live"),
         ("R+P1", "Priority order on the MTB carbon line", "objective", "one step replaced by six ordered steps", "live"),
         ("R+E5", "RW-9304 built in lots of 50", "lot", "applied when rounding the LP solution; exact form is a MIP", "live; outside the LP"),
         ("", "Purchased component, 2-week lead time", f'{A_("0")}, {A_("2")}', "one row (frames) and one column (buy) added", "test only")]
SXX = 1040
def edits():
    g = vrule(990, 580, 1000) + txt(SXX, 604, B_("Generalization") + f'<tspan style="fill:{GREY}"> scenarios v parameters updated</tspan>', 23)
    g += txt(1810, 604, "status", 15, GREY, 700, "end")
    for i, (c, a, p, b, st) in enumerate(EDITS):
        y = 648 + 52 * i
        shown = st.startswith("deck")
        g += txt(SXX, y, c, 17, GREY, 700) + txt(SXX + 76, y, a, 18, INK, 700 if shown else 400) + txt(1810, y, st, 15, INK if shown else GREY, 700 if shown else 400, "end")
        g += (meq(SXX + 76, y + 23, p, 18) if p not in ("objective", "lot") else txt(SXX + 76, y + 23, p, 16)) + txt(SXX + 166, y + 23, b, 16, GREY)
    return g
p4 = page(4, "Linear program", "", network() + vrule(860, 232, 530) + matrices() + vrule(1520, 232, 530) + staircase() + dynamics() + edits())

# ================================================================ 6 · scenarios A, R, R+
# Every number from docs/deck/deck_numbers.json, keys A, R, R+ (the solver session's final set). Same layout on each
# scenario slide: what changed; four headline numbers against the parent; open orders (every order cleared) and MTB
# carbon weeks of supply (targets held from), parent dashed; each line's dates; one sentence.
DN = json.load(open(next(p for p in [HERE.parent / "deck_numbers.json", HERE / "deck_numbers.json"] if p.exists())))
DW = {int(k): datetime.date.fromisoformat(v) for k, v in DN["_meta"]["weeks"].items()}
D_ = lambda s: datetime.date.fromisoformat(str(s)[:10])
fd = lambda d: f"{d.day} {d:%b %Y}"
LNAME = {"mtb-carbon": "MTB carbon", "road-carbon": "Road carbon", "mtb-base": "MTB base", "road-base": "Road base"}
LORDER = ["mtb-carbon", "road-carbon", "mtb-base", "road-base"]
def cleared_week(series):                      # first week from which nothing is owed (series[0] is week 1)
    last = max([i for i, x in enumerate(series) if x > 0.5], default=-1)
    return last + 2
def line_cleared(sc, ln): return DW[cleared_week(DN[sc]["owed_by_line_by_week"][ln])]
def total_owed(sc): return [sum(DN[sc]["owed_by_line_by_week"][ln][i] for ln in LORDER) for i in range(121)]
for sc in ("A", "R", "R+"):                    # the charts' crossing points are the scorecard's dates
    assert DW[cleared_week(total_owed(sc))] == D_(DN[sc]["scorecard"]["Open orders cleared from"]), sc
def wdiff(a, b):
    w = (D_(a) - D_(b)).days // 7
    return "same date" if w == 0 else f"{w:+d} week{'s' if abs(w) != 1 else ''}"
def bw(sc, ln):
    w = DN[sc]["build_weeks"][ln]
    return "same week" if w == 0 else f"{w} week{'s' if w > 1 else ''}"

def poly(pts, col, wdt, dash=False):
    d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return f'<polyline points="{d}" fill="none" stroke="{col}" stroke-width="{wdt}" stroke-linejoin="round"{" stroke-dasharray=" + chr(34) + "7 5" + chr(34) if dash else ""}/>'
WK_OF_DN = lambda s: {v: k for k, v in DW.items()}[D_(s)]
def full_run(sc, ln):                          # weeks 1..n at capacity
    b, c = DN[sc]["builds_by_line_by_week"][ln], DN[sc]["capacity_by_line_by_week"][ln]
    n = 0
    while n < 121 and b[n] >= c[n] - 0.5: n += 1
    return n
for ln in LORDER:                              # the slide's claim: full from week 1 to just before the target is held
    assert full_run("R+", ln) == WK_OF_DN(DN["R+"]["held_by_line"][ln]) - DN["R+"]["build_weeks"][ln] - 1, ln

# ---- per-bike detail (dump_scenarios.py; checked there against deck_numbers.json)
SD = json.load(open(HERE / "scenario_detail.json"))
SIZE_C = {"S": "#86b6ef", "M": "#2a78d6", "L": "#104281"}; FORE_C, CAP_C, OPEN_C = "#eb6834", "#0b0b0b", "#e34948"
SC_C = {"A": "#f3c89a", "R": "#e08a3c", "R+": "#9a3f07"}
MONTHS = []
for t in range(1, 122):
    m = (DW[t].year, DW[t].month)
    if not MONTHS or MONTHS[-1][0] != m: MONTHS.append((m, []))
    MONTHS[-1][1].append(t)
MLAB = lambda m: datetime.date(m[0], m[1], 1).strftime("%b")
def monthly(series, weeks, how="sum"):
    return sum(series[t - 1] for t in weeks) if how == "sum" else series[weeks[-1] - 1]
import textwrap
def sec_head(x, y, s_): return f'<text x="{x}" y="{y}" style="font-size:15px;font-weight:700;fill:{AMB};letter-spacing:1.5px">{s_.upper()}</text>'
def bullets(x, y, items, width=50, size=18, dy=27, gap=7):
    g = ""
    for it in items:
        rows = textwrap.wrap(it, width) if "<" not in it else [it]
        g += f'<circle cx="{x + 4}" cy="{y - 6}" r="3.2" fill="{INK}"/>'
        for r_ in rows:
            g += txt(x + 20, y, r_, size); y += dy
        y += gap
    return g, y
def text_col(x, y, sections, width=50, size=18, dy=27, gap=7, after=20):
    g = ""
    for head_, items in sections:
        g += sec_head(x, y, head_); y += 32
        b, y = bullets(x, y, items, width, size, dy, gap); g += b
        y += after
    return g
def callouts(items, y=226):
    g = ""; n = len(items); w = 1700 / n
    for i, (big, cap) in enumerate(items):
        x = 110 + i * w
        g += f'<rect x="{x}" y="{y}" width="{w - 24}" height="104" rx="12" fill="{tint(AMB, .07)}"/>'
        g += txt(x + 22, y + 56, big, 38, INK, 700) + txt(x + 22, y + 86, cap, 16, GREY)
    return g

# ---- 5 · scenarios A, R and R+
def scenarios_page():
    S = {k: DN[k]["scorecard"] for k in ("A", "R", "R+")}
    assert not DN["R"]["against_A"]["sku_totals_diff"] and not DN["R+"]["against_A"]["sku_totals_diff"]
    assert all(DN["R+"]["held_by_line"][ln] == DN["R"]["held_by_line"][ln] for ln in ("mtb-base", "road-base"))
    g = callouts([("94,429", "bikes in each scenario; identical totals per bike"),
                  ("+2 weeks", "per scenario on every date: orders cleared 14 Dec, 28 Dec, 11 Jan"),
                  ("Carbon lines only", "shift from R to R+; base lines unchanged")])
    g += text_col(110, 400, [
        ("Scenario context", ["One network, one solver, one objective; three settings of build time.",
                              f'{B_("A")}: none. A bike ships in the week it is built.',
                              f'{B_("R")}: one week, every line.',
                              f'{B_("R+")}: two weeks on carbon lines, one on base lines.']),
        ("Assumptions", ["Build times are assumed; the data holds none.",
                         "Stock at Reno and the PDC serves every order.",
                         "Forecast demand is taken as exact."]),
        ("Result notes", ["Build time delays delivery; it does not change the quantity built.",
                          "R+ is the plan: every target held from 4 Oct 2027."])])
    g += vrule(680, 376, 990)
    # phase strip per line: customers waiting -> stock below target -> at target; one bar per scenario
    x0, x1, W1 = 900, 1790, 70
    X = lambda w: x0 + (w - 1) * (x1 - x0) / (W1 - 1)
    PH = {"wait": tint(RED, .5), "below": "#d1d5db", "at": tint(GREEN, .5)}
    g += txt(730, 400, B_("Each line, by scenario: customers waiting, then stock below target, then at target"), 19)
    g += "".join(f'<rect x="{1150 + 210 * i}" y="422" width="16" height="16" fill="{c}"/>' + txt(1172 + 210 * i, 436, lab, 15, INK)
                 for i, (c, lab) in enumerate([(PH["wait"], "customers waiting"), (PH["below"], "stock below target"), (PH["at"], "at target")]))
    yy = 470; bottom = yy + 4 * 88 - 24
    g += "".join(f'<line x1="{X(w)}" y1="462" x2="{X(w)}" y2="{bottom}" stroke="{RULE_C}" stroke-width="1"/>' for w in (18, 35, 53, 70))
    for ln in LORDER:
        g += txt(730, yy + 34, LNAME[ln], 18, INK, 700)
        for i, k in enumerate(("A", "R", "R+")):
            y = yy + i * 22; wc = cleared_week(DN[k]["owed_by_line_by_week"][ln]); wt = WK_OF_DN(DN[k]["held_by_line"][ln])
            g += txt(x0 - 10, y + 14, k, 13, INK, 700 if k == "R+" else 400, "end")
            if wc > 1: g += f'<rect x="{x0}" y="{y}" width="{X(wc) - x0}" height="18" fill="{PH["wait"]}"/>'
            g += f'<rect x="{X(max(wc, 1))}" y="{y}" width="{X(wt) - X(max(wc, 1))}" height="18" fill="{PH["below"]}"/>'
            g += f'<rect x="{X(wt)}" y="{y}" width="{x1 - X(wt)}" height="18" fill="{PH["at"]}"/>'
            g += txt(X(wt) + 6, y + 14, fd(DW[wt]), 13, INK, 700 if k == "R+" else 400)
        yy += 88
    g += "".join(txt(X(w), bottom + 22, lab, 14, GREY, 400, "middle") for w, lab in [(1, "Sep 2026"), (18, "Jan 2027"), (35, "May 2027"), (53, "Sep 2027"), (70, "Jan 2028")])
    sc_ = ["A", "R", "R+"]
    rows = [("Every order cleared", [fd(D_(S[k]["Open orders cleared from"])) for k in sc_]),
            ("All targets held from", [fd(D_(S[k]["All targets held from"])) for k in sc_]),
            ("On-time fill", [f'{100*S[k]["On-time fill rate"]:.1f}%' for k in sc_])]
    xs = [1380, 1580, 1790]; ty = 866
    g += rule(856, 730, 1810) + f'<rect x="1610" y="{ty}" width="196" height="{26 * len(rows) + 40}" rx="8" fill="{tint(SC_C["R+"], .10)}"/>'
    g += "".join(txt(x, ty + 20, h, 14, GREY, 700, "end") for x, h in zip(xs, sc_))
    for i, (lab, vals) in enumerate(rows):
        y = ty + 48 + 26 * i
        g += txt(730, y, lab, 16, INK, 700) + "".join(txt(x, y, v_, 16, INK, 700 if j == 2 else 400, "end") for j, (x, v_) in enumerate(zip(xs, vals)))
    return g
p5 = page(5, "Scenarios A, R and R+", "", scenarios_page())

# ---- 6 · scenario R+
NM = 16                                       # Sep 2026 - Dec 2027
def line_panel(x0, y0, w, h, ln, sc="R+"):
    sk = sorted([s for s, d in SD[sc]["sku"].items() if d["line"] == ln], key=lambda s: "SML".index(SD[sc]["sku"][s]["size"]))
    ms = MONTHS[:NM]
    built = {s: [monthly(SD[sc]["sku"][s]["built"], wk) for _, wk in ms] for s in sk}
    fore = [sum(monthly(SD[sc]["sku"][s]["forecast"], wk) for s in sk) for _, wk in ms]
    cap = [monthly(DN[sc]["capacity_by_line_by_week"][ln], wk) for _, wk in ms]
    opn = [sum(monthly(SD[sc]["sku"][s]["open_orders"], wk, "last") for s in sk) for _, wk in ms]
    top = max(max(cap), max(opn), max(fore)) * 1.08
    gw = w / NM; Y = lambda q: y0 + h - q * h / top
    held = D_(DN[sc]["held_by_line"][ln])
    g = txt(x0, y0 - 16, f'{B_(LNAME[ln])}<tspan style="fill:{GREY};font-size:15px"> build time {bw(sc, ln)} · target held {fd(held)}</tspan>', 19)
    g += "".join(f'<line x1="{x0}" y1="{Y(q)}" x2="{x0+w}" y2="{Y(q)}" stroke="{RULE_C}" stroke-width="1"/>' + txt(x0 - 8, Y(q) + 5, f"{q:,}", 13, GREY, 400, "end") for q in [0, int(round(top / 2.16, -2)), int(round(top / 1.08, -2))])
    for j in range(NM):
        cx, base = x0 + gw * (j + .5), 0
        for s in sk:
            q = built[s][j]
            g += f'<rect x="{cx - gw * .36}" y="{Y(base + q)}" width="{gw * .72}" height="{Y(base) - Y(base + q)}" fill="{SIZE_C[SD[sc]["sku"][s]["size"]]}" stroke="#fff" stroke-width="0.8"/>'
            base += q
    step = []
    for j, q in enumerate(cap): step += [(x0 + gw * j, Y(q)), (x0 + gw * (j + 1), Y(q))]
    g += poly(step, CAP_C, 1.6, True) + poly([(x0 + gw * (j + .5), Y(q)) for j, q in enumerate(fore)], FORE_C, 2.2)
    g += "".join(f'<path d="M{x0 + gw*(j+.5)} {Y(q)-7} l7 7 l-7 7 l-7 -7 z" fill="{OPEN_C}" stroke="#fff" stroke-width="1.2"/>' for j, q in enumerate(opn) if q > 0.5)
    jh = next(j for j, (m, wk) in enumerate(ms) if DW[wk[0]] <= held <= DW[wk[-1]] + datetime.timedelta(days=6))
    xh = x0 + gw * j if False else x0 + gw * (jh + .5)
    g += f'<line x1="{xh}" y1="{y0}" x2="{xh}" y2="{y0 + h}" stroke="{INK}" stroke-width="1.4" stroke-dasharray="3 4"/>'
    g += "".join(txt(x0 + gw * (j + .5), y0 + h + 20, MLAB(m)[0], 13, GREY, 400, "middle") for j, (m, _) in enumerate(ms))
    g += txt(x0, y0 + h + 40, "2026", 13, GREY, 700) + txt(x0 + gw * 4, y0 + h + 40, "2027", 13, GREY, 700)
    return g
def rplus_page():
    s = DN["R+"]["scorecard"]
    assert all(DN[k]["deliveries"]["largest_gap_bikes"] == 0 for k in ("A", "R", "R+")) and DN["_meta"]["all_checks_pass"]
    assert len(DN["_meta"]["consistency"]) == 14 and all(r["holds"] for r in DN["_meta"]["consistency"])
    g = callouts([(f'{s["Bikes built"]:,}', "bikes built, ten bikes on four lines"),
                  (fd(D_(s["Open orders cleared from"])), "every order cleared"),
                  (fd(D_(s["All targets held from"])), "all targets held from"),
                  (f'{100 * s["On-time fill rate"]:.1f}%', "on-time fill")])
    g += text_col(110, 396, [
        ("Scenario context", ["The build plan: weekly builds per bike at Reno, 7 Sep 2026 to 25 Dec 2028."]),
        ("Assumptions", ["Two weeks to build on carbon lines, one on base lines.",
                         "Targets: 15 weeks of supply on MTB carbon, 12 on MTB base, 8 on road (10 from Jan 2028).",
                         "Every change is known from week 1."]),
        ("Result notes", ["Each line builds at capacity until just before it holds its target."]),
        ("Why believe it", ["Optimal, proved from its own duals; a second algorithm finds the same plan.",
                            "The only optimal plan, to within 2 bikes.",
                            "No plan delivers more by any date, on any line.",
                            "Consistent: 14 rules between the scenarios hold."])], width=56, size=17, dy=24, gap=5, after=14)
    g += vrule(680, 376, 990)
    lg = [("S", "size S"), ("M", "size M"), ("L", "size L")]
    g += "".join(f'<rect x="{730 + 100 * i}" y="390" width="16" height="16" fill="{SIZE_C[k]}"/>' + txt(752 + 100 * i, 404, lab, 15, INK) for i, (k, lab) in enumerate(lg))
    g += poly([(1040, 398), (1074, 398)], FORE_C, 2.2) + txt(1082, 404, "forecast", 15, INK)
    g += poly([(1170, 398), (1204, 398)], CAP_C, 1.6, True) + txt(1212, 404, "capacity", 15, INK)
    g += f'<path d="M1306 391 l7 7 l-7 7 l-7 -7 z" fill="{OPEN_C}"/>' + txt(1320, 404, "open orders, month end", 15, INK)
    g += f'<line x1="1510" y1="390" x2="1510" y2="408" stroke="{INK}" stroke-width="1.4" stroke-dasharray="3 4"/>' + txt(1520, 404, "target held", 15, INK)
    g += txt(1810, 404, "bikes per month", 14, GREY, 400, "end")
    for i, ln in enumerate(LORDER):
        x0, y0 = 790 + (i % 2) * 540, 476 + (i // 2) * 270
        g += line_panel(x0, y0, 480, 160, ln)
    return g + rule(986) + txt(110, 1026, "Next: we change the world live.", 22)
p6 = page(6, "Scenario R+", "", rplus_page())

pages = [p1, p2, p3, p4, p5, p6]
head = f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>'
(out / "object.html").write_text(head + "".join(pages) + "</body></html>")
for i, p in enumerate(pages, 1): (out / f"p{i}.html").write_text(head + p + "</body></html>")
