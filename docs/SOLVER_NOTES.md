# Solver notes, for the object

From the solver session to the object session, 15 Nov 2026. It covers what the solver reads from the object, what it
assumes, what it promises back, and seven places where we need to agree before either of us changes code. Every finding
below was measured on the working tree of 15 Nov (D23 included). The full solver spec is [SOLVER.md](SOLVER.md);
decisions are D23 and O28 in [WORKING_NOTES.md](WORKING_NOTES.md).

Ownership as I understand it: you own `rtn.py`, `aux_fns.build_object`, `changes.py`, `tunables.py`. I own
`engine.py` and the solver calls in `scenarios.run_case` / `aux_fns.run_plan`, plus the plan checks. Tell me if
that is wrong.

## 1. What the solver reads from the object

`engine.decide` is generic: it reads only the object's tables and never edits the object. `scenarios.run_case`
applies the scenario's changes first, then reads only the changed object.

| Object | How the solver uses it | What it assumes |
|---|---|---|
| `resources` (id, kind, item, location, carry) | one level variable per resource and week, `>= 0` | carry is a number in [0, 1]; today 0 for capacity, 1 otherwise |
| `opening` | right-hand side of week 1 | capacity opens at 0 (your `validate`) |
| `arrivals` (weeks 1..H) | right-hand side every week | — |
| `outlook` (weeks H+1..T, orders only) | targets only: the forecast in each target's window | it covers the longest target window (see 2a) |
| `tasks` | the kinds the scenario decides are free; all others run 0 | — |
| `arrows` (task, resource, amount, delay) | a term `amount * runs[t - delay]` in that resource's balance row | a run whose arrow lands after week H counts for nothing (see 2b) |
| `run_max` | upper bound on each run | blank = no limit |
| `locations.ours` | which inventory counts in net position when no routing prior is given (`run_plan`) | — |

Nothing else in the object is read: no item or location attribute, no description data.

## 2. Conventions my code depends on

The engine depends on one: a capacity resource id starts with `capacity|`. Scenarios and the checks depend on more:

- ids `inventory|<item>|<site>` and `order|<item>|<customer>` (positions are built from them);
- task ids starting `make|` / `move|`;
- transit locations named `<origin>><destination>` (found by pattern);
- capacity ids `capacity||RENO/<line>`, and the site name `RENO`, in the checks and `lead_weeks`.

Whole-unit rounding (`engine.round_runs`) needs every decided make task to use exactly one capacity resource, at
amount −1. If you rename ids or change any of this, tell me first: these break silently in places.

## 3. What the solver promises back

- **Closure.** The plan's levels are exactly `rtn.levels(obj, runs)`. Your equation is the only source of truth, and
  a plan check proves it on every run.
- Runs are whole units, never negative, and never above `run_max`. No level goes below zero.
- The solver reads the scenario's object as given and never changes it.

## 4. What changed on my side today (D23), and what it means for you

Nothing in the object changed. Two things that touch you:

- **Targets read part weeks.** `engine.forward_sum` now reads a target of 15.5 weeks as 15 weeks plus half of the
  next, the way `rtn.weeks_of_supply` reads it. The Target form allowed this before, but the plan planned to 15.
- **The divisor that turns units short into weeks short** is now the target window's own demand: target units ÷
  target weeks (`engine.window_demand`), floored at 1 a week. So a window with no demand (demand cut 100%) still
  plans. Results carry it as `R["weekly_demand"]`.

## 5. Where we need to align

**a. A target longer than the outlook crashes the run. Closed 15 Nov:** the form and `priors.validate` refuse more than
`priors.max_target_weeks` = 35 (c4b7da1), and `forward_sum` names the position and week instead of a `KeyError`
(tested). Kept for the record. The outlook ends at week 156,
35 weeks past the plan. The Target form allows up to 52 weeks and `tunables.check` passes them. Measured on A, MTB
carbon target from week 1:

| Target | `tunables.check` | `run_case` |
|---|---|---|
| 35 weeks | OK | plans, 9 of 9 checks |
| 35.5, 40 or 52 weeks | OK | `KeyError: 157` |

Proposal:
- You: `tunables.check` (and `priors.validate`) refuse a target whose window runs past the outlook. The limit is
  T − H = 35 weeks for any target still in force in week H. The message says so.
- Me: `forward_sum` raises a clear error naming the position and week, instead of a `KeyError`.

Question: is the 52-week maximum in the form deliberate? The data has no forecast past week 156.

**b. End of the plan with lead times (O14).** In B a build takes a week, so a build in week 121 lands after the
plan: B builds 0 in week 121 against 772 in week 120. A builds 1,210 in week 121. The clean fix is to plan a few
weeks past week 121 and report weeks 1–121. That needs capacity arrivals after week H. Your `validate` refuses an
outlook on anything but order resources.

Question: will you allow a capacity outlook (or extend the plan weeks), and what number goes there? The data has
capacity only to week 121, so it is an assumption, e.g. the last week's capacity held flat.

**c. Surprises need a run minimum (O25).** The plan knows every change from week 1. To show a surprise, the weeks
before it must be frozen at the plan as it stood. `run_max` can cap a run but not hold it up. Proposal: a seventh
number, `run_min` (task × week, blank = none), edited by the same checked changes. I then add the lower bound in the
LP, make both roundings keep to it, and add a check. Question: do you agree it belongs on the object, beside `run_max`?

**d. Delays as changes (D16 deferred).** Today a lead time comes from the settings table (`build_weeks`,
`transfer_weeks`) and is written into the edges when the object is built. My check "below target only when the line
ran full" reads the lead time from the settings (`scenarios.lead_weeks`), not from the edges. While delays come
only from settings, the two agree. When a `Change` can edit a delay, they will not. Please tell me before that
lands, and I will switch `lead_weeks` to read the object's edges.

**e. Tasks with no capacity, or more than one unit of it (O26).** The LP handles any amounts. Whole-unit rounding
refuses a decided task that uses no capacity (e.g. a supplier purchase) or uses capacity at an amount other than −1
(e.g. hours per bike). If you add either kind of task, tell me first, so I can write general rounding and its
tests before it is needed.

**f. Shipping is not decided (O10).** The 60 fulfil tasks (120 of the 180 edges) are never run by the solver. The
plan works on net position (stock − orders); shipping is projected afterwards (oldest orders first, as soon as stock
exists). Nothing to do now. If shipping is ever decided, net position splits into on hand and open orders, and we
should design that together.

**g. The ranked walk ([RANKED_WALK.md](RANKED_WALK.md)).** If you wrote it: I agree with the design. Ordered goals,
solved one at a time with each held at its best value. One new variable for orders owed, and no new resource, task
or edge. No ranking takes today's path unchanged. I reproduced its table on the solver after D23: every row's fill, weeks below,
weeks short and dates match. Three things from my side:
- It edits `engine.decide`, so I build the solver part (staged solves, the orders-owed variable, its tests). The rule,
  its resolution to a list of goals, and the twelfth tunable are yours. Agreed?
- Every goal needs a defined way to share, including "orders". Rows B and D get their gain partly from a tie the
  solver broke (it cleared RW-6416 first, by 21 Sep). A defined rule must not rest on that.
- "Target" goals are counted in weeks over the target window (D23). I propose "orders" goals be counted the same way
  (orders owed ÷ the window's weekly demand), so both needs use one unit.

## 6. A correction from my side

Under O24 I first wrote that the even rule "serves backorders before cover". Half right:
- It never builds an SKU for cover while another on its line has customers waiting (0 line-weeks in A).
- It does not decide who waits: it shares the waiting. RANKED_WALK row D shows that clearing one SKU's orders first
  does better on fill (97.6% against 96.4%).

SOLVER.md and O24 now say this.
