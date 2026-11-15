# Working notes

Decisions taken and items still open. Updated as we go; newest decisions at the bottom of each list.

## Decisions

| # | Decision | Date |
|---|---|---|
| D1 | The base case (builds on pooled net inventory, no lead times in play, shipping and transfers not decided) is frozen and guarded by `tests/test_base_case.py`. New behaviour is opt-in. | 2026-11-11 |
| D2 | PDC = the Columbus distribution centre. | 2026-11-11 |
| D3 | Routing ("customer orders ship from the PDC") is a planning prior, not part of the object: the routes stay in the object, the prior says which may be used. | 2026-11-11 |
| D4 | Weeks of supply is counted the way demand faces: each stock location against the demand it serves. Stock counts once it has arrived. The factory rolls up to all demand through the transfer to the PDC. | 2026-11-11 |
| D5 | Build time is a modifiable parameter (by line or SKU eventually). First value: 1 week, the same for every line. Reno → PDC stays 1 week. | 2026-11-11 |
| D7 | Scenario A = the base case. Scenario B = routing B: web orders ship from the PDC (replenished from Reno, 1 week); dealer and commercial orders ship direct from Reno; build time 1 week; the LP decides builds and transfers. | 2026-11-11 |
| D8 | Navigation: Overview (Context, Scenarios, Scenario Comparison) → one section per scenario (Summary, Network, Build Plans, Build Score, Inventory Balance) → Model (Object Encoding, Demand Sources, Model Validation). Previous/next links follow that order. Context holds snapshot facts only; the Summarized Plan lives in each scenario's Summary. | 2026-11-11 |
| D9 | The network is shared; a scenario sets edge delays and which ship routes are used. Each scenario's Network page reads both from that scenario's network and routing rule; Object Encoding shows the shared network (every route, no delays). | 2026-11-11 |
| D10 | Second UI `planner/` (run `streamlit run planner/app.py`), built around scenarios: sidebar list (A, B locked; copies editable, saved to outputs/scenarios/), Priors tab edits the table with plain controls → change list → validation → Apply and re-plan. Every edit is a change list (`priors.diff` / `apply_changes`): the format an LLM will propose in. First UI `app/` kept as is. | 2026-11-11 |
| D11 | LLM architecture (`redwheel/llm.py`): request + current priors table + network structure → one structured call (fixed schema; names limited to the network's) → change list applied to a copy → `priors.validate` → one retry with the errors → a proposal for a person to review. The LLM never writes the model, runs a plan or sees orders/stock. Model Opus 5.5, effort medium, server-side refusal fallback on. Live set (5 requests, `RUN_LLM_TESTS=1`): 5/5 first attempt. In the planner: an Ask box on the Priors tab of editable scenarios loads the proposal into the editors as unapplied changes with reasons; the existing Apply/Discard decide. | 2026-11-11 |
| D12 | Third UI `planner2/` (scenario-first; `streamlit run planner2/app.py`). Home (situation, scenario cards, how to use) · Scenario (header with pickers; headline vs a chosen comparison; tabs Summary · Builds · Inventory · SKU detail · Settings) · What-if (start from any scenario; describe it (Claude) or set it directly; review in plain words, live check, live preview of the result; run creates or saves) · Compare (any set vs a reference; settings that differ; when each line holds target; ask why). LLM `explain` answers only from a facts sheet of computed results. `app/` and `planner/` kept. | 2026-11-12 |
| D13 | Rollup check fixed for scenarios where a site serves no orders (its stock is in no pool): pools + in transit + stock at such sites = total net. Found on the user's scenario C (all orders via the PDC); the gap equalled Reno's stock exactly, so the plan was right and the check incomplete. | 2026-11-12 |
| D14 | Scenarios are solved natively by the object. A scenario = changes to the object's numbers (opening, arrival, amount, delay; set/add/scale; dated for arrivals) + planning priors. Applying changes returns a new object; targets are read from the object's own order arrivals, so the object also carries the outlook (forecast weeks 122–156). Spec: README "Every number in the object", "Planning priors", "Changes". Changes are known to the plan from week 1 (it anticipates them); surprises need the fixed prior, later. The settings table stays as is; changes sit beside it. | 2026-11-15 |
| D15 | Three demonstration events, probed in scratch on scenario A before building (these are the acceptance numbers). (1) MTB carbon line down 3 weeks from 1 Mar 2027: 3 cells, −1,125 capacity; 0 built on the line those weeks; total built unchanged (94,429); line holds targets 4 Oct 2027 (was 6 Sep). (2) RW-4418 dealer forecast +30% Jan–Mar 2027: 13 cells, 636 → 827 (+191; one week is 65, and 84.5 rounds up); total built +191, all RW-4418; line holds targets 13 Sep 2027. (3) Supplier slip as a dated max 0 on RW-4418's make runs, 4 weeks from 1 Mar 2027: line still builds 1,500 of 1,500 on its other SKUs; total and line date unchanged. In all three the other lines' builds are identical cell for cell and 8 of 8 checks pass. Targets from the object's arrivals equal today's exactly (A and B, weeks 1–156). | 2026-11-15 |
| D16 | Rules for changes (README "Changes", `changes.py`): one kind of resource per change; arrival changes give both weeks; weeks after the plan only on order resources; no number below zero; a change that alters nothing is refused; applied in order; whole units, scaled numbers rounded halves up. Built for opening and arrival only. Amount and delay stay in the settings table until a task's lead-time edges are marked (a move has four edges, two delayed). Events 1 and 2 re-probed through the native path (object → `changes.apply` → targets from the object → LP): numbers as in D15, 8 of 8 checks. | 2026-11-15 |
| D17 | Scenarios carry changes (`Case.changes`, applied first in `run_case`, saved in the scenario file; old files load with none). Both planner UIs cache a run on its settings and its changes. A what-if or a copy keeps the changes of the scenario it starts from (it changes settings, not the world). Events E1 and E2 are built in (`scenarios.EVENTS`), not in `CASES`, so the UIs do not list them until they can show changes. Validated: A–E identical to the last commit (160,450 numbers); E1 and E2 identical to the same events made by editing the input files (21,518 numbers each); 14 of 14 injected step-3 faults caught. Found and fixed in validation: the planner2 cache decorator had slipped onto a helper keyed by scenario letter (stale results across sessions; also why the suite had slowed to 3 min); charts, the plan grid, line use and SKU facts read capacity and stock from the base data instead of the scenario's object; a scenario with A's settings and a change was badged "Same settings as A". Each now has a test. | 2026-11-15 |
| D18 | Events are in the planner (`planner2/`). Built in: E1 and E2 beside A and B (`state.BUILT_IN`; still not in `scenarios.CASES`, so the older UIs do not list them). What-if has an **Events** card (first in step 2): a line down or slowed, demand up or down, a stock count correction. Each form builds one `Change` (`planner2/events.py`), is shown in words before it is added, and is checked with the events already in the draft by `changes.check`; an event that breaks a rule cannot be added and the reason is shown. A draft starts with its base's events (remove or add); the review lists events added or removed; the preview, create and edit keep them. The Scenario page has a constant events badge, an **Events** tab (numbers changed, effect per line against the compared scenario, two charts for a line with the event weeks shaded) and events in the Settings differences. Compare, the facts for Ask and the Home badge all read events; the duplicate badge and the differences compare events by the resources they edit (a form's `location=DEALERS` equals E2's `channel=dealer`). Wording corrected: the assumptions no longer say only settings differ. Validated: 32 new tests (296 in all, 5 live-LLM skipped); a real-browser walk of every changed page and of creating, viewing and deleting scenarios with events; 37 injected faults in a copy of the repo, all caught (one, a capacity line that drew the builds, needed a stronger test: in E1's weeks the builds equal capacity); a random check of 15 events (5 of each kind) against exact integer arithmetic and a cell-by-cell comparison of the objects. **Correction to D17's report:** 'every other week is built as in A' holds for the line's total and for the other three lines, not SKU by SKU on MTB carbon: the plan re-mixes the three SKUs around the stoppage (week 25: RW-9304 +15, RW-4418 -9, RW-6416 -6; week 29 smaller; one-bike swaps in weeks 33–52). Now pinned in `test_events.py` and stated in the README. | 2026-11-15 |
| D6 | "Shipped" means factory output released to orders as soon as it is available (an assumption). | 2026-11-11 |

## Open items

| # | Item | Notes |
|---|---|---|
| O1 | Split the forecast by ship-to location | Not needed while every order ships from the PDC. Needed once a second shipping site is allowed. Method agreed in principle: historical state mix; commercial orders have no location. |
| O2 | Need-by-date phasing of the opening backlog | Open orders counted as owed now. Wanted: owed in their need-by week; orders without one (all web orders) at an agreed service level. Depends on O3. |
| O3 | Question for Redwheel: is the forecast by order-placement week or by due week? | If by due week, phasing backlog by need-by date could double count. |
| O4 | Road target step date | Brief says "in 2028"; we use 3 Jan 2028. Fiscal reading would be Sep 2028. |
| O5 | Run bookkeeping: save a case with its inputs and results, reload, compare | After the first non-trivial case works end to end. |
| O6 | LLM form that fills in a case | Exhibit candidate: "change the build time on a line". After O5. |
| O7 | Scenario list to re-run | Supplier slip, demand spike on a SKU, line capacity down: specified in D14/D15; build steps O18–O22. |
| O8 | Object Encoding page: show how the raw files map into the object | Pinned by the user. |
| O9 | Build Score page needs a proper rework | Heatmap removed; quarter-end table per position. Planner's rule toggle for scenario A only. |
| O10 | Shipping decided by the model rather than assumed | Today: ship as soon as stock exists, oldest orders first. |
| O11 | Code and README still say "arrows"; the UI says "edges" | Rename if wanted. |
| O12 | Near-term forecast is well below recent orders on every line | Stated on page 1; raise with Redwheel. |
| O13 | Road SKUs hold stock roughly equal to their open orders, and those orders are not shipping | Data does not say why. |
| O14 | End-of-horizon effect in scenarios with lead times | In scenario B a bike built in week 121 lands after the horizon, so the plan builds nothing in week 121, tapers in week 120 and transfers nothing in the last week. Fix: plan a few weeks past the reporting horizon (needs capacity assumed beyond the data). Guarded by a test so it is not forgotten. |
| O15 | ~~Other pages show scenario A only~~ | Done: each scenario has its own section of pages (D8). |
| O16 | ~~Planning priors as an editable table~~ | Done: `redwheel/priors.py`, edited in the planner's Priors tab. |
| O17 | ~~Guard against parking stock in transit~~ | Done as a validation rule: transfers may be decided only when Reno and the PDC serve different orders. Evidence B does not park: re-solved with a 100x per-run cost, transfers identical in total and timing. (Transfers = PDC demand + closing − opening PDC stock + in transit is an identity, not evidence.) |
| O18 | ~~Events step 2: the object carries the outlook; targets read the object's arrivals; generic `changes.apply` with validation~~ | Done (D16). 249 tests; every pinned number unchanged. |
| O19 | ~~Events step 3: scenarios carry changes; events 1 and 2 (and a stock correction) as built-in scenarios~~ | Done (D17). Changes are stored by plan week; the UI will show dates. |
| O20 | Events step 4: dated limits on runs in the solver; rounding respects them; widen "below target only while the line is full" to count a build limit | Then event 3. Test case for the widened check: a limit in weeks 1–4 on a SKU that starts below target. |
| O21 | ~~Events step 5: UI~~ | Done (D18). Not done: the older UIs (`app/`, `planner/`) do not list events; the Events tab shows a line's totals, not its SKU mix (E1's re-mix and E2's SKU shift are visible only in the SKU detail tab); events are dated by plan week (a date picks its week) and there is no form for a supplier slip yet (step 4, O20). |
| O22 | Events step 6: LLM proposes changes through the same checked loop | Extend the live test set. |
| O23 | Later: surprise events (fixed prior on earlier weeks), dated edges, priorities, batch sizes | |

## Presentation plan (presentation 2026-11-16)

**The story.** We turned Redwheel's nine files into one model of its supply chain. The build plan comes out of
that model. When something changes, we change a few numbers in the model and re-run. No new code.

### The five parts (30 minutes)

| # | Part | Min | On screen |
|---|---|---|---|
| 1 | The plan | 2 | Scenario A: 94,429 bikes built, and the date each line reaches its target |
| 2 | The data | 4 | Which file fills which part of the model; what is fact and what is assumed |
| 3 | The model | 8 | One bike (RW-4418) drawn as the model, with its real numbers |
| 4 | How the model becomes the plan | 4 | One table: each part of the model and what it becomes in the solver |
| 5 | Something changes (live) | 10 | A line goes down for 3 weeks: what we changed, and what the plan did |

Two minutes left for limits and what is next.

### What to build today

| # | What | Who |
|---|---|---|
| 1 | Events run as scenarios: line down, demand up (O19) | other agent |
| 2 | Events tab in planner2: the numbers changed, and two charts, base plan vs event (O21) | other agent (done, D18) |
| 3 | Object page in planner2: parts 2, 3 and 4 above | Claude (this session) |
| 4 | Deck as a PDF: the same five parts, numbers taken from the code | Claude (this session) |
| 5 | One practice run, then commit and submit | user |

The two charts for the Events tab, both for the MTB carbon line, event weeks shaded:
weekly builds against capacity, and weeks of supply against the 15-week target.

### The live example (checked on scenario A)

MTB carbon line down for 3 weeks from 1 Mar 2027.

- We change 3 numbers: capacity 375 → 0 in those weeks.
- The line was already full, so the 1,125 lost bikes cannot be made up until capacity rises on 6 Sep 2027.
- The line reaches its target on 4 Oct 2027 instead of 6 Sep: four weeks late.
- The other three lines do not change at all.

Second example if there is time: RW-4418 dealer forecast up 30% for Jan–Mar 2027. The plan builds more RW-4418
early, and the other two bikes on that line get fewer builds.

### Deck v2 and run order (2026-11-15)

Deck: https://claude.ai/artifact/7ifdskPFBCM8xmGpgNaoFD (5 slides). Live parts in planner2.

| # | Question | Where | Shows |
|---|---|---|---|
| 1 | What is the plan? | slide | Weeks of supply per bike vs target, 4 lines; shading = line at full capacity |
| 2 | Why believe it? | live | Scenario A › Plan checks: 8 of 8; 278 bike-weeks below target, 0 where the line had room |
| 3 | Why not just write the LP? | slide | Same plan for the brief; rows where a hand LP is rewritten and the object takes a setting |
| 4 | What is the object? | slide | RW-4418 drawn end to end with opening numbers; the one rule |
| 5 | A line goes down 3 weeks | live (events, being built) | 3 numbers; target 4 Oct 2027 not 6 Sep; other lines identical |
| 6 | Columbus ships web orders | live | Compare A vs B: MTB carbon 27 Sep 2027 not 6 Sep; same object and solver |
| 7 | Where does it stop? | slide | 3 not built, 2 need data |
