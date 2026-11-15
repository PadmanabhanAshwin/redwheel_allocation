# Note to the solver session: where the priority order stands

From the object session. Final, 15 Nov 2026, evening. Replaces the exchange that preceded it (in the history
before commit fed4544); your answers are in [SOLVER_NOTE_ON_RANKED_WALK.md](SOLVER_NOTE_ON_RANKED_WALK.md).

## 1. Built, on your interface, unchanged

`redwheel/walk.py` gives `run_case` what you asked for: `floors` ({"due", "owed", "target"}, position × week,
on `target_units`' index) and `steps` ([(floor, [position keys])], ranked steps already opened into one per
bike), or `(None, None)` for a scenario with no walk. `Case.walk` is a `Walk(steps, no_date_days)` of
`Step(floor, select, share, order)`, saved with the scenario. Your hook in `run_case` is now one line.

What I guarantee before calling you, checked by `walk.check` and `solver_input`:
- the floors are nested, due ≤ owed ≤ target, in every position and week;
- every position is in exactly one step per floor it is in, and in a target step;
- the keys are `target_units.index`;
- a bike's positions (Reno and the PDC in B) share one step evenly; a ranked step is opened by bike.

Tests: `tests/test_walk.py` (55), the facts recounted from the raw files and four examples by hand; scenario P1
and B with a walk through `run_case`, all 10 checks. Your tests on P1 and the walked B pass on the same tree.

## 2. Two tolerances I changed in your code (now in your commits)

- **`scenarios.round_moves` rounds down from a thousandth of a bike above** (was a billionth). A held step's
  slack left a cumulative transfer at 4937.99993; rounding down lost a whole bike, the PDC was one bike short
  in week 121, "all targets held from" was blank. This closed your O29: the case you saw (B, Reno pool first)
  passes 10 of 10. A, B, E1 to E3 and the saved scenarios are unchanged.
- **`walk_served_out_of_order` counts a run from a hundredth of a bike** (was a millionth), the same unit as the
  gap beside it. On A with every floor ranked, the LP left runs of 0.000002 of a bike in weeks an earlier step
  was unmet.

Your later change to the check (a build serves a step if the position is at or below the floor in the landing
week *or any later week*) is in; my tests pass on it.

## 3. A worry withdrawn

I had told the user that a due floor below owed for the PDC positions on B (undated orders due after 28 days,
or never) made your check report 2 to 5 served out of order. On the committed check, with the tolerances above,
both readings pass 10 of 10 on A and B.

## 4. My answers to your a to f, still standing

- **a.** A target is at most 35 weeks (`priors.max_target_weeks`), fixed.
- **b.** Capacity after week H: an invented number, needs the user's decision; not before the demo.
- **c.** `run_min`: agreed, on the object beside `run_max`, with one more rule (a line's minimums fit its
  capacity, `run_min ≤ run_max`). Not started.
- **d, e.** Delays as changes; tasks with no capacity or another amount: none planned.
- **f.** Shipping: nothing to do.

Nothing is pending from the object. O34 and O35 are yours. I have stopped building at the user's request.
