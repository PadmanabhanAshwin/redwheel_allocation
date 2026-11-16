"""The object deck: a cover and thirteen 1920x1080 slides as SVG in one HTML file.

Usage: python3 build.py OUTDIR  ->  OUTDIR/object.html and OUTDIR/p1..p14.html (p1 is the cover); print object.html to PDF with Chrome.
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
            f'{s}{rule(200)}{body}<text x="1810" y="1048" class="pg" text-anchor="end">{n} / §N§</text></svg>')
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
A_SC = SC["R+"]["scorecard"]; A_HELD = datetime.date.fromisoformat(A_SC["All targets held from"])
N_SCEN = len([k for k in SC if not k.startswith("_")])
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
             "~Examples", "~\tbuild time 2 weeks: delay θ", "~\tclosed for Christmas: capacity = 0", "~\tRW-9304 first: priority order"],
            [f"{N_SCEN} scenarios", "A, R, R+: build time none, 1 wk,", "\tby model; R+ is the plan", "On R+: Christmas closure, fleet", "\torder, lots of 50, priority order"])
    + flow_arrow(1210, 1250)
    + stage(1250, 290, "Solver", "method by problem structure",
            ["LP: build and transfer plans", "MIP: lot sizes, set-ups,", "\tminimum runs", "Heuristics: dispatch and", "\tallocation rules", "Sampling: safety stock", "\tunder uncertainty"],
            ["LP in HiGHS", "Variables: runs N ≥ 0", "Rows: one balance per", "\tresource and period", "Objective: priority order", "A: 13,068 variables, &lt; 0.2 s", "Lots: by rounding the LP"])
    + flow_arrow(1540, 1580)
    + stage(1580, 230, "Plan", "per scenario", ["Runs N per task and", "\tperiod: the build plan", "Levels X: stock, backlog", "Date each target is met", "Feasibility checks"],
            [f'R+: {A_SC["Bikes built"]:,} bikes', "all targets held from", f"{A_HELD.day} {A_HELD:%b %Y}"])
    # planning question
    + box(110, 822, 730, 176) + txt(130, 856, "Planning question", 21, INK, 700)
    + meq(130, 896, "q = (𝒪, σ, Ω),   answer = Ω(𝒪 | σ)", 30)
    + txt(130, 926, "𝒪 object · σ scope: resources, tasks, horizon · Ω operator: project, decide, intervene, diagnose, evaluate", 15, GREY)
    + txt(130, 958, f'{B_("Example")}  R+C26: “every line closed for the weeks of 21 and 28 Dec 2026”', 16)
    + txt(130, 982, "𝒪: the network · σ: all 4 lines, 121 weeks · Ω: intervene, decide, evaluate against R+", 16)
    # LLM interface
    + box(880, 822, 930, 176, stroke=AMB) + txt(900, 856, "LLM interface", 21, AMB, 700)
    + txt(900, 892, f'{B_("Input")}  natural-language request → typed edit forms → validated in code → proposal for approval', 17)
    + txt(900, 922, f'{B_("Output")}  answers stated from computed results only', 17)
    + txt(900, 958, "No free-form model formulation: the LLM fills fixed forms; it does not write constraints or solve.", 16, GREY)
    + txt(900, 982, "No access to orders, stock or forecasts.", 16, GREY)
    + f'<path d="M1045 822 L1045 803" stroke="{AMB}" stroke-width="2.5" stroke-dasharray="5 4" marker-end="url(#g)"/>'
    + f'<path d="M1695 803 L1695 820" stroke="{AMB}" stroke-width="2.5" stroke-dasharray="5 4" marker-end="url(#g)"/>'
)
p1 = page(1, "Planning system", "Five parts, one object. Every scenario is an edit to the object; the solver and the plan follow from it.", s1)

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
p2 = page(2, "Redwheel resource–task network", "Nine files become 74 resources, 80 tasks and 180 edges; one SKU drawn in full.",
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

p3 = page(3, "Network structures", "Four ways tasks interact through shared resources, and two combinations found in the network.", alone() + rule(520) + kitting() + vrule(980, 560, 930) + fulfilment())

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
        g += meq(110, y, kw, 23, "start", GREY) + meq(240, y, m, 27) + lines(900, y - 8, d, 17, GREY, 24)
    return g
PBAR = f'<tspan style="{MF};text-decoration:overline">N</tspan>'
EDITS = [("R", "Build time 1 week, every line", f'{A_("0")}, {A_("1")}', f'output entry of make moved from {A_("0")} to {A_("1")}', "deck"),
         ("R+", "Build time 2 weeks on carbon lines, 1 on base lines", f'{A_("1")}, {A_("2")}', f'output entry of make in {A_("2")} for carbon, {A_("1")} for base', "deck: the plan"),
         ("R+C26", "Plant closed, weeks of 21 and 28 Dec 2026", "π", "capacity arrival set to 0, every line, 2 weeks", "deck, live"),
         ("R+E4", "Commercial order, 300 RW-4418, week of 9 Nov 2026", "π", "order arrival +300 in 1 week", "deck, live"),
         ("R+P1", "Priority order on the MTB carbon line", "objective", "one step replaced by six ordered steps", "deck, live"),
         ("R+E5", "RW-9304 built in lots of 50", "lot", "applied when rounding the LP solution; exact form is a MIP", "deck, live; outside the LP"),
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
p4 = page(4, "Linear program", "One SKU from the network to the program. A scenario is a change of parameters; the program is fixed.", network() + vrule(860, 232, 530) + matrices() + vrule(1520, 232, 530) + staircase() + dynamics())

# ================================================================ 6 · scenarios A, R, R+
# Every number from docs/deck/deck_numbers.json, keys A, R, R+ (the solver session's final set). Same layout on each
# scenario slide: change against the parent; context, change, result notes; builds by line and month.
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
                  ("+2 weeks", "per scenario on every target date: 6 Sep, 20 Sep, 4 Oct 2027"),
                  ("Carbon lines only", "shift from R to R+; base lines unchanged")])
    g += text_col(110, 400, [
        ("Scenario context", ["One network, one solver, one objective; three settings of build time.",
                              f'{B_("A")}: none. A bike ships in the week it is built.',
                              f'{B_("R")}: one week, every line.',
                              f'{B_("R+")}: two weeks on carbon lines, one on base lines.']),
        ("Assumptions", ["Build times are assumptions; the data contains no lead times.",
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
    rows = [("Position-weeks below target", [f'{S[k]["Position-weeks below target"]:,}' for k in sc_]),
            ("All targets held from", [fd(D_(S[k]["All targets held from"])) for k in sc_]),
            ("On-time fill", [f'{100*S[k]["On-time fill rate"]:.1f}%' for k in sc_])]
    xs = [1380, 1580, 1790]; ty = 866
    g += rule(856, 730, 1810) + f'<rect x="1610" y="{ty}" width="196" height="{26 * len(rows) + 40}" rx="8" fill="{tint(SC_C["R+"], .10)}"/>'
    g += "".join(txt(x, ty + 20, h, 14, GREY, 700, "end") for x, h in zip(xs, sc_))
    for i, (lab, vals) in enumerate(rows):
        y = ty + 48 + 26 * i
        g += txt(730, y, lab, 16, INK, 700) + "".join(txt(x, y, v_, 16, INK, 700 if j == 2 else 400, "end") for j, (x, v_) in enumerate(zip(xs, vals)))
    return g
p6 = page(7, "Scenarios A, R and R+", "The same network and solver with three settings of build time. R+ is the plan.", scenarios_page())

# ---- 6 · scenario R+
NM = 16                                       # Sep 2026 - Dec 2027
def line_panel(x0, y0, w, h, ln, sc="R+", shade=None):
    sk = sorted([s for s, d in SD[sc]["sku"].items() if d["line"] == ln], key=lambda s: "SML".index(SD[sc]["sku"][s]["size"]))
    ms = MONTHS[:NM]
    built = {s: [monthly(SD[sc]["sku"][s]["built"], wk) for _, wk in ms] for s in sk}
    fore = [sum(monthly(SD[sc]["sku"][s]["forecast"], wk) for s in sk) for _, wk in ms]
    cap = [monthly(DN[sc]["capacity_by_line_by_week"][ln], wk) for _, wk in ms]
    opn = [sum(monthly(SD[sc]["sku"][s]["open_orders"], wk, "last") for s in sk) for _, wk in ms]
    top = max(max(cap), max(opn), max(fore)) * 1.08
    gw = w / NM; Y = lambda q: y0 + h - q * h / top
    held = D_(DN[sc]["held_by_line"][ln])
    g = txt(x0, y0 - 16, f'{B_(LNAME[ln])}<tspan style="fill:{GREY};font-size:15px"> build time {bw(sc, ln)} · target held {fd(held)}' + '</tspan>', 19)
    if shade:
        js = [j for j, (m_, wk) in enumerate(ms) if any(shade[0] <= t <= shade[1] for t in wk)]
        g += f'<rect x="{x0 + gw * js[0]}" y="{y0}" width="{gw * len(js)}" height="{h}" fill="{tint(RED, .12)}"/>'
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

def vs_strip(sc, parent, y=226):
    S, P = DN[sc]["scorecard"], DN[parent]["scorecard"]
    pts = round(100 * S["On-time fill rate"], 1) - round(100 * P["On-time fill rate"], 1)
    cols = [("Bikes built", f'{P["Bikes built"]:,}', f'{S["Bikes built"]:,}', "same" if S["Bikes built"] == P["Bikes built"] else f'{S["Bikes built"] - P["Bikes built"]:+,}'),
            ("Position-weeks below target", f'{P["Position-weeks below target"]:,}', f'{S["Position-weeks below target"]:,}', "same" if S["Position-weeks below target"] == P["Position-weeks below target"] else f'{S["Position-weeks below target"] - P["Position-weeks below target"]:+,}'),
            ("All targets held from", fd(D_(P["All targets held from"])), fd(D_(S["All targets held from"])), wdiff(S["All targets held from"], P["All targets held from"])),
            ("On-time fill", f'{100*P["On-time fill rate"]:.1f}%', f'{100*S["On-time fill rate"]:.1f}%', "same" if pts == 0 else f"{pts:+.1f} pt")]
    g = f'<rect x="110" y="{y}" width="1700" height="110" rx="12" fill="{tint(AMB, .07)}"/>'
    g += txt(134, y + 44, parent, 16, GREY, 700) + txt(134, y + 72, sc, 16, INK, 700) + txt(134, y + 98, "change", 16, GREY, 700)
    for i, (h, pv, sv, dv) in enumerate(cols):
        x = 400 + i * 360
        g += txt(x, y + 20, h, 14, GREY, 700) + txt(x, y + 44, pv, 18, GREY) + txt(x, y + 72, sv, 22, INK, 700) + txt(x, y + 98, dv, 16, AMB if dv != "same" else GREY, 700)
    return g
def LEGEND(y=250):
    return ("".join(f'<rect x="{730 + 100 * i}" y="{y - 14}" width="16" height="16" fill="{SIZE_C[k]}"/>' + txt(752 + 100 * i, y, lab, 15, INK) for i, (k, lab) in enumerate([("S", "size S"), ("M", "size M"), ("L", "size L")]))
            + poly([(1040, y - 6), (1074, y - 6)], FORE_C, 2.2) + txt(1082, y, "forecast", 15, INK) + poly([(1170, y - 6), (1204, y - 6)], CAP_C, 1.6, True) + txt(1212, y, "capacity", 15, INK)
            + f'<path d="M1306 {y - 13} l7 7 l-7 7 l-7 -7 z" fill="{OPEN_C}"/>' + txt(1320, y, "open orders, month end", 15, INK)
            + f'<line x1="1510" y1="{y - 14}" x2="1510" y2="{y + 4}" stroke="{INK}" stroke-width="1.4" stroke-dasharray="3 4"/>' + txt(1520, y, "target held", 15, INK) + txt(1810, y, "bikes per month", 14, GREY, 400, "end"))
def scenario_slide(n, sc, parent, title, sub, sections, shade=None, last="", shade_label="closed"):
    assert DN[sc]["checks"]["passed"] == DN[sc]["checks"]["of"]
    g = text_col(110, 252, sections, width=56, size=17, dy=25, gap=6, after=22) + vrule(680, 232, 990) + LEGEND(250)
    for i, ln in enumerate(LORDER):
        x0, y0 = 790 + (i % 2) * 540, 346 + (i // 2) * 360
        g += line_panel(x0, y0, 480, 230, ln, sc, shade)
    return page(n, title, sub, g + (rule(986) + txt(110, 1026, last, 22) if last else ""))
RP, C26, E4, E5, P1 = (DN[k] for k in ("R+", "R+C26", "R+E4", "R+E5", "R+P1"))
assert E4["against_parent"]["other_lines_identical"] and E5["against_parent"]["other_lines_identical"] and E4["scorecard"]["Bikes built"] - RP["scorecard"]["Bikes built"] == 300
assert E5["builds_per_sku_total"]["RW-9304"] == 16300 and E5["deliveries"]["largest_gap_bikes"] == 3 and C26["deliveries"]["largest_gap_bikes"] == 0
assert P1["held_by_line"] == RP["held_by_line"] and P1["per_sku"]["RW-9304"]["at_target"] == "2027-05-31" and P1["per_sku"]["RW-4418"]["at_target"] == "2027-09-13"
p7 = scenario_slide(8, "R+", "R", "Scenario R+", "The build plan: weekly builds per bike against capacity, forecast and open orders.", [
    ("Scenario context", ["The build plan: weekly builds per bike at Reno, 7 Sep 2026 to 25 Dec 2028."]),
    ("Assumptions", ["Two weeks to build on carbon lines, one on base lines.",
                     "Targets: 15 weeks of supply on MTB carbon, 12 on MTB base, 8 on road (10 from Jan 2028).",
                     "Every change is known from week 1."]),
    ("Result notes", ["Each line builds at capacity until just before it holds its target."]),
    ("Why believe it", ["Optimal, proved from its own duals; a second algorithm finds the same plan.",
                        "The only optimal plan, to within 2 bikes.",
                        "No plan delivers more by any date, on any line.",
                        "Consistent: 14 rules between the scenarios hold."])])
# ---- pair pages: R+ against one change. Descriptions on top, the two monthly charts, a time-by-column table below.
WCOL = lambda ts: [(f"{DW[t].day} {DW[t]:%b %y}", [t]) for t in ts]
MCOL = lambda ms: [(f"{datetime.date(m[0], m[1], 1):%b %y}", wk) for m, wk in MONTHS if m in ms]
GAP = [("…", None)]
f_cap = lambda ln: lambda k, wk: sum(DN[k]["capacity_by_line_by_week"][ln][t - 1] for t in wk)
f_bl = lambda ln: lambda k, wk: sum(DN[k]["builds_by_line_by_week"][ln][t - 1] for t in wk)
f_owl = lambda ln: lambda k, wk: round(DN[k]["owed_by_line_by_week"][ln][wk[-1] - 1])
f_bs = lambda sku: lambda k, wk: sum(SD[k]["sku"][sku]["built"][t - 1] for t in wk)
f_ows = lambda sku: lambda k, wk: round(SD[k]["sku"][sku]["open_orders"][wk[-1] - 1])
f_wos = lambda sku: lambda k, wk: round(DN[k]["weeks_of_supply_mtb"][sku][wk[-1] - 1], 1)
def stag_table(y0, sc, cols, rows, first):
    xg, xm, xs, xa, xb = 110, 250, 530, 640, 1810
    cw = (xb - xa) / len(cols)
    g = txt(xg, y0, first, 13, GREY, 700) + "".join(txt(xa + cw * (j + 1) - 8, y0, lab, 13, GREY, 700, "end") for j, (lab, _) in enumerate(cols))
    g += f'<line x1="{xg}" y1="{y0 + 9}" x2="{xb}" y2="{y0 + 9}" stroke="{RULE_C}" stroke-width="1.5"/>'
    y, prev = y0 + 32, None
    for grp, met, fn, fmt in rows:
        for k in ("R+", sc):
            if k == sc: g += f'<rect x="{xm - 8}" y="{y - 16}" width="{xb - xm + 8}" height="22" fill="{tint(AMB, .07)}"/>'
            if grp != prev: g += txt(xg, y, grp, 15, INK, 700); prev = grp
            if k == "R+": g += txt(xm, y, met, 15, INK)
            g += txt(xs, y, k, 14, INK if k == sc else GREY, 700 if k == sc else 400)
            for j, (_, wk) in enumerate(cols):
                if wk is None: continue
                v_ = fn(k, wk); hit = k == sc and v_ != fn("R+", wk)
                g += txt(xa + cw * (j + 1) - 8, y, fmt.format(v_), 15, AMB if hit else INK, 700 if hit else 400, "end")
            y += 22
        y += 6
    return g
RP_DESC = [("Settings", "Build time 2 weeks on carbon lines, 1 on base lines. Stock at Reno and the PDC pooled against every order. Even rule."),
           ("Result", "94,429 bikes. All targets held from 4 Oct 2027. 367 position-weeks below target. On-time fill 94.8%.")]
def desc(x0, key, cap, items):
    g = txt(x0, 246, key, 22, INK, 700) + txt(x0 + 20 + 15 * len(key), 246, cap, 16, GREY)
    y = 280
    for lab, text in items:
        g += f'<text x="{x0}" y="{y}" style="font-size:12px;font-weight:700;fill:{AMB};letter-spacing:1.2px">{lab.upper()}</text>'
        for r_ in textwrap.wrap(text, 96): g += txt(x0 + 90, y, r_, 16); y += 22
        y += 6
    return g
def pair_page(n, sc, title, sub, cap, items, cols, rows, first, shade=None, shade_label=""):
    assert DN[sc]["checks"]["passed"] == DN[sc]["checks"]["of"]
    g = desc(110, "R+", "reference", RP_DESC) + desc(980, sc, cap, items) + vrule(940, 226, 670)
    for k, x0 in (("R+", 110), (sc, 980)):
        g += line_panel(x0, 506, 760, 136, "mtb-carbon", k, shade if k == sc else None)
    ly = 448
    lg = "".join(f'<rect x="{110 + 90 * i}" y="{ly - 12}" width="14" height="14" fill="{SIZE_C[c]}"/>' + txt(130 + 90 * i, ly, lab, 14, INK) for i, (c, lab) in enumerate([("S", "size S"), ("M", "size M"), ("L", "size L")]))
    lg += poly([(390, ly - 5), (420, ly - 5)], FORE_C, 2.2) + txt(428, ly, "forecast", 14, INK) + poly([(510, ly - 5), (540, ly - 5)], CAP_C, 1.6, True) + txt(548, ly, "capacity", 14, INK)
    lg += f'<path d="M636 {ly - 12} l7 7 l-7 7 l-7 -7 z" fill="{OPEN_C}"/>' + txt(650, ly, "open orders, month end", 14, INK) + f'<line x1="822" y1="{ly - 12}" x2="822" y2="{ly + 2}" stroke="{INK}" stroke-width="1.4" stroke-dasharray="3 4"/>' + txt(832, ly, "target held", 14, INK)
    if shade: lg += f'<rect x="930" y="{ly - 12}" width="14" height="14" fill="{tint(RED, .12)}"/>' + txt(950, ly, shade_label, 14, INK)
    lg += txt(1810, ly, "MTB carbon, bikes per month", 14, GREY, 400, "end")
    g += lg + rule(704) + stag_table(742, sc, cols, rows, first) + txt(250, 742, "amber: differs from R+", 13, GREY)
    return page(n, title, sub, g)
# facts stated on the pages, checked against the data before the pages are written
_rb = lambda sc, ln, a, b: sum(DN[sc]["builds_by_line_by_week"][ln][a - 1:b])
assert _rb("R+C26", "road-base", 12, 15) - _rb("R+", "road-base", 12, 15) == _rb("R+", "road-base", 16, 17) == 229
assert [DN["R+C26"]["builds_by_line_by_week"]["road-base"][t - 1] for t in (16, 17)] == [0, 0]
assert DN["R+C26"]["owed_by_line_by_week"]["mtb-carbon"][18] == 724 and DN["R+"]["owed_by_line_by_week"]["mtb-carbon"][18] == 0
assert all(_rb("R+E4", "mtb-carbon", t, t) == _rb("R+", "mtb-carbon", t, t) for t in range(1, 53)) and _rb("R+E4", "mtb-carbon", 53, 121) - _rb("R+", "mtb-carbon", 53, 121) == 300
assert [f_bs('RW-4418')(k, [1, 2, 3, 4, 5, 6, 7, 8]) for k in ('R+', 'R+E4')] == [1090, 1269]
assert all(x % 50 == 0 for x in SD["R+E5"]["sku"]["RW-9304"]["built"]) and all(_rb("R+E5", "mtb-carbon", t, t) == 375 for t in range(1, 11))
p9 = pair_page(9, "R+C26", "Scenario R+C26: all lines closed for two weeks", "R+ with capacity set to 0 on all four lines in the weeks of 21 and 28 Dec 2026.", "all lines closed",
    [("Change", "Capacity arrival set to 0 on all four lines in weeks 16–17 (21 Dec 2026 – 3 Jan 2027): 8 entries."),
     ("Result", "94,429 bikes. All targets held from 25 Oct 2027 (+3 weeks). 394 position-weeks below target (+27). On-time fill 93.8%."),
     ("Effect", "MTB carbon builds nothing in the two weeks; its open orders reach 724 on 11 Jan 2027, where R+ has 0. Road base, below capacity in R+, builds the 229 bikes of the closed weeks in weeks 12–15.")],
    WCOL(range(12, 23)),
    [("MTB carbon", "Capacity", f_cap("mtb-carbon"), "{:,}"), ("MTB carbon", "Build plan", f_bl("mtb-carbon"), "{:,}"), ("MTB carbon", "Open orders, end of week", f_owl("mtb-carbon"), "{:,}"),
     ("Road base", "Build plan", f_bl("road-base"), "{:,}")], "week of", shade=(16, 17), shade_label="closed")
p10 = pair_page(10, "R+E4", "Scenario R+E4: 300 RW-4418 added", "R+ with a commercial order for 300 RW-4418 added in the week of 9 Nov 2026.", "fleet order",
    [("Change", "Order arrival +300 on RW-4418, commercial channel, week 10 (9 Nov 2026): 1 entry."),
     ("Result", "94,729 bikes (+300). All targets held from 11 Oct 2027 (+1 week). 370 position-weeks below target (+3). On-time fill 94.0%."),
     ("Effect", "MTB carbon is at capacity until Sep 2027, so the line total does not change before then; the mix changes (RW-4418: 1,269 in Sep–Oct 2026, against 1,090). The line builds 300 more in Sep 2027, when capacity rises to 580 a week. Other lines unchanged.")],
    MCOL([(2026, 9), (2026, 10), (2026, 11), (2026, 12), (2027, 1)]) + GAP + MCOL([(2027, 8), (2027, 9), (2027, 10)]),
    [("RW-4418", "Build plan", f_bs("RW-4418"), "{:,}"), ("RW-4418", "Open orders, month end", f_ows("RW-4418"), "{:,}"),
     ("MTB carbon", "Build plan", f_bl("mtb-carbon"), "{:,}")], "month", shade=(10, 10), shade_label="order arrives")
p11 = pair_page(11, "R+E5", "Scenario R+E5: RW-9304 in lots of 50", "R+ with every RW-9304 build a whole multiple of 50.", "lots of 50",
    [("Change", "Lot size of make RW-9304 set to 50 in all weeks. The LP is unchanged; the lot size is applied when its solution is rounded to whole bikes."),
     ("Result", "94,462 bikes (+33, all RW-9304: 16,300). All targets held from 4 Oct 2027. 367 position-weeks below target. On-time fill 94.8%."),
     ("Effect", "Every RW-9304 build is a multiple of 50 and the line stays at 375 a week; RW-4418 and RW-6416 take the difference. 3 RW-9304 bikes are delivered one week late (11 Jan 2027).")],
    WCOL(range(1, 11)),
    [("RW-9304", "Build plan", f_bs("RW-9304"), "{:,}"), ("RW-4418", "Build plan", f_bs("RW-4418"), "{:,}"), ("RW-6416", "Build plan", f_bs("RW-6416"), "{:,}")], "week of")
p12 = pair_page(12, "R+P1", "Scenario R+P1: priority order on MTB carbon", "R+ with the objective replaced by six ordered steps. Network and data unchanged.", "priority order",
    [("Change", "Objective only. Six steps, each minimised and then held: past-due orders; open orders; target for RW-9304, then RW-4418, then RW-6416; target for the other seven SKUs."),
     ("Result", "94,429 bikes. All targets held from 4 Oct 2027. 346 position-weeks below target (−21). On-time fill 94.8%."),
     ("Effect", "RW-9304 reaches target on 31 May 2027, RW-4418 on 13 Sep, RW-6416 on 4 Oct; in R+ all three reach it on 4 Oct. Step 1 covers every line, so road carbon’s mix changes in a few early weeks.")],
    MCOL([(2026, 12), (2027, 1), (2027, 2), (2027, 3), (2027, 4), (2027, 5), (2027, 6), (2027, 7), (2027, 8), (2027, 9), (2027, 10)]),
    [("RW-9304", "Weeks of supply, month end", f_wos("RW-9304"), "{:.1f}"), ("RW-4418", "Weeks of supply, month end", f_wos("RW-4418"), "{:.1f}"),
     ("RW-6416", "Weeks of supply, month end", f_wos("RW-6416"), "{:.1f}")], "month")
# ================================================================ 5b · priority order
# Planning priors: scenarios.CASE_RP.priors (settings a planner writes; not in the data). Floors for RW-4418, week 1:
# NOTE_TO_DECK_BOT.md §2 (net -1,285; due -123; owed 0; target 857). Two bikes: tests/test_engine.py
# test_walk_on_two_bikes (builds pinned; net = previous net + builds, no demand). R+ against R+P1: deck_numbers.json
# weeks_of_supply_mtb and per_sku at_target; the walk's six steps from R+P1.walk.
PO_C = {"RW-9304": "#b45309", "RW-4418": "#111827", "RW-6416": "#2563eb"}; MTB = ["RW-9304", "RW-4418", "RW-6416"]
def priors_col(x, y):
    rows = [("Routes", "every site serves every customer"), ("Build time", "carbon lines 2 weeks, base lines 1"),
            ("Transfer Reno → PDC", "1 week; not used in R+"), ("Plan decides", "make; move off"),
            ("Targets", "road 8 wk (10 from 2028), MTB base 12, MTB carbon 15"), ("Undated order", "due 7 days after it was placed")]
    g = sec_head(x, y, "Planning priors") + txt(x, y + 26, "Settings a planner writes; none is in the data.", 16, GREY)
    for i, (a, b) in enumerate(rows):
        yy = y + 62 + 30 * i
        g += txt(x, yy, a, 16, INK, 700) + txt(x + 190, yy, b, 15)
    return g
def floors_col(x, y):
    net, due, owed, tgt = NUM["rw4418_floors"]
    g = sec_head(x, y, "Floors") + txt(x, y + 26, "Levels net inventory must reach, read from the object.", 16, GREY)
    lo, hi = -1500, 1000; y0, y1 = y + 80, y + 300
    Y = lambda v: y1 - (v - lo) * (y1 - y0) / (hi - lo)
    g += f'<line x1="{x + 150}" y1="{y0}" x2="{x + 150}" y2="{y1}" stroke="{LIGHT}" stroke-width="2"/>'
    for v, lab, word, off in [(tgt, "target", "the next 15 weeks of forecast", 5), (owed, "owed", "no customer waiting", -6), (due, "due", "no order past its date", 16)]:
        g += f'<line x1="{x + 130}" y1="{Y(v)}" x2="{x + 170}" y2="{Y(v)}" stroke="{INK}" stroke-width="2.5"/>'
        g += txt(x + 120, Y(v) + off, f"{v:+,}" if v else "0", 15, INK, 700, "end") + txt(x + 182, Y(v) + off, f'{B_(lab)} <tspan style="fill:{GREY}">{word}</tspan>', 15)
    g += f'<circle cx="{x + 150}" cy="{Y(net)}" r="6" fill="{AMB}"/>' + txt(x + 120, Y(net) + 5, f"{net:,}", 15, AMB, 700, "end") + txt(x + 182, Y(net) + 5, "RW-4418, week 1: 25 in stock, 1,310 on order", 15, GREY)
    return g + txt(x, y1 + 36, "Below a floor is a need; the lower the floor, the more it counts.", 16)
TWO = [("Even rule", [[0, 0], [5, 5], [10, 10], [15, 15]]),
       ("Y first", [[-10, 10], [-10, 20], [0, 20], [10, 20]]),
       ("Customers, then Y first", [[0, 0], [0, 10], [0, 20], [10, 20]])]
def two_bikes(x, y):
    g = sec_head(x, y, "Two bikes, one line") + txt(x, y + 26, "10 a week, no new orders. X: 10 customers waiting. Target 20 each.", 16, GREY)
    g += txt(x, y + 50, "Net inventory at the end of each week, X / Y", 15, GREY)
    g += "".join(txt(x + 215 + 78 * j, y + 82, f"week {j + 1}", 13, GREY, 700, "middle") for j in range(4))
    for i, (rule_, cells) in enumerate(TWO):
        yy = y + 118 + 46 * i
        g += txt(x, yy, rule_, 16, INK, 700)
        for j, (cx, cy) in enumerate(cells):
            px = x + 215 + 78 * j
            g += f'<rect x="{px - 36}" y="{yy - 21}" width="72" height="30" rx="6" fill="{tint(RED, .15) if cx < 0 else "#f3f4f6"}"/>'
            g += txt(px, yy, f"{cx} / {cy}", 14, RED if cx < 0 else INK, 700 if cx < 0 else 400, "middle")
    return g + lines(x, y + 274, ["Ranking the bikes alone keeps X’s customers waiting two weeks.", "A step for customers first, then the ranking, does not."], 16, INK, 24)
def p1_chart(x0, y0, w, h):
    W1 = 60; x1, y1 = x0 + w, y0 + h
    X = lambda t: x0 + (t - 1) * w / (W1 - 1); Y = lambda v: y1 - (v + 25) * h / 42
    g = sec_head(x0, y0 - 56, "R+ against R+P1") + txt(x0, y0 - 30, "Weeks of supply, MTB carbon bikes. Grey dashed: R+, all three together.", 16, GREY)
    g += "".join(f'<line x1="{x0}" y1="{Y(v)}" x2="{x1}" y2="{Y(v)}" stroke="{RULE_C}" stroke-width="1"/>' + txt(x0 - 8, Y(v) + 5, f"{v}", 13, GREY, 400, "end") for v in (-20, -10, 0, 10))
    g += f'<line x1="{x0}" y1="{Y(15)}" x2="{x1}" y2="{Y(15)}" stroke="{INK}" stroke-width="1.5" stroke-dasharray="6 5"/>' + txt(x0 - 8, Y(15) + 5, "15", 13, INK, 700, "end")
    for k in MTB:
        g += poly([(X(t), Y(v)) for t, v in zip(range(1, W1 + 1), DN["R+"]["weeks_of_supply_mtb"][k][:W1])], LIGHT, 2, True)
    for k in MTB:
        g += poly([(X(t), Y(v)) for t, v in zip(range(1, W1 + 1), DN["R+P1"]["weeks_of_supply_mtb"][k][:W1])], PO_C[k], 2.5)
        wt = WK_OF_DN(DN["R+P1"]["per_sku"][k]["at_target"])
        g += f'<circle cx="{X(wt)}" cy="{Y(15)}" r="5" fill="{PO_C[k]}" stroke="#fff" stroke-width="1.5"/>'
    g += "".join(txt(X(t), y1 + 22, lab, 13, GREY, 400, "middle") for t, lab in [(1, "Sep 2026"), (18, "Jan 2027"), (35, "May 2027"), (53, "Sep 2027")])
    for i, k in enumerate(MTB):
        g += f'<rect x="{x0 + 190 * i}" y="{y1 + 40}" width="14" height="14" fill="{PO_C[k]}"/>' + txt(x0 + 20 + 190 * i, y1 + 52, f'{k}: {fd(D_(DN["R+P1"]["per_sku"][k]["at_target"]))}', 14, INK)
    return g
def priority_page():
    assert DN["R+P1"]["held_by_line"] == DN["R+"]["held_by_line"] and DN["R+P1"]["scorecard"]["Bikes built"] == DN["R+"]["scorecard"]["Bikes built"]
    assert [w["floor"] for w in DN["R+P1"]["walk"]] == ["due", "owed", "target", "target", "target", "target"]
    g = txt(110, 250, "A scenario has three parts a planner can read and change: the world (stock, capacity, demand), the rules (routes, build times, what the plan decides) and the purpose: what the plan protects first.", 19)
    g += priors_col(110, 310) + floors_col(110, 560)
    g += vrule(700, 296, 940) + two_bikes(740, 310)
    g += vrule(1240, 296, 940) + p1_chart(1310, 420, 490, 300)
    g += rule(690, 740, 1200) + sec_head(740, 736, "Scenario R+P1, six steps in turn") + lines(740, 766, ["1  due, every bike  2  owed, every bike", "3  target, RW-9304  4  target, RW-4418  5  target, RW-6416", "6  target, the other seven bikes"], 16, INK, 24)
    g += txt(740, 860, "Each step: minimise its shortfall, hold the result, then the next step.", 16, GREY)
    g += rule(968) + txt(110, 1012, "A priority order changes the objective only. R+P1 builds R+’s bikes and holds every line’s target on R+’s date; it changes the order in which the three bikes get there.", 20)
    return g
p5 = page(5, "Priority order", "The third part of a scenario: what the plan protects first, written as ordered steps.", priority_page())

# ================================================================ 0 · cover, divider, close
def cover():
    g = txt(110, 420, "Redwheel build plan", 72, INK, 700) + txt(110, 476, "A resource–task network, a linear program, and the plan they produce.", 28, GREY)
    arc = [("1", "Planning system", "from the data files to the plan"), ("2–3", "The object", "Redwheel as a network; how its parts interact"),
           ("4", "Linear program", "how the network becomes the program"), ("5", "Priority order", "what the plan protects first"),
           ("6", "Scenarios", "the full set and what each edits"), ("7–8", "The plan", "build time; scenario R+"), ("9–12", "Changes to R+", "four edits, each shown against R+")]
    for i, (n, h, d) in enumerate(arc):
        x = 110 + i * 244
        g += f'<rect x="{x}" y="600" width="226" height="150" rx="12" fill="{tint(AMB, .07)}"/>' + txt(x + 20, 640, n, 16, AMB, 700) + txt(x + 20, 672, h, 21, INK, 700) + lines(x + 20, 702, textwrap.wrap(d, 22), 16, GREY, 22)
    g += txt(110, 900, "Every number on these slides is read from docs/deck/deck_numbers.json, written by one run of every scenario through the product, with every plan check passing.", 17, GREY)
    g += txt(110, 928, "16 November 2026.", 17, GREY)
    return f'<svg width="1920" height="1080" viewBox="0 0 1920 1080">{DEFS}{g}</svg>'
def divider():
    S = {k: DN[k]["scorecard"] for k in ("A", "R", "R+", "R+C26", "R+E4", "R+E5", "R+P1")}
    peak = max(DN["R+C26"]["owed_by_line_by_week"]["mtb-carbon"][16:22])
    assert peak == 724 and DN["R+E5"]["builds_per_sku_total"]["RW-9304"] == 16300 and NUM["frames_test"] == "3, 0, 9, 4"
    held = lambda k: fd(D_(S[k]["All targets held from"]))
    even = "Even rule: the worst SKU on each line, in weeks short, then the total."
    rows = [("A", "A bike ships in the week it is built.", "None: the base object; make output in A₀.", even, f"All targets held from {held('A')}."),
            ("R", "One week from build to stock that can ship, every line.", "Make output entry moved from A₀ to A₁ on all four lines.", "Even rule.", f"All targets held from {held('R')} (+2 weeks)."),
            ("R+", "Two weeks on carbon lines, one on base lines. The build plan.", "Make output entry in A₂ on carbon lines, A₁ on base lines.", "Even rule.", f"{S['R+']['Bikes built']:,} bikes; all targets held from {held('R+')} (+2 weeks)."),
            ("R+C26", "All lines closed in the weeks of 21 and 28 Dec 2026.", "π: capacity arrival 0 on 4 lines × 2 weeks (8 entries).", "Even rule.", f"Up to {peak} MTB carbon bikes owed in Jan 2027; targets held from {held('R+C26')} (+3 weeks)."),
            ("R+E4", "Commercial order for 300 RW-4418 in the week of 9 Nov 2026.", "π: order arrival +300 on RW-4418, commercial channel (1 entry).", "Even rule.", f"{S['R+E4']['Bikes built']:,} bikes (+300); MTB carbon target held {fd(D_(DN['R+E4']['held_by_line']['mtb-carbon']))} (+1 week)."),
            ("R+E5", "RW-9304 built in whole lots of 50.", "Lot size 50 on make RW-9304, applied when the LP solution is rounded.", "Even rule.", "RW-9304 total 16,300 (+33); no target date moves."),
            ("R+P1", "Priority order on the MTB carbon line.", "None.", "Six steps, each minimised then held: past-due orders; open orders; target for RW-9304, RW-4418, RW-6416 in turn; target for the rest.",
             "RW-9304 at target 31 May 2027, RW-4418 13 Sep, RW-6416 4 Oct; line dates as R+."),
            ("Test", "Bought frame with a 2-week lead time; small test network, not Redwheel data.", "One new resource row (frames), one new task column (buy); its +1 in A₂.", "Even rule.", "Builds 3, 0, 9, 4 in weeks 1–4.")]
    X = [110, 220, 640, 1060, 1420]; W = [None, 44, 44, 38, 42]
    g = "".join(txt(x, 258, h, 14, GREY, 700) for x, h in zip(X, ["Scenario", "Description", "Edit to the RTN", "Objective", "Result"]))
    g += f'<line x1="110" y1="272" x2="1810" y2="272" stroke="{RULE_C}" stroke-width="1.5"/>'
    y = 304
    for k, *cells in rows:
        wrapped = [textwrap.wrap(c, w) for c, w in zip(cells, W[1:])]
        h = 24 * max(len(w) for w in wrapped) + 22
        if k == "R+": g += f'<rect x="96" y="{y - 24}" width="1728" height="{h}" rx="8" fill="{tint(AMB, .08)}"/>'
        col = GREY if k == "Test" else INK
        g += txt(X[0], y, k, 19, col, 700)
        for x, lines_ in zip(X[1:], wrapped):
            g += "".join(txt(x, y + 24 * r, ln_, 16, col) for r, ln_ in enumerate(lines_))
        y += h
        if k in ("R+", "R+P1"): g += f'<line x1="110" y1="{y - 18}" x2="1810" y2="{y - 18}" stroke="{RULE_C}" stroke-width="1.5"/>'; y += 8
    return page(6, "Scenarios", "Each scenario edits the RTN parameters or the objective. The program is the same in every one.", g)
p0 = cover(); p8 = divider()
pages = [p0, p1, p2, p3, p4, p5, p8, p6, p7, p9, p10, p11, p12]
N_PAGES = len(pages) - 1
pages = [p.replace('§N§', str(N_PAGES)) for p in pages]
head = f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>'
(out / "object.html").write_text(head + "".join(pages) + "</body></html>")
for i, p in enumerate(pages, 1): (out / f"p{i}.html").write_text(head + p + "</body></html>")
