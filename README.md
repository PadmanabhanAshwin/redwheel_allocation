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
pytest                         # master data, the object, and the equation
streamlit run app/app.py      # planner UI
```

## Layout

| Path | What |
|---|---|
| `data/` | The nine CSVs exactly as Redwheel shared them (never edited) |
| `src/main.py` | The pipeline as `# %%` cells, calling the modules below |
| `src/redwheel/` | `config` · `utils` (helpers) · `read` (one reader per file) · `aux_fns` (Redwheel logic) · `rtn` (the generic object) |
| `tests/` | `test_rtn` (generic object, by hand) · `test_master` · `test_object` (Redwheel as the object) |
| `app/` | Streamlit UI: `app.py` (navigation) · `ui.py` (shared data and styling) · `views/` (one file per page) |
| `docs/` | Assumptions and data-quality log |
| `scripts/explore/` | Original profiling scripts (reference only) |
| `outputs/` | Generated tables (git-ignored) |

Dependencies: one `requirements.txt`, direct dependencies pinned.

---

# The object

How Redwheel's supply chain is represented. Everything downstream (build plan, what-ifs, the UI)
reads this one object. It follows the Resource–Task Network (Pantelides, 1994).

**Status:** built and tested. Generic code in `src/redwheel/rtn.py`, Redwheel's mapping in
`aux_fns.build_object`, step by step in `src/main.py` cells 2.1–2.5. Every number below is checked
by a test.

## Where everything goes

| | Place | Holds | Code |
|---|---|---|---|
| 1 | **Master data** | the cleaned files, and the description tables: item, location, week | `read`, `aux_fns` (steps 1.1–1.5) |
| 2 | **Setup lists** | how Redwheel is wired: what is built where, what can go where | `aux_fns.build_routing`, `build_routes` |
| 3 | **Object** | resources, tasks, arrows, and the numbers on them | `rtn` (generic) |
| 4 | **Planning priors** | targets, priorities, restrictions | next step |
| 5 | **Engine** | the equation, the solver, the explanations | `rtn.levels` now; solver later |

The test for whether something belongs in the object or in the priors: *would it still be true if
management changed its mind?* If yes, it is physical and goes in the object (the line exists, the
truck takes a week, capacity is 375). If no, it is a choice and goes in the priors (15 weeks of
supply, Columbus serves the east, keep a safety stock).

## Definition

There are two kinds of node and nothing else.

**Resource** — something with a quantity each week, called its **level**. Identified by

```
(kind, item, location)        kind = inventory | capacity | order
```

`item` is the SKU, blank for capacity.

**Task** — an activity that runs some number of times in a week. Identified by a name and a kind
(make, move, fulfil). A task is defined entirely by its **arrows**. Where a task goes from and to
is read off its arrows; it is not a property of the task.

**Arrow** — connects a task to a resource. It has an **amount** (what one run adds to or removes
from the resource) and a **delay** (how many weeks after the run that happens).

### Description tables

Item, location and week are not nodes. They have no quantity and nobody decides them. They
describe resources and tasks, and live in master data as `dim_sku`, `dim_location`, `dim_week`.
The equation never reads them. They are used to generate resources and tasks, to pick a group of
resources for a prior ("all our inventory of carbon MTB"), and for reporting.

### The equation

The same rule for every resource, every week:

```
level[r, t] = carry[r] · level[r, t−1]
            + Σ over arrows into r:  amount · runs[task, t − delay]
            + arrival[r, t]
```

- `carry` is 1 for inventory and orders (what is left carries into next week) and 0 for capacity
  (unused capacity is lost).
- `arrival` is what comes from outside: forecast onto order resources, weekly capacity onto
  capacity resources, nothing onto inventory.
- Every level must stay ≥ 0. For capacity: a line cannot build more than it has. For inventory: a
  site cannot ship what it does not hold. For orders: we cannot ship more than was ordered.
- Weeks run 1 to 121 (2026-09-07 to 2028-12-25). Week 0 is the opening snapshot. A level is the
  quantity at the end of the week. A run whose arrow lands after week 121 has no effect inside the
  horizon; a transfer started in week 121 is still in transit at the end.

### Net position

The number the weeks-of-supply targets are set on. Per SKU:

```
net position = inventory at every location that is ours (RENO + CMH + RENO>CMH)
             − orders at every customer and dealer
```

Shipping a bike lowers inventory and orders by one each, so it does not change the net position.
Moving a bike does not change it either. What is left is

```
net position[t] = net position[t−1] + built[t] − forecast[t]
```

The full object reduces to this exactly, every SKU, every week (tested).

## Granularity

Each resource sits at the finest level all of its inputs share.

| Resource | Granularity | Set by |
|---|---|---|
| inventory | SKU × site × week | plant snapshot is per SKU per site |
| order | SKU × channel × week | forecast is per SKU per channel per week; no order says which site ships it |
| capacity | line × week | capacity file is per line per week |
| dealer inventory | SKU, all 45 dealers summed | forecast has no dealer split, so per-dealer stock has nothing to connect to |

## How Redwheel is built into it

Resources and tasks are generated, not typed by hand, using two conventions. The conventions are
generic (`rtn.py`); they are a way to build the object for a make-and-distribute supply chain,
not part of the object itself.

**Convention 1 — the class of a location decides which resources exist there.**

| Location class | Resources generated | Stock is ours |
|---|---|---|
| factory | inventory, per SKU | yes |
| production line (belongs to a factory) | capacity | – |
| distribution center | inventory, per SKU | yes |
| in-transit (one per transfer route) | inventory, per SKU | yes |
| customer | orders, per SKU | – |
| dealer | orders and its own inventory, per SKU | no |

**Convention 2 — three task templates.** A route to a location that holds orders is a fulfil;
any other route is a move.

| Task | Arrows (amount, delay) |
|---|---|
| **make** | line capacity −1 now · factory inventory +1 after the build time |
| **move** | origin inventory −1 now · in-transit inventory +1 now · in-transit inventory −1 after the transit time · destination inventory +1 after the transit time |
| **fulfil** | site inventory −1 now · customer order −1 after the delivery time |

**Steps** (cells in `src/main.py`)

| Cell | Step | Result |
|---|---|---|
| 1.1–1.5 | Master data: the nine files cleaned, plus `dim_location` | 10 SKUs, 4 lines, 10 locations, 121 plan weeks |
| 2.1 | Description tables for the object | items, locations, weeks |
| 2.2 | Resources from convention 1 | 74 |
| 2.3 | Tasks and arrows from convention 2 and two setup lists (below) | 80 tasks, 180 arrows |
| 2.4 | Opening levels and weekly arrivals; `validate` | object complete |
| 2.5 | Run the equation with no plan | opening net position matches step 1.5 |

The two setup lists:

- **What is built where** — 10 rows: each SKU → its line at RENO → RENO stock.
- **What can go where** — 7 rows: RENO → CMH (1 week); RENO → WEB, DEALERS, COMMERCIAL;
  CMH → WEB, DEALERS, COMMERCIAL (0 weeks).

The second list holds every route that is *physically possible*. Which routes to use is a
planning prior. Stopping CMH from serving commercial is a prior that sets those runs to zero, not
a deleted route.

## Redwheel as this object

| | Count | What |
|---|---|---|
| Locations | 10 | RENO (factory) · 4 production lines under RENO · CMH (distribution center) · RENO>CMH (in-transit) · WEB, COMMERCIAL (customers) · DEALERS (dealer) |
| Resources | 74 | 40 inventory (10 SKUs × RENO, CMH, RENO>CMH, DEALERS) · 30 order (10 SKUs × WEB, DEALERS, COMMERCIAL) · 4 capacity |
| Tasks | 80 | 10 make · 10 move · 60 fulfil (10 SKUs × 2 sites × 3 customers) |
| Arrows | 180 | make 20 · move 40 · fulfil 120 |

Lines and the SKUs that share them: road-base (RW-7298, RW-9835) · road-carbon (RW-1378,
RW-2984, RW-3980) · mtb-base (RW-9324, RW-9901) · mtb-carbon (RW-4418, RW-6416, RW-9304).

Opening levels (2026-09-07) and arrivals over the 121 weeks:

| | Units |
|---|---|
| Inventory at RENO | 1,965 |
| Inventory at CMH | 1,035 |
| Inventory in transit | 0 |
| Orders (backlog) | 5,991 — WEB 2,139 · DEALERS 2,914 · COMMERCIAL 938 |
| **Net position, all SKUs** | **−2,991** |
| Dealer inventory (not ours, not in the net position) | 2,000 |
| Forecast arriving, weeks 1–121 | 79,622 |
| Capacity arriving, weeks 1–121 | 123,150 |

Dealer inventory is in the object with its opening level and no arrows. The data has no dealer
sell-through, so nothing moves it. With that data it connects without changing anything else.

## Planning priors

Defined here; built in the next step.

The object has two kinds of number: levels (on resources) and runs (on tasks). A prior is a
statement about a level, a run, or a sum of them (like net position), in one of six forms:

| Form | On a level | On a run |
|---|---|---|
| **min** | safety stock | minimum build |
| **max** | storage limit | route not used (max 0) |
| **target** | weeks of supply | – |
| **cost** | orders left waiting; stock above target | prefer one route over another |
| **multiple** | – | fixed order quantity, lot size |
| **fixed** | – | frozen weeks, a planner's manual build |

One row per prior:

| Column | Meaning | Example |
|---|---|---|
| applies to | level, run, or net position | net position |
| selection | filter on the description tables | product group = road |
| form | one of the six | target |
| value, unit | units, or weeks of forward forecast | 10 weeks |
| from, to | the weeks it applies | 2028-01-03 onward |
| strength | hard, or soft | soft |
| source | brief, assumption, or planner | brief |

A prior is stored once with a date range, not as a value per week. A planner change is a new row
on top, not an edit: "road carbon target 12 weeks for June 2027, source = planner". For any
week the most specific row applies, and the base row stays, so every change can be seen,
compared and undone.

Links between SKUs (substitutes, families) are description data, next to the item table, that
priors and tasks can use. Redwheel has none.

Redwheel's priors:

| Prior | Form | Source |
|---|---|---|
| road, 8 weeks; 10 weeks from 2028-01-03 | target on net position | brief (2028 start date assumed) |
| mtb base, 12 weeks | target on net position | brief |
| mtb carbon, 15 weeks | target on net position | brief |
| orders left waiting | cost, highest | assumption |
| stock above target | cost, small | assumption |
| moving RENO → CMH | cost, small | assumption |

## What is general and what is Redwheel

| Layer | What | Changes for another company |
|---|---|---|
| Object | resource, task, arrow, the equation (`rtn.py`) | never |
| Conventions | location classes, task templates (`rtn.py`) | a row when a new kind of place or activity appears |
| Redwheel | locations, setup lists, numbers, priors, assumptions (`aux_fns.py`, `config.py`) | all of it |

The same object, with more rows in the conventions, also represents: components (one more arrow
on make), suppliers (a buy task), more sites, route capacity (one more arrow on move), a SKU
built on two lines, ports and cross-docks. Redwheel has none of these, so none are tested.

## What comes from the files and what is assumed

| | Source |
|---|---|
| 10 SKUs with class, trim, size | Fact — order files; the three channels agree on every SKU |
| 4 production lines and weekly capacity | Fact — `capacity_plan.csv`, one line per class × trim |
| Which SKU is built on which line | Fact — SKU class and trim match exactly one line |
| Two stock sites, RENO and CMH | Fact — `plant_inventory_snapshot.csv` |
| All four lines are at RENO | Assumption — the capacity file has no location; RENO is the only site named a plant |
| A RENO → CMH transfer takes 1 week, no limit on volume | Assumption — no transfer data |
| Nothing in transit on 2026-09-07 | Assumption — no transfer data |
| Either site can serve any channel | Assumption — no order file says where it ships from |
| A bike built in a week can ship that week | Assumption — no build lead time given |
| Demand that cannot be met waits; it never cancels | Assumption — consistent with the brief's backlog wording |
| Dealer inventory is not ours and is not netted | Assumption — it is stock already sold to dealers |
| Dealer stock counts (dated 09-02 to 09-07) are taken as of 2026-09-07 | Assumption |

`BUILD_WEEKS` and `TRANSFER_WEEKS` are in `config.py`. Changing one is a one-line edit; the
object and the tests follow it.

## Tests

58 tests, all passing (`pytest`).

| File | What it checks |
|---|---|
| `test_rtn.py` | The generic object on a tiny supply chain worked out by hand: every arrow, every level week by week, net position, a transfer still in transit at the end of the horizon, the graph view, and that `validate` rejects broken objects |
| `test_master.py` | Master data against figures recounted from the raw files without this codebase |
| `test_object.py` — structure | Location classes; resource counts per kind and location; each SKU made on its own line only; each line shared by exactly its SKUs; every move goes through transit; every customer can be served from both sites; every order is reachable from its line in the graph; only dealer stock is unconnected |
| `test_object.py` — numbers | Opening inventory row by row against the plant file; dealer stock; backlog per SKU and channel; forecast and capacity arrivals cell by cell; opening net position against the independent recount |
| `test_object.py` — equation | With no plan: stock stays, orders grow by the forecast, capacity resets. With four plans (random builds, all transferred, little built, no transfers): no level below zero, net position equals opening + built − forecast, bikes are conserved, transfers land after exactly the transfer time, dealer stock never changes |

The tests were checked by breaking the object on purpose, seven ways: transit stock released on
the wrong week, web and dealer channels swapped, orders not carrying over, in-transit not counted
as ours, builds landing at CMH, capacity carrying over, dealer stock counted as ours. A test
failed every time.

## What a change to the plan edits

| A planner says | What changes |
|---|---|
| A line is down for two weeks | that line's capacity arrival in those weeks (object) |
| Forecast is up 20%; a big order just landed | arrivals at the order resources (object) |
| The stock count was wrong | opening level (object) |
| Transfers now take two weeks | the delay on the move arrows (object) |
| Lock the first four weeks; build 100 of X in week 5 | a fixed prior on those runs |
| CMH stops serving commercial | a max-0 prior on those fulfil runs |
| Target goes from 15 to 12 weeks | a target prior |

One edit, re-run, compare with the previous run.

## Known limits

- **No basis in the data for site or channel decisions.** Nothing says which site should serve
  whom or which channel comes first. The build plan does not depend on it (net position does not
  change with shipping or moving), but per-site and per-channel numbers need a prior from Redwheel.
- **Orders are grouped per SKU × channel.** The object cannot promise a date for one specific
  order, or serve oldest orders first.
- **Road SKUs have stock on hand roughly equal to their open orders, and those orders are not
  shipping.** The data does not say why. The object would ship them in week 1.
- **Quantities are continuous.** Builds are rounded to whole bikes afterwards.
- **One forecast number per week.** No range.
