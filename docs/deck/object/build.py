"""Object deck. Usage: python3 build.py OUTDIR  -> object.html, p1..p4.html (print object.html to PDF with Chrome)."""
import sys, pathlib
out = pathlib.Path(sys.argv[1])
CSS = '''@page{size:1920px 1080px;margin:0}
html,body{margin:0;background:#fff}
svg{display:block;font-family:"Helvetica Neue",Helvetica,Arial,sans-serif;page-break-after:always}
.h1{font-size:50px;font-weight:700;fill:#111827}
.tag{font-size:17px;font-weight:700;letter-spacing:2.5px;fill:#6b7280}
.name{font-size:26px;font-weight:600;fill:#111827}
.num{font-size:38px;font-weight:700;fill:#111827}
.dim{fill:#9ca3af;font-weight:400}
.res{fill:#fff;stroke:#111827;stroke-width:2.5}
.task{fill:#111827}
.tname{font-size:24px;fill:#d1d5db}
.tnum{font-size:34px;font-weight:700;fill:#fff}
.wire{stroke:#111827;stroke-width:2.5;fill:none}
.amt{font-size:24px;font-weight:700;fill:#b45309}
.st{font-size:27px;fill:#111827}
.b{font-weight:700}
.note{font-size:23px;fill:#6b7280}
.mono{font-family:Menlo,Consolas,monospace;font-size:27px;fill:#111827}
.cell{font-family:Menlo,Consolas,monospace;font-size:28px;fill:#111827}
.colh{font-family:Menlo,Consolas,monospace;font-size:20px;fill:#6b7280}
.pg{font-size:18px;fill:#9ca3af}'''
DEFS = '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto"><path d="M0 0L10 5L0 10z" fill="#111827"/></marker></defs>'
def page(n, title, body):
    return f'<svg width="1920" height="1080" viewBox="0 0 1920 1080">{DEFS}<text x="110" y="112" class="h1">{title}</text>{body}<text x="1810" y="1048" class="pg" text-anchor="end">{n}</text></svg>'
def rule(y): return f'<line x1="110" y1="{y}" x2="1810" y2="{y}" stroke="#e5e7eb" stroke-width="2"/>'
def lines(x, y, rows, cls="st", dy=38): return "".join(f'<text x="{x}" y="{y+i*dy}" class="{cls}">{r}</text>' for i, r in enumerate(rows))
def res(x, y, w, name, val, h=120): return f'<rect class="res" x="{x}" y="{y}" width="{w}" height="{h}" rx="22"/><text x="{x+26}" y="{y+48}" class="name">{name}</text><text x="{x+26}" y="{y+98}" class="num">{val}</text>'
def task(x, y, name, w=180): return f'<rect class="task" x="{x}" y="{y}" width="{w}" height="120" rx="8"/><text x="{x+w/2}" y="{y+72}" class="tnum" text-anchor="middle">{name}</text>'
def edge(x1, y1, x2, y2, lab, lx=None, ly=None, anchor="middle"):
    lx = (x1 + x2) / 2 if lx is None else lx; ly = y1 - 16 if ly is None else ly
    return f'<path class="wire" marker-end="url(#a)" d="M{x1} {y1} L{x2} {y2}"/><text x="{lx}" y="{ly}" class="amt" text-anchor="{anchor}">{lab}</text>'

# ---------- 1: the object
U, M = 520, 740
orders = f'''<rect class="res" x="1500" y="{U-60}" width="310" height="{M-U+120}" rx="22"/>
<text x="1526" y="{U-12}" class="name">Open orders</text><text x="1526" y="{U+40}" class="num">1,310</text>
<text x="1526" y="{U+98}" class="note">Dealers</text><text x="1784" y="{U+98}" class="note" text-anchor="end">669</text>
<text x="1526" y="{U+136}" class="note">Web</text><text x="1784" y="{U+136}" class="note" text-anchor="end">496</text>
<text x="1526" y="{U+174}" class="note">Commercial</text><text x="1784" y="{U+174}" class="note" text-anchor="end">145</text>
<line x1="1526" y1="{U+196}" x2="1784" y2="{U+196}" stroke="#e5e7eb" stroke-width="2"/>
<text x="1526" y="{U+234}" class="note">Forecast</text><text x="1784" y="{U+234}" class="note" text-anchor="end">+50 / wk</text>'''
graph = (res(110, M-60, 290, "MTB carbon line", "375 / wk") + edge(400, M, 446, M, "−1", ly=M-22) + task(450, M-60, "make") + edge(630, M, 676, M, "+1", ly=M-22)
 + res(680, M-60, 290, "Reno", "25 bikes") + edge(970, M, 1246, M, "−1", lx=1010, ly=M-22) + task(1250, M-60, "fulfil") + edge(1430, M, 1496, M, "−1", ly=M-22)
 + edge(790, M-60, 790, U+64, "−1", lx=772, ly=(M+U)/2+10, anchor="end") + task(700, U-60, "move")
 + edge(880, U, 1000, U, "+1, 1 wk", ly=U-22) + res(1004, U-60, 200, "Columbus", "0 bikes") + edge(1204, U, 1246, U, "−1", ly=U-22) + task(1250, U-60, "fulfil") + edge(1430, U, 1496, U, "−1", ly=U-22) + orders)
legend = ('<rect class="res" x="110" y="893" width="46" height="34" rx="10"/><text x="172" y="919" class="note"><tspan class="b" fill="#111827">Resource node.</tspan> A level per week: inventory, open orders, capacity.</text>'
 '<rect class="task" x="110" y="943" width="46" height="34" rx="5"/><text x="172" y="969" class="note"><tspan class="b" fill="#111827">Task node.</tspan> A number of runs per week. The plan decides make and move; fulfil is assumed: orders ship as stock allows.</text>'
 '<path class="wire" marker-end="url(#a)" d="M110 1010 L154 1010"/><text x="172" y="1018" class="note"><tspan class="b" fill="#111827">Edge.</tspan> Task to resource, with an amount per run and a delay in weeks (0 unless shown).</text>')
p1 = page(1, "The object: Redwheel as a resource–task network",
 lines(110, 196, ['<tspan class="b">1. It is generated from master data.</tspan>',
                  "Every SKU × location that holds stock or orders is a resource,",
                  "plus one capacity resource per line. Every routing row is a",
                  "make task; every route is a move or a fulfil task.",
                  '<tspan class="dim" style="fill:#6b7280">→ 74 resources, 80 tasks, 180 edges for 10 SKUs.</tspan>'])
 + lines(990, 196, ['<tspan class="b">2. Every edge is one cause-and-effect link.</tspan>',
                    "Running a task changes a resource’s level by a signed amount,",
                    "after a delay. Levels change in only two ways: through an edge,",
                    "or by an external arrival (forecast orders, weekly capacity).",
                    '<tspan style="fill:#6b7280">So any effect can be traced back along edges to its cause.</tspan>'])
 + rule(392) + '<text x="110" y="432" class="tag">SUBGRAPH FOR ONE SKU · RW-4418 · OPENING STATE 7 SEP 2026</text>'
 + graph + rule(850) + legend)

# ---------- 2: the balance equation
def lane(y, sku, runs, a, b):
    c = y + 48
    return f'''<rect class="task" x="700" y="{y}" width="320" height="96" rx="8"/><text x="724" y="{y+36}" class="tname" style="font-size:21px">make {sku}</text><text x="724" y="{y+78}" class="tnum">{runs} runs</text>
<path class="wire" marker-end="url(#a)" d="M1020 {c} L1216 {c}"/><text x="1118" y="{c-14}" class="amt" text-anchor="middle">+1</text>
<rect class="res" x="1220" y="{y}" width="590" height="96" rx="22"/><text x="1246" y="{c+9}" class="name">{sku} at Reno</text><text x="1784" y="{c+13}" class="num" text-anchor="end">{a} <tspan class="dim">→</tspan> {b}</text>'''
Y = [404, 524, 644]; C = [y + 48 for y in Y]
fan = (f'<path class="wire" marker-end="url(#a)" d="M510 {C[1]-28} C600 {C[1]-28} 610 {C[0]} 696 {C[0]}"/><path class="wire" marker-end="url(#a)" d="M510 {C[1]} L696 {C[1]}"/><path class="wire" marker-end="url(#a)" d="M510 {C[1]+28} C600 {C[1]+28} 610 {C[2]} 696 {C[2]}"/>'
 + f'<text x="640" y="{C[0]-18}" class="amt" text-anchor="end">−1</text><text x="640" y="{C[1]-14}" class="amt" text-anchor="end">−1</text><text x="640" y="{C[2]+38}" class="amt" text-anchor="end">−1</text>')
def trow(y, name, kind, a, b, c, d):
    return (f'<text x="110" y="{y}" class="st"><tspan class="b">{name}</tspan>  <tspan style="fill:#6b7280;font-size:23px">{kind}</tspan></text>'
     + "".join(f'<text x="{x}" y="{y}" class="cell" text-anchor="end">{v}</text>' for x, v in zip([980, 1330, 1560, 1790], [a, b, c, d])))
thead = "".join(f'<text x="{x}" y="800" class="colh" text-anchor="end">{h}</text>' for x, h in zip([980, 1330, 1560, 1790], ["carry · level[t−1]", "Σ amount · runs", "arrival[t]", "= level[t]"]))
p2 = page(2, "Every level follows one balance equation",
 '<text x="110" y="190" class="mono">level[r, t]  =  carry[r] · level[r, t−1]  +  Σ amount[e] · runs[task(e), t − delay(e)]  +  arrival[r, t]</text>'
 + '<text x="110" y="234" class="note">Sum over the edges e that end at resource r.  carry = 1 for inventory and orders, 0 for capacity.  level ≥ 0, so a line cannot overbuild.</text>'
 + rule(278) + '<text x="110" y="324" class="tag">WORKED: MTB CARBON LINE · WEEK OF 21 SEP 2026 (t = 3) · RUNS FROM THE PLAN · INVENTORY BEFORE ORDERS SHIP</text>'
 + f'<rect class="res" x="110" y="{C[1]-85}" width="400" height="170" rx="22"/><text x="136" y="{C[1]-38}" class="name">MTB carbon line</text><text x="136" y="{C[1]+16}" class="num">375 <tspan class="dim">→</tspan> 0</text><text x="136" y="{C[1]+56}" class="note">arrives → left after runs</text>'
 + fan + lane(Y[0], "RW-4418", 142, 247, 389) + lane(Y[1], "RW-6416", 89, 128, 217) + lane(Y[2], "RW-9304", 144, 425, 569)
 + thead + trow(850, "MTB carbon line", "capacity, carry 0", "0", "−142 −89 −144", "+375", "= 0") + trow(900, "RW-4418 at Reno", "inventory, carry 1", "247", "+142", "0", "= 389")
 + rule(940) + '<text x="110" y="992" class="st">74 resources × 121 weeks = 8,954 of these rows. They are the constraints the solver receives; the runs are its decision variables.</text>')


# ---------- 3: why it works
def rn(x, c, name, val, w=200):
    return f'<rect class="res" x="{x}" y="{c-36}" width="{w}" height="72" rx="16"/><text x="{x+16}" y="{c-6}" class="name" style="font-size:19px">{name}</text><text x="{x+16}" y="{c+24}" class="num" style="font-size:25px">{val}</text>'
def tk(x, c, name, w=130, h=72, val=None):
    if val is None: return f'<rect class="task" x="{x}" y="{c-h/2}" width="{w}" height="{h}" rx="6"/><text x="{x+w/2}" y="{c+9}" class="tnum" style="font-size:25px" text-anchor="middle">{name}</text>'
    return f'<rect class="task" x="{x}" y="{c-h/2}" width="{w}" height="{h}" rx="6"/><text x="{x+14}" y="{c+7}" class="tname" style="font-size:19px;fill:#fff">{name}</text><text x="{x+w-14}" y="{c+8}" class="tnum" style="font-size:22px" text-anchor="end">{val}</text>'
def ar(x1, y1, x2, y2, lab="", curve=False, ly=None):
    d = f"M{x1} {y1} C{x1+45} {y1} {x2-55} {y2} {x2-4} {y2}" if curve else f"M{x1} {y1} L{x2-4} {y2}"
    t = f'<text x="{(x1+x2)/2}" y="{(ly if ly else min(y1,y2)-12)}" class="amt" style="font-size:21px" text-anchor="middle">{lab}</text>' if lab else ""
    return f'<path class="wire" marker-end="url(#a)" d="{d}"/>{t}'
def panel(px, py, n, pattern, meaning, diagram, text, reading):
    g = f'<text x="{px}" y="{py}" class="st"><tspan class="b">{n}. {pattern}</tspan>  <tspan style="fill:#b45309;font-weight:700">→ {meaning}</tspan></text>'
    g += diagram(px, py + 122)
    g += lines(px, py + 240, text, cls="note", dy=32)
    return g + f'<text x="{px}" y="{py+240+32*len(text)+4}" class="note" style="fill:#111827">{reading}</text>'
dA = lambda x, c: tk(x, c, "make") + ar(x+130, c, x+200, c, "+1") + rn(x+200, c, "Reno stock", "25") + ar(x+400, c, x+470, c, "−1") + tk(x+470, c, "move")
dB = lambda x, c: (rn(x, c, "MTB carbon line", "375 / wk", w=210) + "".join(ar(x+210, c+dy0, x+330, c+dy, curve=True) for dy0, dy in [(-14, -58), (0, 0), (14, 58)])
                   + tk(x+330, c-58, "make RW-4418", w=250, h=46, val="142") + tk(x+330, c, "make RW-6416", w=250, h=46, val="89") + tk(x+330, c+58, "make RW-9304", w=250, h=46, val="144")
                   + f'<text x="{x+270}" y="{c-52}" class="amt" style="font-size:21px" text-anchor="middle">−1</text>')
dC = lambda x, c: (rn(x, c-44, "Line capacity", "has room") + rn(x, c+44, "Frames on hand", "3") + ar(x+200, c-44, x+330, c-12, "−1", ly=c-44) + ar(x+200, c+44, x+330, c+12, "−1", ly=c+62) + tk(x+330, c, "make"))
dD = lambda x, c: rn(x, c, "Reno, week t", "−1") + ar(x+200, c, x+270, c) + tk(x+270, c, "move") + ar(x+400, c, x+530, c, "+1, 1 wk") + rn(x+530, c, "Columbus, week t+1", "+1", w=260)
p3 = page(3, "Why nodes and edges are enough",
 '<text x="110" y="168" class="st">Slide 2 gave one equation and one bound: level ≥ 0. Applied to the graph, they produce the four interactions a supply chain is made of.</text>'
 + rule(204)
 + panel(110, 262, 1, "Series", "dependency", dA,
         ["Reno stock cannot go below zero, so move can send on only", "what is there: 25 bikes on 7 Sep, plus whatever make adds."], "Upstream limits downstream.")
 + panel(1000, 262, 2, "Shared input", "competition", dB,
         ["Three tasks draw on one resource that cannot go below", "zero: 142 + 89 + 144 = 375. One more of one is one less of another."], "SKUs compete for a line.")
 + rule(608)
 + panel(110, 666, 3, "Joint input", "matching", dC,
         ["make takes one build and one frame. Frames have a two-week lead", "time, so builds run 3, 0, 9, 4: none in week 2, though the line has room."], "The scarcer input sets the pace. Tested on a small example, not Redwheel’s data.")
 + panel(1000, 666, 4, "Delay", "lag", dD,
         ["One run of move leaves Reno now and reaches Columbus", "a week later. In between it is counted as in-transit stock."], "Lead time, with nothing lost on the way.")
 + rule(1004) + '<text x="110" y="1046" class="note" style="fill:#111827">None of the four is written as a rule in code. Each is the balance equation and level ≥ 0, read off a different shape of graph.</text>')
# ---------- 4: solving one interaction (base case)
import json, datetime
BD = json.load(open(pathlib.Path(__file__).with_name("base_mtb.json")))
SKUS = ["RW-9304", "RW-4418", "RW-6416"]; COL = {"RW-9304": "#b45309", "RW-4418": "#111827", "RW-6416": "#2563eb"}
def dlab(t): d = datetime.date.fromisoformat(BD["weeks"][str(t)]); return f"{d.day} {d.strftime('%b')}"
# opening state (7 Sep 2026), from the object: stock, open orders, target for week 1 (next 15 weeks of forecast), average weekly forecast
OPEN = {"RW-9304": (10, 1435, 823, 102.5), "RW-4418": (25, 1310, 857, 135.2), "RW-6416": (15, 767, 515, 81.2)}
def bars():
    X = lambda i: 270 + (i - 1) * 116
    g = '<text x="110" y="254" class="tag">THE PLAN · BUILDS PER WEEK, OF 375</text>'
    lx = 560
    for sk in SKUS:
        g += f'<rect x="{lx}" y="238" width="18" height="18" fill="{COL[sk]}"/><text x="{lx+26}" y="254" style="font-size:19px;font-weight:600;fill:#111827">{sk}</text>'; lx += 124
    y0, hh = 470, 180
    for i in range(1, 7):
        top = y0
        for sk in SKUS:
            v = BD["builds"][sk][i - 1]; h = v / 375 * hh; top -= h
            if v:
                g += f'<rect x="{X(i)-38}" y="{top}" width="76" height="{h-1.5}" fill="{COL[sk]}"/>'
                if h >= 22: g += f'<text x="{X(i)}" y="{top+h/2+7}" text-anchor="middle" style="font-size:19px;font-weight:700;fill:#fff">{v}</text>'
                else: g += f'<text x="{X(i)+46}" y="{top+h/2+6}" style="font-size:17px;font-weight:700;fill:{COL[sk]}">{v}</text>'
    g += f'<line x1="200" y1="{y0}" x2="920" y2="{y0}" stroke="#111827" stroke-width="2"/>'
    return g + "".join(f'<text x="{X(i)}" y="{y0+30}" text-anchor="middle" style="font-size:19px;fill:#6b7280">{dlab(i)}</text>' for i in range(1, 7))
RED = "#b91c1c"
N = ["9304", "4418", "6416"]
def xs(n, col=None):
    f = ' fill="%s"' % col if col else ""
    return '<tspan%s>x</tspan><tspan dy="6" style="font-size:68%%"%s>%s</tspan><tspan dy="-6"> </tspan>' % (f, f, n)
def arrow_big(x, y): return f'<path d="M{x} {y} h34" stroke="#9ca3af" stroke-width="4" fill="none"/><path d="M{x+30} {y-9} l14 9 l-14 9 z" fill="#9ca3af"/>'
def mono(x, y, t, fs=23, **kw): return f'<text x="{x}" y="{y}" class="cell" style="font-size:{fs}px;{kw.get("style","")}">{t}</text>'
def frag(y0=330):
    g = ""; C = [y0, y0 + 90, y0 + 180]; cy = C[1]
    g += f'<rect class="res" x="110" y="{cy-40}" width="150" height="80" rx="14"/><text x="124" y="{cy-8}" class="name" style="font-size:17px">line capacity</text><text x="124" y="{cy+22}" class="num" style="font-size:23px">375</text>'
    for c, n, sk in zip(C, N, SKUS):
        g += f'<path class="wire" style="stroke-width:2" marker-end="url(#a)" d="M260 {cy+(c-cy)/8} C292 {cy+(c-cy)/8} 282 {c} 312 {c}"/>'
        g += f'<rect class="task" x="316" y="{c-24}" width="140" height="48" rx="6"/><text x="386" y="{c+6}" class="tname" style="font-size:17px;fill:#fff" text-anchor="middle">make {n}</text>'
        g += f'<path class="wire" style="stroke-width:2" marker-end="url(#a)" d="M456 {c} L492 {c}"/>'
        g += f'<rect class="res" x="496" y="{c-24}" width="146" height="48" rx="12" style="stroke-width:2"/><text x="508" y="{c+6}" class="name" style="font-size:16px">stock {n}</text><text x="632" y="{c+7}" class="num" style="font-size:19px" text-anchor="end">{OPEN[sk][0]}</text>'
    return g + f'<text x="290" y="{y0-12}" class="amt" style="font-size:18px" text-anchor="middle">−1</text><text x="474" y="{y0-10}" class="amt" style="font-size:18px" text-anchor="middle">+1</text>'
def edgetable(y0=296):
    g = "".join(f'<text x="{x}" y="{y0}" class="colh" style="font-size:17px" text-anchor="{a}">{h}</text>' for x, h, a in [(730, "task", "start"), (880, "resource", "start"), (1090, "amount", "end"), (1160, "delay", "end")])
    y = y0 + 34
    for n in N:
        for rname, amt in [("line capacity", "−1"), (f"stock {n}", "+1")]:
            g += f'<text x="730" y="{y}" class="cell" style="font-size:19px">make {n}</text><text x="880" y="{y}" class="cell" style="font-size:19px">{rname}</text><text x="1090" y="{y}" class="cell" style="font-size:19px;font-weight:700;fill:#b45309" text-anchor="end">{amt}</text><text x="1160" y="{y}" class="cell" style="font-size:19px" text-anchor="end">0</text>'
            y += 38
    return g
def grid(x, y):
    cols = [x + 300, x + 372, x + 444]; xs0 = x + 210
    g = f'<text x="{(cols[0]+cols[2])/2}" y="{y-44}" text-anchor="middle" style="font-size:16px;fill:#b45309;font-weight:700">× runs of each make task (unknown)</text>'
    g += f'<text x="{xs0}" y="{y-14}" text-anchor="end" class="colh" style="font-size:16px">start</text><text x="{x+520}" y="{y-14}" class="colh" style="font-size:16px">level</text>'
    g += "".join(f'<text x="{c}" y="{y-14}" text-anchor="middle" class="colh" style="font-size:18px;fill:#b45309">{xs(n)}</text>' for c, n in zip(cols, N))
    rows = [("line capacity", "375", ["−1", "−1", "−1"]), ("stock 9304", "10", ["+1", "", ""]), ("stock 4418", "25", ["", "+1", ""]), ("stock 6416", "15", ["", "", "+1"])]
    g += f'<path d="M{cols[0]-34} {y} h-8 v{46*4} h8 M{cols[2]+34} {y} h8 v{46*4} h-8" fill="none" stroke="#111827" stroke-width="2"/>'
    for i, (lab, st, ent) in enumerate(rows):
        yy = y + 46 * i + 31
        g += f'<text x="{x}" y="{yy}" style="font-size:19px;font-weight:600;fill:#111827">{lab}</text><text x="{xs0}" y="{yy}" text-anchor="end" class="cell" style="font-size:22px">{st}</text>'
        g += "".join(f'<text x="{c}" y="{yy}" text-anchor="middle" class="cell" style="font-size:22px;font-weight:700">{e}</text>' for c, e in zip(cols, ent))
        g += f'<text x="{x+520}" y="{yy}" class="cell" style="font-size:22px">≥ 0</text>'
    return g
MF = "font-family:Times,serif;font-style:italic"
def v(base, sub=""):
    """A maths identifier with an optional subscript."""
    t = f'<tspan style="{MF}">{base}</tspan>'
    return t + (f'<tspan dy="7" dx="1" style="{MF};font-size:19px">{sub}</tspan><tspan dy="-7" style="font-size:12px"> </tspan>' if sub else "")
def meq(x, y, t, fs=30): return f'<text x="{x}" y="{y}" style="font-size:{fs}px;fill:#111827;font-family:Times,serif">{t}</text>'
def lp_panel():
    g = '<text x="110" y="628" class="tag">4 · THE LINEAR PROGRAM</text>'
    # left: from the RTN
    g += '<rect x="110" y="650" width="1040" height="292" rx="14" fill="#fff" stroke="#111827" stroke-width="2.5"/>'
    g += '<rect x="110" y="650" width="1040" height="44" rx="14" fill="#111827"/><rect x="110" y="680" width="1040" height="14" fill="#111827"/><text x="134" y="680" style="font-size:17px;font-weight:700;letter-spacing:2px;fill:#fff">FROM THE RTN · GENERATED FROM NODES AND EDGES</text>'
    rows = [(748, "Variables", f'{v("x", "k,t")} ≥ 0', "runs of make task k in week t", "one per task node"),
            (822, "Constraints", f'{v("capacity", "t")} = 375 − Σ{v("", "k")} {v("x", "k,t")} ≥ 0', "the line cannot overbuild", "one per resource node"),
            (882, "", f'{v("stock", "k,t")} = {v("stock", "k,t−1")} + {v("x", "k,t")} ≥ 0', "what is built is added to stock", "")]
    for y, lab, eq, mean, src in rows:
        g += f'<text x="134" y="{y}" style="font-size:22px;font-weight:700;fill:#111827">{lab}</text>' + meq(310, y, eq)
        g += f'<text x="760" y="{y-10 if src else y}" class="note" style="font-size:20px;fill:#111827">{mean}</text>' + (f'<text x="760" y="{y+16}" class="note" style="font-size:17px">{src}</text>' if src else "")
    g += '<line x1="134" y1="776" x2="1126" y2="776" stroke="#e5e7eb" stroke-width="2"/>'
    g += '<text x="134" y="924" class="note" style="font-size:17px">k = SKU, t = week. The 375 and every −1, +1 are read from the object’s tables.</text>'
    # right: fed in
    g += '<rect x="1180" y="650" width="630" height="292" rx="14" fill="#fff" stroke="#b45309" stroke-width="2.5"/>'
    g += '<rect x="1180" y="650" width="630" height="44" rx="14" fill="#b45309"/><rect x="1180" y="680" width="630" height="14" fill="#b45309"/><text x="1204" y="680" style="font-size:17px;font-weight:700;letter-spacing:2px;fill:#fff">FED IN · A PLANNING CHOICE</text>'
    g += '<text x="1204" y="738" style="font-size:22px;font-weight:700;fill:#111827">Objective</text>'
    g += lines(1204, 776, ["Keep every SKU as close to its stock target", "as the line allows, worst-off SKU first."], cls="st", dy=32).replace('class="st"', 'class="st" style="font-size:23px"')
    g += meq(1204, 868, f'minimise   Σ{v("", "t")} max{v("", "k")} {v("gap", "k,t")}')
    g += '<text x="1204" y="904" class="note" style="font-size:18px">gap = weeks SKU k is below its target in week t.</text>'
    g += '<text x="1204" y="928" class="note" style="font-size:18px">How the gap is measured is a setting, not part of the graph.</text>'
    return g
p4 = page(4, "From the object to a linear program",
 '<text x="110" y="168" class="st">One line (MTB carbon, 375 builds a week) and the three SKUs built on it: RW-9304, RW-4418, RW-6416. Week of 7 Sep 2026.</text>'
 + rule(204)
 + '<text x="110" y="250" class="tag">1 · THE GRAPH</text>' + frag() + arrow_big(662, 420)
 + '<text x="730" y="250" class="tag">2 · STORED AS A TABLE OF EDGES</text>' + edgetable() + arrow_big(1184, 420)
 + '<text x="1250" y="250" class="tag">3 · ONE EQUATION PER RESOURCE</text>' + grid(1250, 330)
 + f'<text x="1250" y="556" class="note" style="font-size:19px">Top row: 375 − {xs("9304")}− {xs("4418")}− {xs("6416")}≥ 0.</text><text x="1250" y="584" class="note" style="font-size:19px">Each ±1 is one row of the edge table.</text>'
 + lp_panel()
 + rule(968)
 + '<text x="110" y="1018" class="st">The left box is generated for every line by the same code. Changing the objective changes only the right box.</text>')

# ---------- 5: the objective and the check
RATE1 = {sk: BD["target_units"][sk][0] / BD["target_weeks"][sk] for sk in SKUS}       # bikes per week of target, week 1
D1 = {sk: BD["net"][sk][0] + BD["builds"][sk][0] - BD["net"][sk][1] for sk in SKUS}  # orders arriving in week 1
def gap_after(sk, build): return (BD["target_units"][sk][0] - (BD["net"][sk][0] - D1[sk] + build)) / RATE1[sk]
def position_chart():
    X = lambda w: 290 + (w + 28) / 44 * 630
    g = '<text x="110" y="262" class="tag">WHERE EACH SKU STANDS AGAINST ITS TARGET, IN WEEKS OF DEMAND</text>'
    top, bot = 300, 590
    g += f'<line x1="{X(0)}" y1="{top}" x2="{X(0)}" y2="{bot}" stroke="#111827" stroke-width="2"/><line x1="{X(15)}" y1="{top}" x2="{X(15)}" y2="{bot}" stroke="#b45309" stroke-width="3"/>'
    g += f'<text x="{X(0)}" y="{bot+26}" text-anchor="middle" style="font-size:18px;fill:#111827">0</text><text x="{X(15)}" y="{bot+26}" text-anchor="middle" style="font-size:18px;font-weight:700;fill:#b45309">target 15</text>'
    g += "".join(f'<text x="{X(w)}" y="{bot+26}" text-anchor="middle" style="font-size:18px;fill:#6b7280">{w}</text>' for w in (-20, -10))
    g += f'<text x="{X(-14)}" y="{bot+54}" text-anchor="middle" style="font-size:18px;fill:#6b7280">← orders we owe, weeks</text><text x="{X(8)}" y="{bot+54}" text-anchor="middle" style="font-size:18px;fill:#6b7280">stock, weeks →</text>'
    for r, sk in enumerate(SKUS):
        y = 318 + r * 92
        open_gap = (BD["target_units"][sk][0] - BD["net"][sk][0]) / RATE1[sk]; after = BD["short_weeks"][sk][0]
        g += f'<rect x="110" y="{y+3}" width="18" height="18" fill="{COL[sk]}"/><text x="138" y="{y+19}" style="font-size:21px;font-weight:600;fill:#111827">{sk}</text><text x="138" y="{y+54}" style="font-size:17px;fill:#6b7280">after week 1</text>'
        g += f'<rect x="{X(15-open_gap)}" y="{y}" width="{X(15)-X(15-open_gap)}" height="28" fill="{COL[sk]}" opacity="0.35"/><text x="{X(15-open_gap)+10}" y="{y+21}" style="font-size:18px;font-weight:700;fill:#111827">{open_gap:.1f} weeks short at opening</text>'
        g += f'<rect x="{X(15-after)}" y="{y+34}" width="{X(15)-X(15-after)}" height="28" fill="{COL[sk]}"/><text x="{X(15-after)+10}" y="{y+55}" style="font-size:18px;font-weight:700;fill:#fff">{after:.1f}</text>'
    return g
def check():
    plan = {sk: BD["builds"][sk][0] for sk in SKUS}
    opts = [(f"The plan: {plan['RW-9304']} / {plan['RW-4418']} / {plan['RW-6416']}", plan, True), ("All 375 to RW-9304", {"RW-9304": 375}, False), ("Equal thirds: 125 each", {sk: 125 for sk in SKUS}, False)]
    g = '<text x="110" y="712" class="tag">CHECK · THREE WAYS TO PLACE WEEK 1’S 375 BUILDS</text>'
    g += '<text x="920" y="744" text-anchor="end" style="font-size:17px;fill:#6b7280">largest gap after, weeks</text>'
    for i, (name, b, isplan) in enumerate(opts):
        y = 788 + i * 48; worst = max(gap_after(sk, b.get(sk, 0)) for sk in SKUS)
        if isplan: g += f'<rect x="100" y="{y-32}" width="842" height="46" rx="8" fill="#f3f4f6"/>'
        g += f'<text x="118" y="{y}" style="font-size:22px;font-weight:{700 if isplan else 400};fill:#111827">{name}</text><text x="920" y="{y}" text-anchor="end" class="cell" style="font-size:24px;font-weight:700;fill:{"#111827" if isplan else "#9ca3af"}">{worst:.1f}</text>'
    return g + '<text x="110" y="936" class="note">Moving any build between SKUs lengthens the longest bar.</text>'
def bars_sol():
    X = lambda i: 1180 + (i - 1) * 108
    g = '<text x="1010" y="290" class="tag">THE SOLUTION · RUNS PER WEEK, OF 375</text>'
    lx = 1010
    for sk in SKUS:
        g += f'<rect x="{lx}" y="312" width="16" height="16" fill="{COL[sk]}"/><text x="{lx+22}" y="327" style="font-size:17px;font-weight:600;fill:#111827">{sk}</text>'; lx += 112
    y0, hh = 640, 270
    for i in range(1, 7):
        top = y0
        for sk in SKUS:
            v = BD["builds"][sk][i - 1]; h = v / 375 * hh; top -= h
            if v:
                g += f'<rect x="{X(i)-38}" y="{top}" width="76" height="{h-1.5}" fill="{COL[sk]}"/>'
                if h >= 22: g += f'<text x="{X(i)}" y="{top+h/2+7}" text-anchor="middle" style="font-size:19px;font-weight:700;fill:#fff">{v}</text>'
                else: g += f'<text x="{X(i)+46}" y="{top+h/2+6}" style="font-size:17px;font-weight:700;fill:{COL[sk]}">{v}</text>'
    g += f'<line x1="1110" y1="{y0}" x2="1810" y2="{y0}" stroke="#111827" stroke-width="2"/>'
    g += "".join(f'<text x="{X(i)}" y="{y0+30}" text-anchor="middle" style="font-size:19px;fill:#6b7280">{dlab(i)}</text>' for i in range(1, 7))
    g += '<text x="1010" y="730" class="tag">GAP AFTER EACH WEEK, WEEKS</text>'
    for r, sk in enumerate(SKUS):
        y = 772 + r * 44
        g += f'<rect x="1010" y="{y-16}" width="16" height="16" fill="{COL[sk]}"/><text x="1034" y="{y}" style="font-size:18px;font-weight:600;fill:#111827">{sk[3:]}</text>'
        g += "".join(f'<text x="{X(i)}" y="{y}" text-anchor="middle" class="cell" style="font-size:21px;">{BD["short_weeks"][sk][i-1]:.1f}</text>' for i in range(1, 7))
    return g + '<text x="1010" y="930" class="note">Level after one week, then kept level. All three on target 6 Sep 2027.</text>'
DUE1 = {"RW-9304": -146, "RW-4418": -123, "RW-6416": -56}   # due floor, week 1: object session, NOTE_TO_DECK_BOT.md §2 (not recomputed here)
NEED = [("#b91c1c", "overdue orders"), ("#f59e0b", "open orders, not yet due"), ("#9ca3af", "short of target stock")]
def fmt_date(iso): d = datetime.date.fromisoformat(iso[:10]); return f"{d.day} {d.strftime('%b %Y')}"
def col_floors(x):
    X = lambda b: x + 40 + (b + 1500) / 2400 * 620
    g = f'<text x="{x}" y="262" class="tag">1 · STATE · NET INVENTORY (STOCK − OPEN ORDERS), BIKES</text>'
    lx = x
    for col, lab in NEED:
        g += f'<rect x="{lx}" y="286" width="16" height="16" fill="{col}"/><text x="{lx+24}" y="301" style="font-size:17px;fill:#6b7280">{lab}</text>'; lx += 46 + len(lab) * 9.2
    g += f'<line x1="{X(0)}" y1="330" x2="{X(0)}" y2="700" stroke="#111827" stroke-width="2"/><text x="{X(0)}" y="726" text-anchor="middle" style="font-size:17px;fill:#111827">0 · nobody waiting</text>'
    for r, sk in enumerate(SKUS):
        y = 392 + r * 112; start = BD["net"][sk][0]; due = DUE1[sk]; tg = BD["target_units"][sk][0]
        g += f'<rect x="{x}" y="{y-40}" width="18" height="18" fill="{COL[sk]}"/><text x="{x+28}" y="{y-24}" style="font-size:21px;font-weight:700;fill:#111827">{sk}</text><text x="{x+140}" y="{y-24}" class="note" style="font-size:19px">starts at {start:,.0f}</text>'
        for (a_, b_), (col, _) in zip([(start, due), (due, 0), (0, tg)], NEED):
            w = X(b_) - X(a_); n = b_ - a_
            g += f'<rect x="{X(a_)}" y="{y}" width="{w-2}" height="38" fill="{col}"/>'
            if w > 70: g += f'<text x="{X(a_)+w/2}" y="{y+26}" text-anchor="middle" style="font-size:19px;font-weight:700;fill:{"#111827" if col != "#b91c1c" else "#fff"}">{n:,.0f}</text>'
            else: g += f'<text x="{X(b_)-6}" y="{y-8}" text-anchor="end" style="font-size:16px;font-weight:700;fill:#b45309">{n:,.0f}</text>'
        g += f'<text x="{X(tg)+8}" y="{y+26}" style="font-size:17px;fill:#6b7280">target</text>'
    return g
def col_order(x):
    g = f'<text x="{x}" y="262" class="tag">2 · PRIORITY ORDER · TODAY</text>'
    g += f'<rect x="{x}" y="290" width="350" height="150" rx="14" fill="#fff" stroke="#b45309" stroke-width="2.5"/><text x="{x+22}" y="330" style="font-size:16px;font-weight:700;letter-spacing:2px;fill:#b45309">STEP 1 OF 1</text>'
    g += f'<text x="{x+22}" y="372" style="font-size:28px;font-weight:700;fill:#111827">Target</text><text x="{x+22}" y="412" style="font-size:22px;fill:#111827">all three bikes · shared evenly</text>'
    g += lines(x, 486, ['<tspan class="b" fill="#111827">Shared evenly:</tspan> every bike on', "the line is the same number of", "weeks short of its target."], cls="note", dy=30)
    g += lines(x, 600, ['<tspan class="b" fill="#111827">Customers come first anyway:</tspan>', "a bike with orders waiting is", "always further below target", "than one without."], cls="note", dy=30)
    return g
def tile(x, w, big, small): return f'<rect x="{x}" y="800" width="{w}" height="120" rx="14" fill="#f3f4f6"/><text x="{x+26}" y="852" style="font-size:36px;font-weight:700;fill:#111827">{big}</text><text x="{x+26}" y="892" class="note" style="font-size:21px;fill:#111827">{small}</text>'
def col_decision(x):
    X = lambda i: x + 46 + (i - 1) * 84
    g = f'<text x="{x}" y="262" class="tag">3 · DECISION · RUNS PER WEEK, OF 375</text>'
    y0, hh = 700, 390
    for i in range(1, 7):
        top = y0
        for sk in SKUS:
            val = BD["builds"][sk][i - 1]; h = val / 375 * hh; top -= h
            g += f'<rect x="{X(i)-34}" y="{top}" width="68" height="{h-1.5}" fill="{COL[sk]}"/>'
            if h >= 24: g += f'<text x="{X(i)}" y="{top+h/2+7}" text-anchor="middle" style="font-size:19px;font-weight:700;fill:#fff">{val}</text>'
    g += f'<line x1="{x}" y1="{y0}" x2="{x+510}" y2="{y0}" stroke="#111827" stroke-width="2"/>'
    return g + "".join(f'<text x="{X(i)}" y="{y0+26}" text-anchor="middle" style="font-size:17px;fill:#6b7280">{dlab(i)}</text>' for i in range(1, 7))
def burn_down():
    x0, x1, yb, yt, TMAX = 200, 1070, 700, 300, 56
    X = lambda t: x0 + t / TMAX * (x1 - x0); Y = lambda u: yb - u / 6000 * (yb - yt)
    series = {sk: [BD["target_units"][sk][0] - BD["net"][sk][0]] + BD["short_units"][sk][:TMAX] for sk in SKUS}
    g = '<text x="110" y="262" class="tag">BIKES BELOW TARGET ON THE LINE · ALL THREE, STACKED</text>'
    for u in (0, 2000, 4000, 6000):
        g += f'<line x1="{x0}" y1="{Y(u)}" x2="{x1}" y2="{Y(u)}" stroke="{"#111827" if u == 0 else "#e5e7eb"}" stroke-width="{2 if u == 0 else 1.5}"/><text x="{x0-12}" y="{Y(u)+6}" text-anchor="end" style="font-size:18px;fill:#6b7280">{u:,}</text>'
    base = [0.0] * (TMAX + 1)
    for sk in SKUS:
        top = [base[t] + series[sk][t] for t in range(TMAX + 1)]
        pts = " ".join(f"{X(t):.1f},{Y(top[t]):.1f}" for t in range(TMAX + 1)) + " " + " ".join(f"{X(t):.1f},{Y(base[t]):.1f}" for t in range(TMAX, -1, -1))
        g += f'<polygon points="{pts}" fill="{COL[sk]}"/>'
        g += f'<text x="{X(0)+14}" y="{Y(base[3]+0.3*(top[3]-base[3]))+7}" style="font-size:19px;font-weight:700;fill:#fff">{sk}</text>'
        base = top
    total0 = sum(series[sk][0] for sk in SKUS)
    g += f'<text x="{X(0)+60}" y="{Y(total0)+4}" style="font-size:24px;font-weight:700;fill:#111827">← {total0:,.0f} at opening</text>'
    wk_of = {v: int(k) for k, v in BD["weeks"].items()}
    tc = wk_of[list(BD["orders_cleared"].values())[0]]; tt = BD["on_target_week"]
    for t, l1, l2, anchor in [(tc, fmt_date(BD["weeks"][str(tc)]), "open orders cleared, all three bikes", "start"), (tt, fmt_date(BD["weeks"][str(tt)]), "all three bikes at target", "end")]:
        g += f'<line x1="{X(t)}" y1="{yt+60}" x2="{X(t)}" y2="{yb}" stroke="#111827" stroke-width="2" stroke-dasharray="5 6"/><circle cx="{X(t)}" cy="{yb}" r="7" fill="#111827"/>'
        dx = 12 if anchor == "start" else -12
        g += f'<text x="{X(t)+dx}" y="{yt+82}" text-anchor="{anchor}" style="font-size:22px;font-weight:700;fill:#111827">{l1}</text><text x="{X(t)+dx}" y="{yt+110}" text-anchor="{anchor}" style="font-size:19px;fill:#111827">{l2}</text>'
    g += f'<text x="{X(34)}" y="{Y(3550)}" text-anchor="middle" style="font-size:19px;fill:#6b7280">the line builds 375 of 375 every week until then</text>'
    for t in (1, 14, 27, 40, 53):
        d = datetime.date.fromisoformat(BD["weeks"][str(t)]); g += f'<text x="{X(t)}" y="{yb+28}" text-anchor="middle" style="font-size:18px;fill:#6b7280">{d.strftime("%b %Y")}</text>'
    return g
def split_bars():
    X = lambda i: 1230 + (i - 1) * 100
    g = '<text x="1180" y="262" class="tag">THE SPLIT OF THE 375 · FIRST SIX WEEKS</text>'
    y0, hh = 700, 390
    for i in range(1, 7):
        top = y0
        for sk in SKUS:
            val = BD["builds"][sk][i - 1]; h = val / 375 * hh; top -= h
            g += f'<rect x="{X(i)-38}" y="{top}" width="76" height="{h-1.5}" fill="{COL[sk]}"/>'
            if h >= 24: g += f'<text x="{X(i)}" y="{top+h/2+7}" text-anchor="middle" style="font-size:19px;font-weight:700;fill:#fff">{val}</text>'
    g += f'<line x1="1180" y1="{y0}" x2="1810" y2="{y0}" stroke="#111827" stroke-width="2"/>'
    return g + "".join(f'<text x="{X(i)}" y="{y0+28}" text-anchor="middle" style="font-size:18px;fill:#6b7280">{dlab(i)}</text>' for i in range(1, 7))
def beat(x, n, head, l1, l2):
    return (f'<text x="{x}" y="806" style="font-size:25px;font-weight:700;fill:#111827">{n}. {head}</text>'
            + f'<text x="{x}" y="846" class="note" style="font-size:21px;fill:#111827">{l1}</text><text x="{x}" y="876" class="note" style="font-size:21px;fill:#111827">{l2}</text>')
p5 = page(5, "The line is the limit, so the plan decides who waits",
 '<text x="110" y="168" class="st">The base plan for the MTB carbon line and its three bikes, from 7 Sep 2026.</text>'
 + rule(204) + burn_down() + '<line x1="1130" y1="232" x2="1130" y2="740" stroke="#e5e7eb" stroke-width="2"/>' + split_bars() + rule(760)
 + beat(110, 1, "The line cannot keep up.", "It builds 375 a week against 5,657 needed, with", "new orders arriving. It runs full for a year.")
 + beat(680, 2, "So the only decision is the split.", "Week 1 leans to RW-9304, the furthest behind.", "After that the split holds steady.")
 + beat(1250, 3, "Today’s rule: share the wait equally.", "All three bikes clear their open orders on the", "same day, and reach target on the same day.")
 + rule(920)
 + '<text x="110" y="976" class="st">Change the rule and who waits changes. That rule is the priority order, on the next slide.</text>')

# ---------- 6: a different priority order
CX_, CY_ = "#111827", "#b45309"
def orow(y, name, tag, steps, bx, by, out):
    g = f'<text x="110" y="{y-34}" style="font-size:26px;font-weight:700;fill:#111827">{name}</text>' + (f'<text x="110" y="{y-70}" style="font-size:16px;font-weight:700;letter-spacing:2px;fill:#b91c1c">{tag}</text>' if tag else "")
    g += lines(110, y + 4, steps, cls="cell", dy=32).replace('class="cell"', 'class="cell" style="font-size:20px"')
    for i in range(4):
        x = 760 + i * 104; top = y + 50
        for val, col in ((by[i], CY_), (bx[i], CX_)):
            h = val * 11
            if val:
                top -= h
                g += f'<rect x="{x-36}" y="{top}" width="72" height="{h-1.5}" fill="{col}"/><text x="{x}" y="{top+h/2+7}" text-anchor="middle" style="font-size:18px;font-weight:700;fill:#fff">{val}</text>'
        g += f'<text x="{x}" y="{y+76}" text-anchor="middle" style="font-size:16px;fill:#6b7280">week {i+1}</text>'
    g += f'<line x1="712" y1="{y+50}" x2="1120" y2="{y+50}" stroke="#111827" stroke-width="2"/>'
    return g + lines(1220, y - 20, out, cls="st", dy=36).replace('class="st"', 'class="st" style="font-size:24px"') + rule(y + 104)
p6 = page(6, "A different priority order, the same object and solver",
 '<text x="110" y="168" class="st">A small example. Bikes X and Y share a line that builds 10 a week. X has 10 customers waiting, Y has none. Each should hold 20 in stock.</text>'
 + rule(204)
 + "".join(f'<text x="{x}" y="250" class="tag">{h}</text>' for x, h in [(110, "PRIORITY ORDER"), (712, "BUILDS PER WEEK"), (1220, "WHAT HAPPENS")])
 + f'<rect x="960" y="234" width="16" height="16" fill="{CX_}"/><text x="982" y="249" style="font-size:17px;font-weight:600;fill:#111827">X</text><rect x="1020" y="234" width="16" height="16" fill="{CY_}"/><text x="1042" y="249" style="font-size:17px;font-weight:600;fill:#111827">Y</text>'
 + orow(370, "Today’s rule", "", ["1. target · both bikes · shared evenly"], [10, 5, 5, 5], [0, 5, 5, 5],
        ["X’s customers are served in week 1.", "Then both build stock together."])
 + orow(590, "Rank the bikes: Y first", "THE TRAP", ["1. target · Y", "2. target · X"], [0, 0, 10, 10], [10, 10, 0, 0],
        ["Y fills its stock first.", "X’s customers wait until week 3."])
 + orow(810, "Customers, then Y first", "", ["1. owed   · both bikes · shared evenly", "2. target · Y", "3. target · X"], [10, 0, 0, 10], [0, 10, 10, 0],
        ["X’s customers are served in week 1.", "Then Y gets its stock before X."])
 + '<text x="110" y="966" class="st">A priority has two parts: which need comes first, then which bike. “Owed” is the floor at zero: nobody waiting.</text>'
 + '<text x="110" y="1010" class="note">Each row is a test of the solver. On Redwheel, today’s rule written as a one-step priority order gives the same plan, cell for cell.</text>')
pages = [p1, p2, p3, p4, p5, p6]
head = f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>'
(out / "object.html").write_text(head + "".join(pages) + "</body></html>")
for i, p in enumerate(pages, 1): (out / f"p{i}.html").write_text(head + p + "</body></html>")
