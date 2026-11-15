# The solver

Owner: the solver session (`src/redwheel/engine.py`, and the calls to `engine.decide` in `scenarios.run_case` and
`aux_fns.run_plan`). Read this before you call `engine.decide`, compute a "weeks short" yourself, or quote a number
the solver produces. Decision log: D23 in [WORKING_NOTES.md](WORKING_NOTES.md). Last checked 2026-11-15.

## 1. From the object to the LP

Nothing in the LP is written by hand for Redwheel. Every row comes from the object (`rtn.RTN`) or a planning prior.

```
 THE OBJECT                                    THE LP (engine.decide)
 resource r  inventory | capacity | order  ->  level[r,t] >= 0                one variable per resource and week
 task i      make | move | fulfil          ->  0 <= runs[i,t] <= run_max[i,t]  only the kinds the scenario decides
 edge        (i, r, amount, delay)         ->  amount * runs[i, t - delay] in r's balance row
 opening, arrival, carry                   ->  the balance row's constants:

     level[r,t] = carry[r] * level[r,t-1] + sum over edges into r of amount * runs[i, t-delay] + arrival[r,t]

 PLANNING PRIORS
 routing: which stock serves which orders  ->  positions s:  net[s,t] = stock in the pool - orders it faces
 target: N weeks of supply                 ->  target_units[s,t] = forecast of weeks t+1 .. t+N  (engine.forward_sum)
 what the plan decides                     ->  which tasks are free
```

Capacity is a resource that does not carry (unused capacity is lost), so `level >= 0` on it reads "used <= available".
On stock it reads "never send what is not there". Orders are resources too: forecast arrives on them, so net
position = stock − orders, negative when customers are waiting.

Size: scenario A has 13,068 variables, 8,954 balance rows and 3,630 target rows. B has 16,698 variables. HiGHS solves
either in under 0.2 s. Whole bikes come afterwards (`round_runs`, `scenarios.round_moves`), and the plan checks prove
the rounding loses no target. A task with a **lot** (the object's seventh number, a fixed order quantity) is cut into
whole lots the same way: cumulative round-up to a lot, a lot taken back where the line is over, the room it leaves
filled by the tasks most behind the LP (D26). The LP itself does not know lots; the exact version is a MIP, later.

## 2. What it minimises

```
 short[s,t]  >= target_units[s,t] - net[s,t]        units below target  (>= 0)
 excess[s,t] >= net[s,t] - target_units[s,t]        units above target  (>= 0)
 u[s,t]       = short[s,t] / weekly_demand[s,t]     weeks short

 minimise   1      * sum over lines g, weeks t of  max over s on g of u[s,t]   the SKU furthest behind on each line
          + 0.1    * sum over s, t of u[s,t]                                    then the total
          + 0.001  * sum over s, t of excess[s,t] / weekly_demand[s,t]         build to target, not past it
          + 1e-6   * sum of runs                                                nothing built or moved for no reason
```

The max is linear through `worst[g,t] >= u[s,t]`. The weights act as a strict order: the first term's optimum is
the same at w_short = 0.1, 0.01 and 0.001 (checked on A).

**The divisor (D23).** `weekly_demand[s,t] = target_units[s,t] / N[s,t]` (`engine.window_demand`) is the average
forecast over exactly the weeks the target covers. So:

```
 weeks short = N x (share of the target's units that is missing)
```

This equals the shortfall on the weeks of supply the planner sees (N − `rtn.weeks_of_supply`) at the two points that
matter: N with nothing on hand, 0 at target. In between it is close, and exact when the forecast is flat over the
window. It stays linear because the divisor is data. The exact measure is not used: it is convex in net position
only when the forecast never falls, so in general it needs integer variables. A window with less than 1 unit a week
of demand is counted at 1, so nothing is divided by zero.

## 2a. A walk over floors (`decide_walk`, D24)

The same LP with the objective stated as ordered steps ([RANKED_WALK.md](RANKED_WALK.md)). A floor is a level net
position should not fall below: **target** (target units), **owed** (0), **due** (minus the open orders not yet due).
Floor names are opaque to the solver; the floor equal to target units reuses the LP's own shortfall block.
A step is (floor, positions); the walk is the steps in order. For each step: minimise w_worst × Σ the step's largest
shortfall in weeks per line and week + w_short × its total, then hold it at its optimum (+ 1e-7 + 1e-9 × |optimum|).
Last, stock above target and runs, with every step held. The single step (target, every position) gives `decide`'s plan
cell for cell. A ranked step arrives as one step per position, so the solver only ever shares evenly.

```
 short_f[s,t] >= floor_f[s,t] - net[s,t]        one block per floor used (the target floor's block is `short`)
 worst_j[g,t] >= short_f[s,t] / weekly_demand   one block per step j, for the step's positions
 step j:  minimise  w_worst·Σ worst_j + w_short·Σ short_f/d (its positions)   then hold
```

`Plan.steps` records each step's worst and total at its optimum; `Plan.objective` stays the score on the even rule,
so every plan is comparable on one yardstick. Not a single solve with shrinking weights: that differs from the exact
walk at some weights (RANKED_WALK.md §5). The plan check "Walk: a later step is served only when every earlier step
on the line was met or held back" (`scenarios.walk_served_out_of_order`) counts, on the LP's own runs, the (make task,
week) pairs where a task used a line's capacity while a position fed from that capacity was below the floor of a step
and not held back by a run limit (lead time included), and the task served no position of that step or an earlier one
(a position it feeds that is at or below that floor in the week the run lands or any later week: stock carries
forward, so a build ahead of a run limit or of another bike's turn serves a later dip). On tasks, not positions: in B
one make task feeds a bike's Reno and PDC positions, and a build at Reno may be how the PDC is served. The walk reaches the solver through `Case.walk` and
`redwheel.walk.solver_input(case, obj, positions, target_units) -> (floors, steps)` (the object session's module);
`run_case` carries it as `R["walk"]`.

## 3. What the objective decides, and what it does not

Is it optimising anything? Yes, but less than "an LP" suggests, and the deck should say so.

- **Line totals while behind: not decided.** A line below target runs full, so capacity sets its output and the
  units short summed over the line (178,935 unit-weeks in A, every divisor). This is why "capacity sets every date".
- **The mix on a full line: decided.** The first term gives every SKU on the line the same weeks short. This is the
  fair-share, or equal run-out, allocation of distribution planning, solved exactly.
  - What it guarantees: no SKU is built for cover while another on its line has customers waiting (0 line-weeks in
    A; 3 in B, where the waiting pool is a transfer away).
  - What it does not: who waits. The waiting is shared, so all three MTB carbon SKUs clear their open orders together
    on 14 Dec 2026. Clearing RW-6416's orders first (by 21 Sep; [RANKED_WALK.md](RANKED_WALK.md) row D, reproduced
    on this solver) raises on-time fill from 96.4% to 97.6% with the same dates. That choice belongs to a ranked
    walk, not to this objective.
  - Without the term it is worse (O24): position-weeks below target halve (278 → 139), but open orders summed over
    weeks rise 2.5 times (27,849 → 69,381 units) and on-time fill falls to 93.3%, because the LP builds cover on
    small SKUs while a big SKU's customers wait. Keep it until a ranked walk replaces it.
- **How much to build at target: decided.** Enough to hold the target, no more (the excess term).
- **When to build ahead: decided.** The LP sees the whole plan, so it builds before a known gap. In E3 it builds 1,394
  RW-4418 in weeks 55–59 ahead of the frames gap. A rule without look-ahead cannot. On A,
  `aux_fns.compare_plans` gives the LP 278 position-weeks below target and all targets held from 6 Sep 2027. The
  planner's lowest-cover-first rule gives 335 and 1 May 2028, with the same 94,429 bikes.
- **In B, also decided:** which pool the stock sits in, and when to transfer.
- **Not decided:** shipping (projected afterwards: oldest orders first, as soon as stock exists, O10), anything after
  week 121 (O14). Priorities between SKUs are decided only when a scenario carries a walk (§2a). Events are known from week 1 (O25).

## 4. D23: why the divisor changed, and what moved

Before D23 the divisor was one number per position: the mean forecast over all 121 weeks. The MTB carbon SKUs' forecasts
grow at different rates (RW-4418 from 56 to 161 a week, RW-9304 from 54 to 114), so on the near-term rate RW-9304 was
treated as further behind than it was. The plan built only RW-9304 in week 1, and the app then showed RW-9304
about 6 weeks ahead of the other two until mid-2027. The solver levelled one measure and the planner was shown another.

| Scenario A | Before | After |
|---|---|---|
| MTB carbon SKUs apart on the planner's weeks short, while below target (mean / max) | 1.87 / 5.99 weeks | 0.10 / 0.26 weeks |
| MTB carbon builds, weeks 1–3: RW-9304 / RW-4418 / RW-6416 | 375, 312, 128 / 0, 51, 155 / 0, 12, 92 | 269, 146, 144 / 79, 143, 142 / 27, 86, 89 |
| Bikes built in a different week (SKU swaps within a line; none on MTB base) | – | 651, of which 544 on MTB carbon, the last in week 53 |
| LP objective | 949.8 | 1,275.4 (a near-term week now counts at the near-term rate: a different unit, not a worse plan) |

Unchanged in A, B, E1, E2 and E3: every SKU's total, every line's total in every week, every line's date
(MTB carbon 6 Sep / 27 Sep / 4 Oct / 13 Sep / 6 Sep 2027), position-weeks below target (278 in A, 722 in B), and 9 of 9
checks. E1's SKU re-mix around the stoppage is smaller (week 25: +3 / −2 / −1, was +15 / −9 / −6). One line date
moves, and only off the built-in list: E3 under B's rules is held from 27 Dec 2027 (was 1 Nov). See O28.
**Also moved, found by the object session:** the week every open order is cleared is a week earlier (A and E1: 14 Dec
2026, was 21 Dec; B: 4 Jan 2027, was 11 Jan; E2: 14 Dec, was 28 Dec), with the same on-time fill. The scorecard was
not in my first comparison, which looked at line dates and totals.

Same change, same reason: `forward_sum` now reads a part-week target (the Target form allows 0.5 to 52 weeks) as
whole weeks plus that share of the next week, which is how `weeks_of_supply` reads it. At 15.5 weeks the plan used to
plan to 15, and 207 position-weeks it called at target showed below. Now there are none. No built-in scenario uses
a part week.

## 5. Holes checked

| Hole | Status |
|---|---|
| Solver's weeks short ≠ planner's weeks of supply | closed (D23) |
| Part-week target cut to whole weeks | closed (D23) |
| Window with no demand (demand −100%) divides by zero | closed: floor of 1 a week (D23) |
| Weights not a strict order | checked: they are |
| Fairness makes the plan worse (O24) | checked: it is what serves customers first; see §3 |
| "All targets held from" dates the last shortfall; the objective counts how far short, not when (O28) | open |
| End of horizon with lead times (O14) | open, guarded by a test |
| Ties: one-bike swaps between SKUs equally far behind are arbitrary | open, harmless |

## 6. What changed for you

Result keys: `run_case` and `run_plan` return the same keys as before, plus `weekly_demand` (position × week, the
divisor the plan used). `net`, `target_units`, `demand` and the shape of `builds` are unchanged. The values of
`builds` change as in §4.

- **Everyone.** Never divide by a demand of your own to get weeks short. Use `R["weekly_demand"]`, or show weeks of
  supply against target (`R["wos"]`, `R["target_wos"]`): the plan now agrees with it.
- **Deck (`docs/deck/`).** `object/dump_base.py`: replace `wd` (the 121-week mean) with
  `R["weekly_demand"].loc[ix[s], t]` per week. `dump.py` and `object/dump_event.py` call `engine.decide` with the
  121-week mean: pass `engine.window_demand(tu, tw).loc[keys]` instead, or they will not match `run_case`.
  Slide 4's builds change as in §4. Call the measure "weeks short of target", with the footnote "units short ÷
  average forecast over the target's weeks". The 6 Sep 2027 date for the MTB carbon line holds.
- **UI (`planner3/`, `planner2/`, `app/`).** No API change; SKU-by-week builds on three lines move, nothing else.
  `app/views/validation.py` captions the shortfall as "weeks of average demand": it is now the target window's
  demand. Consider showing on-time fill or open orders beside "position-weeks below target" (§3).
- **Object.** Nothing.

## 7. How it is checked

- `tests/test_engine.py`: the LP by hand on the tiny chain; `forward_sum` with part weeks agrees with
  `weeks_of_supply`; `window_demand` with its floor; a Series divisor equals the same number every week; the MTB carbon
  SKUs level on the planner's measure; a 15.5-week target agrees with weeks of supply in every position-week;
  a window with no demand still plans.
- `tests/test_base_case.py`: the frozen base plan (TIMING re-pinned for D23; BUILT, 278 and the dates unchanged).
- `tests/test_events.py`, `tests/test_baseline.py`: events and the LP against the planner's rule.
- D23 was validated against an independent build of the LP from the previous commit's source with the divisor
  computed by hand: zero difference in runs and objective in A, B, E1, E2 and E3. Six faults were planted in a copy
  of the repo (old divisor in each caller, part weeks cut, no floor, week 1's divisor used every week, a wrong divisor
  formula), and the tests caught all six.
