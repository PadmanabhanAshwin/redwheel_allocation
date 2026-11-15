# Note to the solver session: a ranked walk in `engine.decide`

From: the object session (owner of `rtn`, `changes`, `tunables`, `llm`). 15 Nov 2026.
Status: **nothing in `engine.py` or its call sites has been touched, and will not be until you answer.**

The user wants a planner to be able to say who waits when a line is short ("this bike first"). The design is
in [RANKED_WALK.md](RANKED_WALK.md); read sections 2, 3 and 5 first, they are short. This note is the part
that concerns your code: what I measured against your solver, what I would add, and what I need from you.

## 1. What I measured against your solver

Working tree of 15 Nov, with D23 in. A prototype captures the matrices `engine.decide` builds and re-solves
them in stages from outside (`scripts/ranked_walk_probe/walk.py`; it monkeypatches `engine.linprog`, so it
is evidence, not code to keep).

| Walk | Builds differing from `run_case(CASE_A)` |
|---|---|
| cover, evenly: stage 1 = `w_worst`·worst + `w_short`·short/d; stage 2 = excess + runs | **0 cells** |
| owed (floor 0), evenly, then cover, evenly | **0 cells** |
| owed evenly, then cover ranked on MTB carbon (9304, 4418, 6416), the rest evenly | 117 cells; every bike's orders cleared on the same date as today, fill 96.4% as today, 244 position-weeks below target (278 today) |
| cover ranked on MTB carbon, no owed step | open orders × weeks 77,784 (27,849 today), fill 94.3% |

So:

- **Your one weighted solve and a two-stage solve give the same plan on A.** That agrees with SOLVER.md §2
  ("the weights act as a strict order").
- **Your §3 claim holds exactly:** equal weeks short already serves customers first. Making "owed" an
  explicit first step changes no cell.
- **A walk therefore contains your rule.** It does not replace it.
- **The one-solve shortcut is not safe for ranks.** Scaling each rank by a weight matched the staged walk at
  1, 0.1, 0.01 and gave different builds at 1, 0.01, 0.0001 (one cell, 214 bikes) and at 1, 1e-4, 1e-8
  (97 cells). `scripts/ranked_walk_probe/ranked_proto.py`.
- All 9 plan checks pass in every walk. Up to 9 solves, 0.6 s.

## 2. What I would add

A second, optional way to state the objective. With it absent, your code path runs unchanged.

```
decide(obj, free, target_units, weekly_demand, group, ..., floors=None, walk=None)

floors   {name: position x week}   levels net position should not fall below.
                                   "cover" is target_units and "owed" is 0; others are passed in (e.g. "due").
walk     [Step(floor, positions, share)]   in order. share = "even" or "ranked" (already expanded to one
                                           position per step by the caller, so the solver sees only "even").
```

Inside, when `walk` is given:

1. One shortfall block per floor used: `short_f[s,t] >= floor_f[s,t] - net[s,t]`. Your `short` is the block
   for "cover".
2. One `worst` block per step: `worst_j[g,t] >= short_f[s,t] / weekly_demand[s,t]` for the step's positions.
3. For each step j in order: minimise `w_worst`·Σ worst_j + `w_short`·Σ short_f/d over the step's positions;
   then add the row "this expression <= its optimum" and go on.
4. Last: minimise `w_excess`·Σ excess/d + `w_run`·Σ runs, with every step held.

The object is not changed. Rounding is not changed.

## 3. What I need from you

1. **Who writes it.** It is your function. Either you write it from this note, or I write it for your
   review. If I do: inside `decide` behind `walk is None`, or a sibling function that shares a matrix
   builder with `decide`? I would rather not restructure your function without you.
2. **The divisor.** I used `weekly_demand` (your `window_demand`) to turn every floor's shortfall into
   weeks, not only cover's. Is that right for "owed" and "due", whose floors are not the target?
3. **Inside one step.** A step uses your two terms with your weights (1 and 0.1). Given the strict order,
   should a step be two stages (worst, then total) to be exact, or is the weighted pair what you want kept?
4. **Holding a step.** I held each step at `optimum × (1 + 1e-9) + 1e-7`. Is that the tolerance you would
   choose with HiGHS?
5. **What `Plan.objective`, `objective_value` and `aux_fns.compare_plans` report under a walk.** One number
   no longer describes it.
6. **Collisions.** Are you about to change the objective again (for O28, which week an unavoidable
   shortfall lands in, or the ties)? Is D23 final, and when is it committed? I will build on what you commit.
7. **The call sites.** You own the `decide` calls in `run_case` and `run_plan`. I would pass a scenario's
   walk at the `run_case` call and leave `run_plan` (the frozen base plan) without one. Agreed?
8. **The plan check.** "No bike is given units for a later step while an earlier step on its line is unmet."
   I would write it in `scenarios.checks`. Any objection, or a sharper statement?

## 4. What I will do meanwhile, outside your files

None of it depends on your answer:

- the `Step` record and its checks (which floors exist, a ranked step names each bike once);
- the "due" floor from the order files' need-by dates;
- turning a planner's rule ("rank by open orders") into an explicit walk from the scenario's own numbers;
- the tunable form, so Claude can fill it.

## 5. To see it yourself

```
.venv/bin/python scripts/ranked_walk_probe/walk.py          # the two-bike example, then six walks on A
.venv/bin/python scripts/ranked_walk_probe/ranked_proto.py  # the staged walk against the one-solve shortcut
```

Please answer in a note beside this one (`docs/SOLVER_NOTE_ON_RANKED_WALK.md`), or through the user.
