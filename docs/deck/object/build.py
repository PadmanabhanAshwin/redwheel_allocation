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
    + nd(570, M2 - 40, 230, "inventory", "RW-4418, Reno") + edge(800, M2, 1206, M2, "−1", lx=840, ly=M2 - 14) + nd(1210, M2 - 40, 170, "", "fulfil ×3", True) + edge(1380, M2, 1496, M2, "−1", ly=M2 - 14)
    + edge(685, M2 - 40, 685, U2 + 44, "−1", lx=668, ly=(M2 + U2) / 2 + 8, anchor="end") + nd(620, U2 - 40, 130, "", "move", True)
    + edge(750, U2, 896, U2, "+1, 1 wk", ly=U2 - 14) + nd(900, U2 - 40, 240, "inventory", "RW-4418, Columbus") + edge(1140, U2, 1206, U2, "−1", ly=U2 - 14) + nd(1210, U2 - 40, 170, "", "fulfil ×3", True) + edge(1380, U2, 1496, U2, "−1", ly=U2 - 14)
    + f'<rect class="res" x="1500" y="{U2-40}" width="310" height="{M2-U2+80}" rx="16"/>' + txt(1520, U2 - 8, "order ×3", 15, GREY) + txt(1520, U2 + 22, "RW-4418", 21, INK, 700)
    + lines(1520, U2 + 62, ["web", "dealer", "commercial"], 19, INK, 28))
p2 = page(2, "Redwheel resource–task network", "",
          counts() + vrule(920, 224, 600) + node_defs() + rule(624) + txt(110, 664, "Subgraph of one SKU, RW-4418", 18, GREY, 700)
          + s2_graph + txt(110, 974, "Edge label: amount per run; delay 0 unless shown. Each fulfil box stands for three tasks, one per channel.", 18, GREY))

# ================================================================ 3 · network structures
w3 = NUM["wk3"]
# small graph pieces for this slide
def sres(x, c, kind, name, w, h=56):
    return f'<rect class="res" x="{x}" y="{c-h/2}" width="{w}" height="{h}" rx="12"/>' + txt(x + 12, c - 6, kind, 14, GREY) + txt(x + 12, c + 18, name, 18, INK, 700)
def stk(x, c, name, w, h=50, fs=19):
    return f'<rect class="task" x="{x}" y="{c-h/2}" width="{w}" height="{h}" rx="6"/>' + txt(x + w / 2, c + fs * 0.36, name, fs, "#fff", 700, "middle")
def sar(x1, y1, x2, y2, lab="", lx=None, ly=None, anchor="middle", curve=False):
    d = f"M{x1} {y1} C{x1+30} {y1} {x2-36} {y2} {x2-4} {y2}" if curve else f"M{x1} {y1} L{x2-4} {y2}"
    lx = (x1 + x2) / 2 if lx is None else lx; ly = min(y1, y2) - 10 if ly is None else ly
    return f'<path class="wire" style="stroke-width:2" marker-end="url(#a)" d="{d}"/>' + (txt(lx, ly, lab, 18, AMB, 700, anchor) if lab else "")
O = lambda op: f" {op} "; P_ = " + "; SUM_LE = lambda sub: f'Σ{v("", sub)}'

# four structures, each alone: (header, effect, term, diagram(x0, c), relation, number)
CY = 386
def dA(x, c): return stk(x, c, "make", 80) + sar(x+80, c, x+130, c, "+1") + sres(x+130, c, "inventory", "Reno, 25", 140) + sar(x+270, c, x+320, c, "−1") + stk(x+320, c, "move", 80)
def dB(x, c): return (sres(x, c, "capacity", "MTB carbon", 150) + "".join(sar(x+150, c+d0, x+230, c+d1, curve=True) for d0, d1 in [(-12, -52), (0, 0), (12, 52)])
                      + txt(x+188, c-40, "−1", 18, AMB, 700, "middle") + "".join(stk(x+230, c+dy, f"make {k}", 150, 40, 17) for dy, k in [(-52, "9304"), (0, "4418"), (52, "6416")]))
def dC(x, c): return (sres(x, c-31, "capacity", "line", 130, 50) + sres(x, c+31, "inventory", "frames", 130, 50) + sar(x+130, c-31, x+230, c-8, "−1", ly=c-38, curve=True)
                      + sar(x+130, c+31, x+230, c+8, "−1", ly=c+52, curve=True) + stk(x+230, c, "make", 90))
def dD(x, c): return stk(x, c, "move", 80) + sar(x+80, c, x+210, c, "+1, 1 wk") + sres(x+210, c, "inventory", "Columbus", 150)
ALONE = [("Series", "dependency", "material availability", dA,
          f'{SUM_LE("τ≤t")} {v("N", "move,τ")}{O("≤")}{v("X", "Reno,0")}{P_}{SUM_LE("τ≤t")} {v("N", "make,τ")}', "RW-4418: 25 at Reno at opening"),
         ("Shared input", "competition", "capacity allocation", dB,
          f'{v("N", "9304,t")}{P_}{v("N", "4418,t")}{P_}{v("N", "6416,t")}{O("≤")}375',
          f'Week of 21 Sep 2026: {w3["RW-9304"][0]} + {w3["RW-4418"][0]} + {w3["RW-6416"][0]} = 375'),
         ("Joint input", "matching", "assembly, bill of materials", dC,
          f'{v("N", "make,t")}{O("≤")}min( {v("line", "t")}, {v("frames", "t")} )', "Worked below, with a supplier"),
         ("Delay", "lag", "lead time, pipeline stock", dD,
          f'{v("X", "transit,t")}{O("=")}{v("N", "move,t")}',
          f'Scenario B: {SC["B"]["scorecard"]["Average bikes in transit"]:.0f} bikes in transit on average')]
def alone():
    g = txt(110, 240, "Each structure alone", 17, GREY, 700)
    for i, (h, eff, term, dg, rel, num) in enumerate(ALONE):
        x = 110 + i * 435
        g += (txt(x, 290, f'{B_(h)} <tspan style="fill:{GREY}">·</tspan> <tspan style="fill:{AMB};font-weight:700">{eff}</tspan>', 24)
              + txt(x, 316, term, 16, GREY) + dg(x, CY) + meq(x, 486, rel, 24) + txt(x, 518, num, 17))
    return g

# combined: the tested small example (tests/test_generality.py, bike_from_a_frame); Redwheel's data has no components
FRAME = {"week": [1, 2, 3, 4, 5, 6], "frames bought": [9, 4, 4, 4, 0, 0], "frames available": [3, 0, 9, 4, 4, 4],
         "line capacity": [10] * 6, "ordered": [4] * 6, "built": [3, 0, 9, 4, 4, 4], "owed after the week": [1, 5, 0, 0, 0, 0],
         "limit on builds": ["frames", "frames", "orders", "orders", "orders", "orders"]}
C2 = 778
def combined_graph():
    return (stk(110, C2, "buy", 75) + sar(185, C2, 290, C2, "+1, 2 wk") + sres(290, C2, "inventory", "frames, 3", 140)
            + sar(430, C2, 480, C2, "−1") + stk(480, C2, "make", 85)
            + sres(452, C2 - 104, "capacity", "line, 10 / wk", 142) + sar(522, C2 - 76, 522, C2 - 25) + txt(508, C2 - 44, "−1", 18, AMB, 700, "end")
            + sar(565, C2, 615, C2, "+1") + sres(615, C2, "inventory", "bikes", 115) + sar(730, C2, 780, C2, "−1") + stk(780, C2, "fulfil", 85)
            + sar(865, C2, 915, C2, "−1") + sres(915, C2, "order", "4 / wk", 115)
            + "".join(txt(x, C2 + 58, s, 17, AMB, 700, "middle") for x, s in [(237, "delay"), (522, "joint input"), (672, "series")]))
def frame_table():
    x0, xs, y0, dy = 1120, [1470 + 62 * i for i in range(6)], 640, 31
    g = f'<rect x="{xs[1]-27}" y="{y0-22}" width="54" height="{dy*len(FRAME)+4}" rx="6" style="fill:{tint(AMB, 0.13)}"/>'
    for r, (k, vals) in enumerate(FRAME.items()):
        y = y0 + r * dy; head = r == 0; bold = k == "built"; lim = k == "limit on builds"
        col = AMB if lim else (GREY if head else INK); w = 700 if (bold or lim) else 400
        g += txt(x0, y, k, 16 if head else 18, GREY if head else INK, 700 if bold else 400)
        g += "".join(txt(x, y, f"{val}", 15 if lim else (16 if head else 18), col, w, "middle") for x, val in zip(xs, vals))
        if head: g += f'<line x1="{x0}" y1="{y+11}" x2="1810" y2="{y+11}" style="stroke:{RULE_C};stroke-width:1.5"/>'
    return g
p3 = page(3, "Network structures", "",
          alone() + rule(552)
          + txt(110, 600, "Combined: one bike built from a bought frame", 17, GREY, 700)
          + txt(1810, 600, "small example, tested; Redwheel’s data has no components", 16, GREY, 400, "end")
          + combined_graph() + frame_table()
          + lines(110, 892, ["Week 2: the line has 10 free and builds 0; frames bought in week 1 arrive in week 3.",
                             "The plan buys 9 frames in week 1, for the 5 owed and week 3’s 4 ordered.",
                             "With 9 frames at the start instead of 3, it builds 4 every week."], 18, INK, 29)
          + rule(980) + txt(110, 1022, "Alone, each structure gives one relation in closed form. Combined, the limit changes by week; the LP solves the balance for all resources and weeks at once.", 21))

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
p4 = page(4, "Linear program", "MTB carbon line and its three SKUs, week of 7 Sep 2026.",
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
