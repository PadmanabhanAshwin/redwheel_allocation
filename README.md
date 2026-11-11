# Redwheel build planner

Master data → allocation engine → planner UI for Redwheel's weekly build plan (Sep 2026 – Dec 2028).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Run

```bash
python src/main.py             # run the pipeline (or cell by cell in VS Code)
pytest                        # closure checks against independently derived figures
streamlit run app/app.py      # planner UI
```

## Layout

| Path | What |
|---|---|
| `data/` | The nine CSVs exactly as Redwheel shared them (never edited) |
| `src/main.py` | The pipeline as `# %%` cells, calling the modules below |
| `src/redwheel/` | `config` · `utils` (helpers) · `read` (one reader per file) · `aux_fns` (business logic) |
| `app/` | Streamlit UI |
| `docs/` | Assumptions and data-quality log |
| `scripts/explore/` | Original profiling scripts (reference only) |
| `outputs/` | Generated tables (git-ignored) |

Dependencies: one `requirements.txt`, direct dependencies pinned.

---

# The object

How Redwheel's supply chain is represented. Everything downstream (build plan, what-ifs, the UI)
reads this one object. It follows the Resource–Task Network (Pantelides, 1994).

**Status:** the definition below was run as a prototype on the real data and passes every check
in [Checks](#checks). The object code in `src/redwheel/` is the next step; the checks become tests.

## Definition

There are two kinds of node and nothing else.

**Resource** — something with a quantity each week. Identified by three things:

```
(kind, item, location)        kind = inventory | capacity | order
```

`item` is the SKU (blank for capacity). The quantity is called its **level**.

**Task** — an activity that runs some number of times in a week. A task has **arrows** to
resources. Each arrow has an **amount** (what one run adds to or removes from that resource) and a
**delay** in weeks (how long after the run that happens).

**Location** is not a node. It has no quantity and nobody decides it. It is part of what
identifies a resource, and it has a **class**. The class decides which kinds of resource can
exist there.

| Location class | Can hold | Stock is ours |
|---|---|---|
| factory | inventory | yes |
| production line (belongs to a factory) | capacity | – |
| distribution center | inventory | yes |
| in-transit (one per transfer route) | inventory | yes |
| customer | orders | – |
| dealer | orders and its own inventory | no |

Not needed for Redwheel, same mechanism when they are: **supplier** (holds supplier capacity),
**port / cross-dock** (holds inventory passing through).

### The three tasks

| Task | Arrows (amount, delay) |
|---|---|
| **make** | line capacity −1 now · factory inventory +1 now |
| **move** | origin inventory −1 now · in-transit inventory +1 now · in-transit inventory −1 after the transit time · destination inventory +1 after the transit time |
| **fulfil** | site inventory −1 now · customer order −1 now |

Demand is not a task. It arrives from outside: each week's forecast is added to the order resources.

### The one equation

The same rule for every resource, every week:

```
level[r, t] = carry[r] · level[r, t−1]
            + Σ over arrows into r:  amount · runs[task, t − delay]
            + arrival[r, t]
```

- `carry` is 1 for inventory and orders (what is left carries into next week) and 0 for capacity
  (unused capacity is lost).
- `arrival` is what comes from outside: forecast for order resources, weekly capacity for
  capacity resources, zero for inventory.
- Every level must stay ≥ 0. For capacity that means a line cannot build more than it has. For
  inventory, a site cannot ship what it does not hold. For orders, we cannot ship more than was ordered.

Weeks are numbered 1 to 121, starting 2026-09-07. A level is the quantity at the end of the week.
The opening level (week 0) is the snapshot of 2026-09-07.

### Net position

The number the targets are set on. Per SKU:

```
net position = our inventory at every location that is ours (factory + DC + in-transit)
             − orders at every customer and dealer
```

Shipping a bike lowers inventory and orders by one each, so it does not change the net position.
Moving a bike does not change it either. That leaves

```
net position[t] = net position[t−1] + built[t] − forecast[t]
```

which is the simple balance the build plan needs. The full object reduces to it exactly (check 3).

Targets and priorities (weeks of supply, clearing backlog first) are **not** part of the object.
They are rules written on top of the levels, kept in their own table.

## Redwheel as this object

| | Count | What |
|---|---|---|
| Locations | 10 | RENO (factory) · 4 production lines under RENO · CMH (distribution center) · RENO>CMH (in-transit) · WEB, COMMERCIAL (customers) · DEALERS (dealer) |
| Resources | 74 | 40 inventory (10 SKUs × RENO, CMH, RENO>CMH, DEALERS) · 30 order (10 SKUs × WEB, DEALERS, COMMERCIAL) · 4 capacity (one per line) |
| Tasks | 80 | 10 make · 10 move · 60 fulfil (10 SKUs × 2 sites × 3 customers) |
| Arrows | 180 | make 20 · move 40 · fulfil 120 |

Opening levels (2026-09-07):

| | Units |
|---|---|
| Inventory at RENO | 1,965 |
| Inventory at CMH | 1,035 |
| Inventory in transit | 0 |
| Orders (backlog) | 5,991 — WEB 2,139 · DEALERS 2,914 · COMMERCIAL 938 |
| **Net position, all SKUs** | **−2,991** |
| Dealer inventory (not ours, not in the net position) | 2,000 |

Dealer inventory is in the object with its opening level and no arrows. The data has no dealer
sell-through, so nothing moves it. With that data it connects without changing anything else.

## How the object is built

1. **Master tables** — the nine CSVs cleaned into one schema (`src/main.py`, steps 1.1–1.5).
2. **Locations** — ten rows, each with a class and, for a line, its factory.
3. **Resources** — generated, not typed. Every SKU × every location that can hold inventory; every
   SKU × every location that can hold orders; one capacity resource per production line.
4. **Tasks and arrows** — generated from two short lists:
   - what is built where: each SKU → its line → RENO (10 rows)
   - what can go where: RENO → CMH in 1 week; RENO and CMH → each of the 3 customers (7 rows)
5. **Numbers** — opening level per resource (plant snapshot, backlog, dealer report) and arrivals
   per week (forecast, capacity).
6. **Run the equation and the checks.**

To change which site serves which channel, edit the list in step 4. Nothing else changes.

## What comes from the files and what is assumed

| | Source |
|---|---|
| 10 SKUs with class, trim, size | Fact — order files; the three channels agree on every SKU |
| 4 production lines and weekly capacity | Fact — `capacity_plan.csv`, one line per class × trim |
| Which SKU is built on which line | Fact — SKU class and trim match exactly one line |
| Two stock sites, RENO and CMH | Fact — `plant_inventory_snapshot.csv` |
| All four lines are at RENO | Assumption — the capacity file has no location; RENO is the only site named a plant |
| A RENO → CMH transfer takes 1 week, no limit on volume | Assumption — no transfer data |
| Either site can serve any channel | Assumption — no order file says where it ships from |
| A bike built in a week can ship that week | Assumption — no build lead time given |
| Demand that cannot be met waits; it never cancels | Assumption — consistent with the brief's backlog wording |
| Dealer inventory is not ours and is not netted | Assumption — it is stock already sold to dealers |

## Checks

Run on the real data, over all 121 weeks, with eight different plans: random build levels, no
builds at all, no transfers, and everything transferred.

| # | Check | Result |
|---|---|---|
| 1 | No level goes below zero | holds in all eight |
| 2 | Opening net position per SKU equals on-hand − backlog counted straight from the raw files | exact, all 10 SKUs |
| 3 | Net position read from the object equals opening + built − forecast, every SKU, every week | difference 0 in all eight |
| 4 | Bikes are conserved: change in our inventory = built − shipped, every SKU, every week | difference 0 in all eight |
| 5 | Dealer inventory never changes | holds in all eight |

Check 3 fails if in-transit stock is not a resource: a bike on a truck is then at neither site and
drops out of the net position. With transfers running the error was 385 to 1,283 bikes. That is
why in-transit is a location and move has four arrows.

## What a change to the plan edits

| A planner says | What changes |
|---|---|
| A line is down for two weeks | that line's capacity arrival in those weeks |
| Forecast is up 20%; a big order just landed | arrivals at the order resources |
| Lock the first four weeks; build 100 of X in week 5 | those task runs are fixed |
| CMH stops serving commercial | those fulfil tasks are removed |
| Transfers now take two weeks | the delay on the move arrows |
| The stock count was wrong | opening level |
| Target goes from 15 to 12 weeks | the rule table, not the object |

One edit, re-run, compare with the previous run.

## What it does not cover

- **Individual orders.** Orders are grouped per SKU × customer group, so it cannot promise a date
  for one specific PO.
- **Whole bikes and batch sizes.** Quantities are continuous; builds are rounded afterwards.
- **Uncertainty.** The forecast is one number per week.
