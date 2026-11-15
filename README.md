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
pytest                         # everything offline; live LLM tests: RUN_LLM_TESTS=1 pytest tests/test_llm_live.py
streamlit run planner3/app.py --theme.primaryColor=#1F2933 --client.toolbarMode=viewer   # the compact planner (deck's look), being built
streamlit run planner2/app.py  # the planner (scenario-first UI) — start here
streamlit run app/app.py       # first UI: report pages per scenario
streamlit run planner/app.py   # second UI: scenario workbench (kept for reference)
```

The LLM features (What-if "describe the change", "Ask about this plan", "Ask why they differ") use the Anthropic API
with credentials from the environment (`ANTHROPIC_API_KEY`) or an `ant auth login` profile. Everything else works
without them.

## Layout

| Path | What |
|---|---|
| `data/` | The nine CSVs exactly as Redwheel shared them (never edited) |
| `src/main.py` | The pipeline as `# %%` cells, calling the modules below |
| `src/redwheel/` | `config` · `utils` (helpers) · `read` (one reader per file) · `aux_fns` (Redwheel logic) · `rtn` (the generic object) · `changes` (edits to the object's numbers, generic) · `engine` (the LP) · `scenarios` · `priors` (the settings table and its validator) · `tunables` (every tunable, in one list, with its form) · `llm` (requests → checked edits; grounded answers) · `store` (saved scenarios) |
| `tests/` | One file per layer: the generic object by hand, master data, Redwheel as the object, the solver, scenarios and settings, the LLM loop, the UIs |
| `planner3/` | The compact planner, three views with one question each: Plan (built) · What-if · Model (next). `reading` (what the Plan view says, no Streamlit, tested against the engine) · `charts` · `theme` (the deck's palette and type) · `ask` (one Ask box). Same engine, scenarios and saved files as `planner2/` |
| `planner2/` | The planner: `home` · `scenario` · `whatif` · `compare` pages; `components` (settings in plain words, the settings editor), `charts`, `facts` (what the LLM may answer from), `state` (scenarios, drafts, cached runs) |
| `app/` | First UI: `app.py` (navigation) · `ui.py` (shared data and styling, also used by `planner2`) · `views/` (one file per page; four are reused as `planner2` reference pages) |
| `planner/` | Second UI (scenario workbench), kept unchanged |
| `docs/` | Assumptions and data-quality log |
| `scripts/explore/` | Original profiling scripts (reference only) |
| `outputs/` | Generated tables (git-ignored) |

Dependencies: one `requirements.txt`, direct dependencies pinned.

---

# The object

How Redwheel's supply chain is represented. Everything downstream (build plan, what-ifs, the UI)
reads this one object. It follows the Resource–Task Network (Pantelides, 1994).

**Status:** the object, Redwheel's planning priors, the solver and the checks are built and tested.
Generic code in `src/redwheel/rtn.py` and `engine.py`, Redwheel's mapping in
`aux_fns.build_object`, step by step in `src/main.py`. Parts marked **planned** are specified here
and not built yet.

## Where everything goes

| | Place | Holds | Code |
|---|---|---|---|
| 1 | **Master data** | the cleaned files, and the description tables: item, location, week | `read`, `aux_fns` (steps 1.1–1.5) |
| 2 | **Setup lists** | how Redwheel is wired: what is built where, what can go where | `aux_fns.build_routing`, `build_routes` |
| 3 | **Object** | resources, tasks, edges, and the numbers on them | `rtn` (generic) |
| 4 | **Changes** | edits to the object's numbers for one scenario: a line down, a forecast revised, a stock count corrected | `changes` (generic) |
| 5 | **Planning priors** | targets, routing, limits, what the plan decides | `priors`, `scenarios` |
| 6 | **Engine** | the equation, the solver, whole-bike rounding, the checks | `rtn.levels`, `engine`, `scenarios.checks` |

Two tests decide where something goes.

*Would it still be true if management changed its mind?* If yes, it is physical and belongs to the
object (the line exists, the truck takes a week, capacity is 375). If no, it is a choice and goes
in the priors (15 weeks of supply, Columbus serves the east, keep a safety stock).

*Is it the base data, or one scenario's version of the world?* The base object is built once from
the files. A scenario that says the world is different (a line is down in March, the forecast is
revised, transfers take two weeks) is a list of **changes** to the object's numbers. A scenario
that wants something different (another target, another routing rule) changes the **priors**.

The solver reads the object and the priors and nothing else. A scenario is therefore data, and
solving a new one needs no new solver code and no new Redwheel code.

## Definition

There are two kinds of node and nothing else.

**Resource** — something with a quantity each week, called its **level**. Identified by

```
(kind, item, location)        kind = inventory | capacity | order
```

`item` is the SKU, blank for capacity.

**Task** — an activity that runs some number of times in a week. Identified by a name and a kind
(make, move, fulfil). A task is defined entirely by its **edges**. Where a task goes from and to
is read off its edges; it is not a property of the task.

**Edge** — connects a task to a resource (`arrows` in the code). It has an **amount** (what one run adds to or removes
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
            + Σ over edges into r:  amount · runs[task, t − delay]
            + arrival[r, t]
```

- `carry` is 1 for inventory and orders (what is left carries into next week) and 0 for capacity
  (unused capacity is lost).
- `runs[task, t]` is what the plan decides, never below zero and never above the task's **run
  limit** that week, where it has one: `0 ≤ runs[task, t] ≤ run_max[task, t]`. A limit says how
  many times a task can run at most, e.g. no RW-4418 built while its frames are late. With no
  limit, only the levels bound a task (a build needs line capacity, a transfer needs stock).
- `arrival` is what comes from outside: forecast onto order resources, weekly capacity onto
  capacity resources, nothing onto inventory.
- Every level must stay ≥ 0. For capacity: a line cannot build more than it has. For inventory: a
  site cannot ship what it does not hold. For orders: we cannot ship more than was ordered.
- Weeks run 1 to 121 (2026-09-07 to 2028-12-25). Week 0 is the opening snapshot. A level is the
  quantity at the end of the week. A run whose edge lands after week 121 has no effect inside the
  horizon; a transfer started in week 121 is still in transit at the end.
- Arrivals are known past the plan: the forecast runs to week 156. Weeks 122–156 are the
  **outlook**. Nothing is decided there, but a weeks-of-supply target near the end of the plan
  reads them (the furthest any target reads is week 136). The object stores them next to the
  arrivals, as `outlook`, and only order resources have one: the capacity file stops at week 121.

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

## Every number in the object

The object holds six kinds of number and nothing else: five the equation reads, and the run
limit, which bounds what the plan may decide. This is the complete list of what a scenario can say
is different about the world.

| Number | Sits on | Weeks | Redwheel's base value | A change may |
|---|---|---|---|---|
| **opening** | resource | 0 | plant snapshot; open orders | set, add or scale |
| **arrival** | resource | 1–156 for orders, 1–121 for capacity | forecast onto orders; weekly capacity onto lines | set, add or scale, over a date range |
| **carry** | resource | – | 1 for inventory and orders, 0 for capacity | nothing: fixed by the kind of resource |
| **amount** | edge | – | one unit of line capacity and one bike per build; one bike per move or shipment | not yet |
| **delay** | edge | – | build 0 weeks, transfer 1 week, delivery 0 weeks | build time per line and transfer time, through the settings table |
| **run limit** | task | 1–121 | none (any task may run as often as the levels allow) | set, over a date range: the most a task can run each week |

What the plan decides is `runs[task, week]` for weeks 1–121, never below zero and never above its
run limit. A task the plan does not decide has runs of zero; a run limit on one is refused, since
it would change nothing. What follows from the equation is `level[resource, week]`,
never below zero.

Shipping is not decided today: fulfil runs are zero in the solver, and what ships each week is
worked out afterwards from the stock the plan leaves (orders ship as soon as stock exists, oldest
first, an assumption).

Amount and delay hold one value per edge for the whole plan. A value that holds only for some
weeks ("transfers take two weeks in February") needs dated edges, which are not built.

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

| Task | Edges (amount, delay) |
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
| 2.3 | Tasks and edges from convention 2 and two setup lists (below) | 80 tasks, 180 edges |
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
| Edges | 180 | make 20 · move 40 · fulfil 120 |

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

Dealer inventory is in the object with its opening level and no edges. The data has no dealer
sell-through, so nothing moves it. With that data it connects without changing anything else.

## Planning priors

The object has two kinds of result: levels (on resources) and runs (on tasks). A prior is a
statement about a level, a run, or a **position**, in one of six forms.

A **position** is a signed sum of levels that a target is set on. Redwheel's positions come from
the routing rule: stock sites that serve a common customer form a pool, and for each SKU and pool
the position is the inventory at the pool's sites minus the orders of the customers it serves.
With every route allowed there is one pool per SKU, and the position is the net position above
less stock in transit: stock counts in a position once it has arrived.

| Form | On a level or a position | On a run | Status |
|---|---|---|---|
| **target** | weeks of supply: the position should cover the next N weeks of arrivals onto its order resources | – | built |
| **cost** | orders left waiting; stock above target | a small cost per run | built, with fixed weights |
| **max** | storage limit | route not used (max 0); a build limit over a date range | routing and "what the plan decides" built; dated limits **planned** |
| **min** | safety stock | minimum build | not built |
| **fixed** | – | frozen weeks, a planner's manual build | not built |
| **multiple** | – | fixed order quantity, lot size | not built; needs whole-number variables |

A weeks-of-supply target is the one place a prior reads the object's inputs: it is measured in
arrivals onto order resources, outlook weeks included. So a change to those arrivals moves the
target with it, and there is no second copy of demand to keep in step. (The frozen base function
`aux_fns.run_plan` still reads the forecast table; a test holds the two equal for all 156 weeks.)

One row per prior, in general:

| Column | Meaning | Example |
|---|---|---|
| applies to | a level, a run, or a position | position |
| selection | filter on the description tables | product group = road |
| form | one of the six | target |
| value, unit | units, or weeks of forward arrivals | 10 weeks |
| from, to | the weeks it applies | 2028-01-03 onward |
| strength | hard, or soft | soft |
| source | brief, assumption, or planner | brief |

A prior is stored once with a date range, not as a value per week.

**Built so far:** the settings table in `priors.py` (prior, applies to, value, from date), checked
against the object before every run. It has five row types. Two of them are not priors by the
first test above. They are changes to edge delays, kept in the same table because a planner sets
them the same way:

| Row type | It is | Becomes |
|---|---|---|
| `route` | prior | the pools, and so the positions |
| `target_weeks` | prior | the target on each position, from a date |
| `decides` | prior | which kinds of task have runs to decide (builds, transfers) |
| `build_weeks` | change | the delay on a line's make edges |
| `transfer_weeks` | change | the delay on the move edges |

Links between SKUs (substitutes, families) are description data, next to the item table, that
priors and tasks can use. Redwheel has none.

Redwheel's priors:

| Prior | Form | Source |
|---|---|---|
| road, 8 weeks; 10 weeks from 2028-01-03 | target on each position | brief (2028 start date assumed) |
| mtb base, 12 weeks | target on each position | brief |
| mtb carbon, 15 weeks | target on each position | brief |
| the worst shortfall against target on a line in a week | cost, weight 1 | assumption |
| total shortfall against target | cost, weight 0.1 | assumption |
| stock above target | cost, weight 0.001 | assumption |
| a bike built or moved | cost, weight 0.000001 | assumption: nothing is built or moved without need |

Shortfall and stock above target are counted in weeks of the position's average demand.

## Changes

A change edits numbers of the object for one scenario. The base object is never modified:
`changes.apply(object, changes)` returns a new object and a report, and everything after that (the
equation, the targets, the solver, the checks) reads the new object.

**Built** for the opening level, the arrivals and the run limits (`changes.py`, generic, tested by
hand on the tiny supply chain and on Redwheel's object, and against a second implementation on
random changes). A scenario carries a list of changes (`Case.changes`),
`run_case` applies them to the object before anything else reads it, and they are saved with the
scenario. A what-if, or a copy, keeps the changes of the scenario it starts from: it changes
settings, not the world.

One row per change:

| Column | Meaning | Example |
|---|---|---|
| field | which number: `opening` or `arrival` (on resources), `run_max` (on tasks) | arrival |
| selection | which resources or tasks: conditions on kind, item, location (resources only), or any column of the item description table (and, for resources, the location table). Every condition must hold | kind = capacity, location = RENO/mtb-carbon |
| operation | `set` replaces each selected number, `add` adds to each, `scale` multiplies each | set |
| value | the number | 0 |
| from, to | arrival and run limit: the first and last week, both included | weeks 26 to 28 (1–15 Mar 2027) |
| reason | why, in words | line down for maintenance |

The rules. A list of changes that breaks any of them is refused, with every broken rule named:

1. Field, operation and value are well formed; a set or scale value is not negative.
2. The selection names exactly one kind, uses only known columns (none that exists in two
   tables), and matches at least one resource or task. The kind fits the field: a resource kind
   (inventory, capacity, order) for opening and arrival, a task kind (make, move) for a run limit.
3. An opening change has no weeks, and capacity has no opening level.
4. An arrival change gives both weeks, with 1 ≤ first ≤ last ≤ 156. Weeks after the plan
   (122–156) can change only on order resources: nothing is decided there, and only targets read
   them.
5. A run limit is set, never added to or scaled, and gives both weeks with 1 ≤ first ≤ last ≤ 121:
   tasks run only in the plan.
6. No number goes below zero.
7. A change that alters no number is refused: it is almost always a wrong week or selection.
8. Changes apply in the order listed, so a later change sees the result of an earlier one.

**Whole units.** Redwheel's object counts whole bikes. A set or add value must be a whole number,
and a scaled number is rounded to the nearest whole unit, halves up (65 bikes × 1.3 = 84.5 → 85).

**The report** has one row per change: how many resources and numbers it touched, and their total
before and after. A three-week line stoppage reads "1 resource, 3 numbers, 1,125 → 0".

**Amount and delay are not changed this way yet.** Redwheel sets its two delays in the settings
table. Changing an edge needs one more definition first: which of a task's edges carry its lead
time. A move has four edges and only two of them are delayed.

**The plan knows every change from week 1.** A line that is down in March is planned around from
September: where it can, the plan builds differently beforehand (more in total if the line has spare
capacity; otherwise a different mix of SKUs). That is right for anything known in advance, such
as a shutdown or a revised forecast. A surprise needs the weeks before it held as already built,
which is the *fixed* prior, not built.

What a planner says, and what it is:

| A planner says | It is | In the object or the priors | Status |
|---|---|---|---|
| A line is down for three weeks | change | arrival onto the line's capacity, set to 0, dated | built (scenario E1) |
| Forecast is up 30% for a quarter; a big order landed | change | arrival onto order resources, scale or add, dated | built (scenario E2) |
| The stock count was wrong | change | opening level | built (tested) |
| A bike takes a week to build | change | delay on make edges | built (`build_weeks` setting) |
| Transfers now take two weeks | change | delay on move edges | built (`transfer_weeks` setting) |
| Frames are late: none of one SKU for eight weeks | change | run limit 0 on that SKU's make task, dated | built (scenario E3) |
| At most 20 a week of a SKU go to the PDC | change | run limit 20 on that SKU's move task, dated | built (tested on B) |
| The PDC stops serving commercial | prior | routing rule | built |
| Target goes from 15 to 12 weeks | prior | target | built |
| Lock the first four weeks | prior | fixed on those runs | not built |

### How a scenario is solved

1. The base object, built once from the files.
2. The scenario's changes are applied to it, giving the scenario's object.
3. The scenario's priors are read against that object: positions, targets, and which runs are
   decided. A run limit on a run that is not decided is refused.
4. The linear programme chooses the runs, each within its run limit.
5. Runs are rounded to whole bikes, within capacity and within the run limits.
6. Levels follow from the equation, and the checks run on the result.

Steps 2 to 6 are one code path for every scenario (`scenarios.run_case`); the base case has no
changes, runs through it and reproduces the frozen base plan exactly. The two delay settings are
still applied when the object is built, before step 2.

### Events

Two scenarios show the object solving a changed world. Each is scenario A's settings with one
change, and is tested three ways: the change touched exactly the numbers it says, the plan moved
where it must and nowhere else (every other line's builds identical to A, week by week), and every
plan check passes. Each also gives exactly the same plan as the same event made by editing the
input files instead (every number compared).

**In the planner (`planner2/`)** both are built in beside A and B, and anyone can make their own on the
What-if page (the **Events** card: a line down or slowed, demand up or down, a stock count
correction; each checked against the object before it is added, and with the settings, previewed
and saved as part of the scenario). A scenario's page has an **Events** tab (the numbers changed, the
effect on each line against the scenario it is compared with, and two charts for a line, the event
weeks shaded), an events badge, and its events in the Settings tab's differences. Compare lists
events among the settings that differ, and the facts that Ask answers from list them with the numbers
each changed. The older UIs (`app/`, `planner/`) run and chart a saved scenario that has events, from
its own object (capacity, stock), but do not list them.

| Scenario | Change | Numbers changed | What the plan does |
|---|---|---|---|
| **E1** MTB carbon line down three weeks | capacity of RENO/mtb-carbon set to 0, weeks 26–28 (1–15 Mar 2027) | 3: 1,125 → 0 | builds nothing on the line those weeks; the same 94,429 bikes, built at other times; MTB carbon holds targets from 4 Oct 2027, not 6 Sep |
| **E2** RW-4418 dealer demand up 30% | dealer orders of RW-4418 scaled by 1.3, weeks 18–30 (4 Jan–29 Mar 2027) | 13: 636 → 827 | builds 191 more, all RW-4418; MTB carbon holds targets from 13 Sep 2027 |
| **E3** RW-4418 frames late eight weeks | run limit of RW-4418's make task set to 0, weeks 60–67 (25 Oct–13 Dec 2027) | 8: no limit → 0 | builds the 1,394 RW-4418 it would have made in those weeks in the five weeks before (the line has room then); no other SKU, date or total moves |

In E1 nothing can be built ahead: in A the MTB carbon line already runs full every week from
7 Sep 2026 to 30 Aug 2027. So the plan makes up the 1,125 bikes lost in March exactly, in the five
weeks from 6 Sep 2027, out of capacity that A leaves spare. The other three lines are built exactly
as in A. On MTB carbon the line's total is the same as A's in every week except those eight, but the
mix of its three SKUs shifts around the stoppage (week 25: RW-9304 +15, RW-4418 -9, RW-6416 -6; week
29 smaller; one-bike swaps between SKUs in weeks 33–52, a tie the solver breaks differently). The line
holds its targets from 4 Oct 2027, the week the catch-up ends.

E3 is absorbed: the plan knows the frames are late, and the line has spare capacity in the weeks
before, so it builds ahead and every target is held as in A. Shorter slips, and slips while the
line is full, are absorbed too, by building the line's other bikes in the gap: in Redwheel the
line's total capacity is the limit, not any one bike. The cost shows only in the objective (stock
carried above target before the gap). E3 gives exactly the same optimum (objective, every run,
every level) as the same event written without a run limit: a separate frames supply that RW-4418
uses one of per bike, none arriving in those weeks. E3 is not yet listed in the planner, whose
words for events do not cover a run limit. A stock correction (200
fewer RW-9324 at Reno) is tested the same way: 200 more built, all RW-9324, and no date moves,
because that SKU has stock to spare.

## Every tunable, in one list

Everything a scenario can say is different is in one list, `redwheel/tunables.py`. A tunable is a
planner's question with a form; filling the form gives either a change to one of the object's
numbers or rows of the settings table. Nothing else is tunable, and nothing is defined twice.

| Tunable | Changes | Where it sits in the model | Unit | Dated | Form fields | Default |
|---|---|---|---|---|---|---|
| Stock count | data | opening level of a SKU's stock at a site | bikes | no | SKU, site, correction | RW-9324 at Reno, −200 |
| Line capacity | data | arrivals onto a line's capacity | % of normal (0 = down, 120 = overtime) | yes | line, from, weeks, % | **E1** |
| Demand | data | arrivals onto orders (a SKU, a line or all; a channel or all) | % of forecast | yes | SKUs, channel, from, weeks, % | **E2** |
| One-off order | data | arrivals onto one SKU's orders from one channel, one week | bikes | yes | SKU, channel, week, bikes | RW-4418, commercial, 300 |
| Build limit | data | run limit of make tasks (parts late or short) | bikes a week, each SKU | yes | SKUs, from, weeks, at most | **E3** |
| Transfer limit | data | run limit of move tasks, Reno to the PDC | bikes a week, each SKU | yes | SKUs, from, weeks, at most | all SKUs, 20 a week |
| Build time | rules | delay on make edges | weeks | no | line, weeks | MTB carbon, 2 |
| Transfer time | rules | delay on move edges | weeks | no | weeks | 2 |
| Ship from | rules | which fulfil routes exist | site | no | channel, site | web from the PDC |
| Plan transfers | rules | whether the plan decides moves | yes / no | no | yes or no | yes |
| Target | rules | a group's weeks-of-supply target, from a date | weeks of supply | yes | group, weeks, from | MTB carbon 18 from 6 Sep 2027 |

Every field has its choices, range and default (`TUNABLES[key].fields`). A date picks the plan
week that contains it; "n weeks" is n whole plan weeks. The defaults of Line capacity, Demand and
Build limit are E1, E2 and E3: filled with nothing changed, they plan exactly like those scenarios
(tested). The rules tunables rebuild scenario B from A (tested).

What the module gives, for any UI or an LLM:

| Call | Does |
|---|---|
| `TUNABLES`, `table()` | the list; one row per tunable |
| `make(key, **values)` | a filled form → an `Edit` (a `Change`, or settings rows); refuses a wrong field, naming it |
| `apply(case, edits, **fields)` | the scenario with the edits (settings applied, changes added in order) |
| `check(case, edits)` | every reason it cannot run, in words, without planning: the settings against the network, each change against the object, a limit on runs the plan does not decide, an edit that changes nothing |
| `describe(edit or change)`, `name_hint(change)` | in words, e.g. "MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027 · down (none)" |
| `now(key, case, **values)` | what the scenario has there now, e.g. "375 a week", "no limit" |
| `differences(a, b)` | what b sets differently from a: settings and changes, as Tunable · What · From · To · Why |
| `change_rows(changes, report)` | a run's changes with the numbers each changed (from `R["change_report"]`) |

The planner (`planner2/`) still uses its own words for events (`planner2/events.py`); they cover
the first four data tunables. E3 joins its built-in list when its words come from this module.

### A request in words → tunables, filled by Claude

`llm.propose_edits(request, case)` turns a sentence into filled tunable forms for that scenario,
checked before anyone sees them. Claude only fills forms; it never runs or changes the model.

1. Claude gets the request, the scenario in words (its settings and the changes it already has),
   the catalogue (sites, channels, lines, SKUs with line and size) and every tunable with its
   fields, choices and ranges. No orders, forecasts, stock or customer data.
2. It answers in a fixed shape: edits (each a tunable and all its fields), what no tunable can
   express, and a question when the request does not say which line, SKU, channel, site or weeks.
   Tunable and field names can only be real ones.
3. Each edit goes through `tunables.make` (every field checked; a field left out is an error,
   never a default) and `tunables.check` (against the network and the object, in words). Anything
   that fails goes back to Claude once, with the reasons.
4. The result is a proposal: the edits, in words, with the words of the request each carries out.
   `proposal.scenario()` gives the scenario with them, for a person to review and run.

Live, against the real model, with known answers (`RUN_LLM_TESTS=1`): "A line is down for the
next two weeks" → a question ("Which line…?"), no edits. "The MTB carbon line is down for the next
two weeks" → line capacity 0 in the weeks of 7 and 14 Sep 2026. "The road carbon line is down for
all of March 2027" → the five weeks from 1 Mar. E1 and E2 in one sentence, E3, a stock count and
scenario B from A: each exactly. A conditional shipping rule → unsupported, with the reason. Each
on the first attempt. `llm.propose`, the earlier settings-only version, is kept while the planner
UIs call it.

## What is general and what is Redwheel

| Layer | What | Changes for another company |
|---|---|---|
| Object | resource, task, edge, the equation; changes to its numbers (`rtn.py`, `changes.py`) | never |
| Solver | the linear programme on any object, any positions and targets (`engine.py`) | never |
| Conventions | location classes, task templates (`rtn.py`) | a row when a new kind of place or activity appears |
| Scenario runs | pools from a routing rule, a run from a settings table (`scenarios.py`, `priors.py`) | the method carries over; the code names Redwheel's two sites and three customers |
| Redwheel | locations, setup lists, numbers, priors, assumptions (`aux_fns.py`, `config.py`) | all of it |

The same object, with more rows in the conventions, also represents: components (one more edge
on make), suppliers (a buy task), more sites, route capacity (one more edge on move), a SKU
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

369 tests, all passing (`pytest`), plus 13 that call the LLM (`RUN_LLM_TESTS=1 pytest tests/test_llm_live.py`).

| File | What it checks |
|---|---|
| `test_rtn.py` | The generic object on a tiny supply chain worked out by hand: every edge, every level week by week, net position, a transfer still in transit at the end of the horizon, the graph view, and that `validate` rejects broken objects |
| `test_master.py` | Master data against figures recounted from the raw files without this codebase |
| `test_object.py` — structure | Location classes; resource counts per kind and location; each SKU made on its own line only; each line shared by exactly its SKUs; every move goes through transit; every customer can be served from both sites; every order is reachable from its line in the graph; only dealer stock is unconnected |
| `test_object.py` — numbers | Opening inventory row by row against the plant file; dealer stock; backlog per SKU and channel; forecast and capacity arrivals cell by cell; opening net position against the independent recount |
| `test_object.py` — equation | With no plan: stock stays, orders grow by the forecast, capacity resets. With four plans (random builds, all transferred, little built, no transfers): no level below zero, net position equals opening + built − forecast, bikes are conserved, transfers land after exactly the transfer time, dealer stock never changes |
| `test_changes.py` | Each kind of change worked out by hand on the tiny supply chain, a change reaching into the outlook and moving a target, every rule that refuses a change; then on Redwheel: the outlook against the forecast file, and that a change touches exactly the numbers it says |
| `test_events.py` | Scenarios E1 and E2 and a stock correction: exactly which numbers changed, which builds moved, which dates moved, every plan check; changes saved and loaded with a scenario |
| `test_engine.py` | The linear programme on small cases worked out by hand, lead times, whole-bike rounding |
| `test_base_case.py` | The base plan pinned, quantity and timing per SKU; and that scenario A run from its settings table gives exactly that plan |
| `test_scenarios.py`, `test_priors.py` | Pools from the routing rule; the books balance across sites and in transit; every plan check on A and B; the settings table, and each rule that rejects a bad one |
| `test_baseline.py` | The LP against the planner's rule, and that no feasible plan beats the LP on its own objective |
| `test_report.py`, `test_demand.py` | Report figures; demand sources |
| `test_llm.py`, `test_llm_live.py` | Both proposal loops (settings only; any tunable) with a fake model: the answer's shape, every field checked and none defaulted, failures sent back once with the reasons, what the model sees; then 13 live requests with known answers (8 for any tunable, 5 for settings) |
| `test_app.py`, `test_planner.py`, `test_planner2.py` | Every page of the three UIs, and each flow a planner takes |
| `test_tunables.py` | The one list: every form's defaults valid; the forms make exactly E1, E2, E3 and the stock correction, and the rules forms rebuild B from A; wrong fields refused with the reason; checks in words; every tunable in words; what is there now; differences between scenarios; every data tunable run through the solver with every plan check passing (a one-off order of 300: exactly 300 more of that SKU built) |
| `test_events_ui.py` | Events in the planner: plan weeks and dates; the forms make exactly events E1 and E2 (same numbers changed); events in words; what differs between two lists of events; the Events tab's charts (window, shading, the lowest SKU, capacity); the What-if card (invalid events refused with the reason, events checked together, added, removed, saved, run); Home, Compare, Settings and the facts for Ask |

The object tests were checked by breaking the object on purpose, seven ways: transit stock released on
the wrong week, web and dealer channels swapped, orders not carrying over, in-transit not counted
as ours, builds landing at CMH, capacity carrying over, dealer stock counted as ours. A test
failed every time.

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
