# Solver's answer on the ranked walk

From the solver session to the object session, 15 Nov 2026. Answers [RANKED_WALK_NOTE_TO_SOLVER.md](RANKED_WALK_NOTE_TO_SOLVER.md).
My own notes to you, on everything other than the walk, are in [SOLVER_NOTES.md](SOLVER_NOTES.md); item 5a there
(a target over 35 weeks crashes the run) needs an answer before the demo.

Short version: I agree with the design, I will write the solver part, and the walk may build on D23 as it stands.
I ran `walk.py` on the current tree and every number in your note reproduces.

## 1. One thing to fix in the design before it is built: how a step shares

Your walk 2 ("owed evenly, then cover evenly") changes 0 cells. The earlier prototype's row D ("everyone's orders
first, then target evenly", `ranked_proto2.py`, now removed) gave a different plan: fill 97.6% against 96.4%, with
RW-6416's orders cleared on 21 Sep instead of 14 Dec. Both runs are right. They define the owed step differently:

- walk 2 minimises, per line and week, the largest backlog in weeks, then the total (your "even": my two terms);
- row D minimised the total backlog only, with no per-line worst term.

With the total alone, the solver clears whichever SKU is cheapest to clear first (the smallest). That is the tie you
noted in row B, and it is where row D's fill gain came from. So the two facts to carry into the design:

- "Owed, shared evenly" is already what today's rule does. Adding it as a step changes nothing (your walk 2).
- A gain in fill comes only from a *stated* order of who is cleared first (walk 5: 97.4%, orders cleared 5 Oct, 9 Nov,
  14 Dec). A step with no sharing rule gets a gain the planner did not ask for.

So: every step must carry a sharing rule, "even" or an explicit order, and "even" always means worst-then-total.
Your `Step(floor, positions, share)` already has the field; this just says it is never optional. This also corrects
what I wrote under O24 and in SOLVER.md §3 (now fixed): the even rule never builds cover while a customer waits on
the same line, but it does not decide who waits.

## 2. Answers

**1. Who writes it.** I do, from your note. A sibling `decide_walk(obj, free, target_units, weekly_demand, group,
floors, walk, ...)` sharing one matrix builder with `decide`, so `decide`'s behaviour stays byte for byte (the
frozen base case guards it). Not inside `decide` behind `walk is None`: the staged loop and the extra blocks would
double the function. I will refactor the builder out first, run the full suite, then add the walk. Timing: after the
demo on 16 Nov unless the user wants it on the day; it is a few hours with tests.

**2. The divisor.** Yes: one unit for every floor, `window_demand` (target units ÷ target weeks). For "owed" the
shortfall below 0 in those units is the backlog in weeks of the window's demand; for "due" likewise. Two floors on one
position are then comparable, and a step's "even" means the same thing whatever its floor.

**3. Inside one step.** Keep the weighted pair (1 and 0.1) in one solve per step. On A the first term's optimum is the
same at w_short 0.1, 0.01 and 0.001, so the pair is already exact for cover. Two stages per step would double the
solves for no change. One test per new floor should check the same (solve the step at two weights, same first-term
optimum), so the claim is measured, not assumed.

**4. Holding a step.** `optimum × (1 + 1e-9) + 1e-7` is fine. HiGHS's own feasibility tolerance is 1e-7, so an
absolute slack below that is a coin toss. I would write it as `optimum + max(1e-6, 1e-6 × |optimum|)` so the
number is readable, and after each solve assert the held expressions are within that slack of their optima
(it catches a wrong row index, which is the fault most likely here).

**5. Reporting.** `Plan` gets `steps`: a list of (step name, optimum in weeks), one per solve, plus the final
excess/runs value. `Plan.objective` and `objective_value` stay what they are: the score on today's even rule. That is
a yardstick every plan can be scored on, including a walked one, which is what `compare_plans` needs; it is not the
walk's objective, and the UI should label it so. A walk's own record is `steps`.

**6. Collisions.** D23 is final. I am not changing the objective for O28 (which week an unavoidable shortfall lands
in) or for ties before the walk exists; both belong in it or after it. D23 is uncommitted only because the user has
not asked for a commit; I recommend committing it now so you build on it. The files are listed in
WORKING_NOTES D23.

**7. Call sites.** Agreed: `run_case` passes the scenario's walk (a new `Case.walk`, yours to add and store, None by
default); `run_plan` never has one. `scenarios.round_moves` and `engine.round_runs` take the LP runs as they do now.

**8. The plan check.** Agreed, in `scenarios.checks`, but per step, not per bike, and with the lead time:

> For each step i, a position s in it below its floor at t, whose feeding tasks were not at their run limit in week
> u = t − lead: every make task that ran in week u on the same capacity must have served a position of step i or
> earlier, i.e. a position it feeds that is at or below that step's floor in the week the run lands for it.

(Second correction, on B: the test is on what the capacity was used for, not on which position a task is named after.
In B one make task feeds a bike's Reno and PDC positions, and building at Reno in week 1 is how the PDC's owed
bikes are served in week 3. With that, "PDC pool first" on B passes 10 of 10.)

(Corrected while building: my first wording, "no position in a later step ran", flagged 98 pairs on the correct walk,
because a position in the owed step is also in a later cover step; a run on it in a week it is owed serves the owed
step.)

(The run-limit clause is from your second note: a pinned bike, as RW-4418 in E3, must let later steps use the line.)

Per step, because a lower-ranked bike built for *owed* while a higher-ranked bike is below *cover* is correct in walk 4
(the owed step comes first); the earlier prototype's "87 cases" in row B were that, not violations. With the lead
time, as the existing "below target only when the line ran full" check does. Test it on the LP runs or allow one
bike, because rounding can put one unit on the wrong bike for a week.

## 3. Two things I would add to the design

- **A step that cannot be met leaves its shortfall in some week, and the walk does not choose which** (O28). The
  "held from" date follows the last one. Same as today; the walk does not make it worse, but the UI should show the
  size of the last dip beside the date.
- **The resolved walk must be stored by position, not by SKU**, or B's Reno and PDC positions of one bike end up in
  the same step with no way to rank them. Your layer 2 can do this now at no cost.

## 4. On your second note (b5c333b): agreed, with three remarks

Your handover (§3) is what I will code against: `floors` and `steps` as written, `None, None` for no walk, and
`Plan.steps` back as (step name, worst, total) in weeks, in order. The two-bike table and the five walks on A
reproduce on the current tree and will be the tests. Three remarks:

- **"Web orders count as due" is an assumption**, like "shipped" is. Label it where "due" appears, and tie it to O3:
  if Redwheel's forecast is by due week, "forecast orders are due when they arrive" is right; if by placement week,
  it is early.
- **In B, the order of a bike's two positions** is yours to test, as you say. My expectation: the position whose
  pool holds the backlog first; a ranked step with both positions in it is the safe default until measured.
- **Solve count grows with ranked positions:** ten bikes ranked on cover is twelve solves, about a second. Fine for
  the UI; say so in the form's help so nobody ranks all twenty positions of B and expects 0.1 s.

## 5. Built (15 Nov, after the user asked for it before the demo)

- `engine.decide_walk(obj, free, target_units, weekly_demand, group, floors, steps, ...)` beside `decide`, on a shared
  matrix builder (`_build`); `decide` unchanged: the frozen base case and every pinned number pass. `Plan.steps` is a
  list of `{"floor", "positions", "worst", "total"}` in order, weeks. Hold is `opt + 1e-7 + 1e-9|opt|` (your value;
  mine let the last stage drift the score by 1e-3).
- Your two-bike table and the five walks on A reproduce to the cell, pinned in `tests/test_engine.py`.
- `run_case`: `if getattr(case, "walk", None): from redwheel import walk as wk; floors, steps = wk.solver_input(case,
  obj, pos, tu)`; a non-empty `steps` goes to `decide_walk`, else today's path. The import is inside the branch, so the
  repo runs before your module exists. `R["walk"] = {"floors", "steps"}` or None. Your guarantees (floors nested,
  cover = target_units, every position in a cover step, keys = target_units.index) are what I rely on; `decide_walk`
  refuses an unknown floor, a position with no target, and an empty walk. Floor names are opaque (your §8): the floor
  equal to target_units is found by value and reuses the LP's shortfall block, whatever you call it.
- The check, per step with lead time and run limits (`scenarios.walk_served_out_of_order`), is the tenth row of
  `checks` when `R["walk"]` is set; tested on the ranked walk (0) and on the same plan claimed in the opposite order
  (caught).

Yours: `Case.walk`, `redwheel/walk.py` with `solver_input`, saving the walk with the scenario, the tunable, the UI
words. When `Case.walk` lands, `tests/test_scenarios.py` should run one walked scenario end to end through `run_case`
and check 10 of 10.

## 6. Timing

Nothing in `engine.py` for the walk until D23 is committed and you confirm 1, 7 and 8. Then: matrix builder out of
`decide` (suite identical), `decide_walk` with the tiny-chain tests from your `toy()`, the step record passed through
`run_case`, the check, and the six walks on A reproduced as tests. Every existing scenario identical, cell for cell.
