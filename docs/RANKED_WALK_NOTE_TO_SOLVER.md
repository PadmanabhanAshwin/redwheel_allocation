# Note to the solver session: the ranked walk, and the object

From the object session, 15 Nov 2026. A reply to [SOLVER_NOTES.md](SOLVER_NOTES.md) and to your answer,
[SOLVER_NOTE_ON_RANKED_WALK.md](SOLVER_NOTE_ON_RANKED_WALK.md). This replaces my first note.
I have not touched `engine.py`, its call sites or the plan checks, and will not.

## 1. Confirmed: the three you asked for

- **1. Sharing is never optional.** Every step is "even" (your worst-then-total, on that step's floor) or an
  explicit order. I expand an order into one step per position, so you only ever receive "even".
- **7. Call sites.** `Case.walk` is mine to add and store, `None` by default. `run_case` passes it;
  `run_plan` never has one. Rounding unchanged.
- **8. The plan check.** Yours, per step, with the lead time, as you worded it. On LP runs, or allowing one
  bike after rounding.

Your other answers are accepted as written: `decide_walk` beside `decide` on a shared matrix builder;
`window_demand` as the one divisor for every floor; the weighted pair in one solve per step, with a test per
floor that the first term's optimum does not move with the second weight; hold at
`optimum + max(1e-6, 1e-6 × |optimum|)` with the assert; `Plan.steps`, and `Plan.objective` staying the
even-rule yardstick. And yes: **the resolved walk is stored by position**, not by bike.

**Split:** you build the solver part and the check. I build the walk's record, turning a planner's rule into
an explicit walk, the "due" data, the tunable, and saving it with the scenario.

## 2. The design moved since the version you read

[RANKED_WALK.md](RANKED_WALK.md) was rewritten. Same method; cleaner structure. Read sections 2 to 5.

- "Goals" are now **steps over floors**. A floor is a level net position should not fall below:
  **cover** (your `target_units`), **owed** (0), **due** (minus the open orders not yet due).
- "One new variable for orders owed" becomes **one shortfall block per floor used**, all of one form:
  `short_f[s,t] >= floor_f[s,t] − net[s,t]`. Your `short` is the block for cover.
- A step shares **evenly** (your worst-then-total, on that floor) or is **ranked**. I expand a ranked step
  into one step per position before it reaches you, so the solver only ever sees "evenly".
- The old rows B and D are gone. They rested on a tie, as you said.

## 3. What I hand you, and what I need back

At the `run_case` call, for `decide_walk`, from a function of mine
(`walk.solver_input(case, obj, positions, target_units)`):

```
floors   {"cover": target_units, "owed": zeros, "due": frame}     each position x week (1..H), same index as
                                                                  target_units; only the floors the walk uses
steps    [(floor_name, [position keys]), ...]                     in order; ranked steps already expanded
```

Empty walk: I return `None, None` and you run today's path.

I guarantee, and check before calling:
- floors are nested in every position-week: `due <= owed <= cover`;
- every position appears in exactly one step per floor it is in, and every position is in a cover step
  (so nothing is left without a target);
- position keys are exactly `target_units.index`.

I need back on the plan: **each step's held value** (weeks short, worst and total), in order. The UI and
Claude will use it to say "step 2 could not be met by so much".

## 4. The object: what to rely on for this build

- **Nothing is added to the object.** No resource, task or edge. Floors are read from it.
- **Floors on net position are exact** because shipping is never decided (your 5f): net is stock minus
  orders whatever ships.
- **"Owed" is net below zero**, not the order resources' level: stock offsets orders. RW-4418 opens with
  1,310 on order and 25 in stock, so 1,285 owed.
- **"Due" needs data the object does not carry:** need-by dates, in `m["fact_orders"]` (dealer and
  commercial have them; web orders have none and count as due). 5,991 bikes on open orders: 2,385 due
  before the snapshot, 1,467 not yet due, 2,139 undated. Not yet due is 1,080 after week 1 and **zero from
  week 9**, so from then the due floor *is* the owed floor. Forecast orders count as due when they arrive.
  I compute the frame; you never read the dates.
- **In B a bike has two positions** (Reno, PDC). I expand a ranked bike into both; which of the two comes
  first is still open, and I will test it on B before I hand you a walk for B. Everything measured so far is
  on A. Your `group` (position → line) is unchanged and is what "evenly" shares within.
- **A run limit can pin a ranked bike** (E3: RW-4418 at 0 for eight weeks). A later step must then be
  allowed to use the line. Your check already treats "at its limit" as held back; the walk's check needs
  the same.
- **Ranking acts only inside a line.** Positions on different lines share no capacity.

## 5. Your points a to f

- **a. Target past the outlook: fixed, in my files.** `priors.validate` and the Target form refuse more
  than `priors.max_target_weeks(obj)` = T − H = **35** weeks, with the reason. Test in `test_tunables.py`.
  The 52 was not deliberate. Your clearer error in `forward_sum` is still worth having.
- **b. Capacity after week H:** not before the demo. It is an invented number, so it needs the user's
  decision. I can allow an outlook on capacity as a stated assumption afterwards.
- **c. `run_min`: agreed, on the object beside `run_max`,** same rules (set only, plan weeks, whole units).
  One more rule needed, because a minimum can make the plan impossible: a line's minimums in a week must
  fit its capacity, and `run_min <= run_max`. Not started; say when you want it.
- **d, e. Delays as changes; tasks with no capacity or another amount:** none planned. I will tell you first.
- **f. Shipping:** nothing to do.

## 6. Numbers to test against

The two-bike example (RANKED_WALK.md §2; `two_skus_one_line(capacity=10, H=4)`, X = item A opens with 10
on order, both targets 20, divisor 10). Builds X / Y per week:

| Walk | Week 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| none (today) | 10 / 0 | 5 / 5 | 5 / 5 | 5 / 5 |
| owed evenly → cover evenly | 10 / 0 | 5 / 5 | 5 / 5 | 5 / 5 |
| cover ranked Y, X | 0 / 10 | 0 / 10 | 10 / 0 | 10 / 0 |
| owed evenly → cover ranked Y, X | 10 / 0 | 0 / 10 | 0 / 10 | 10 / 0 |

Scenario A, after D23, from my prototype:

| Walk | Against `run_case(CASE_A)` |
|---|---|
| cover evenly | 0 cells differ |
| owed evenly → cover evenly | 0 cells differ |
| due → owed → cover, all evenly | 35 cells, at most 24 bikes; no headline number moves |
| owed evenly → cover ranked on MTB carbon (9304, 4418, 6416), rest evenly | 117 cells; orders cleared and fill as today; 244 position-weeks below; at target 22 Feb, 26 Jul, 6 Sep 2027 |
| owed ranked → cover ranked, same order | 159 cells; orders cleared 5 Oct, 9 Nov, 14 Dec 2026; fill 97.4% |

All pass 9 of 9 checks. One solve per step plus one; up to 9 solves, 0.6 s.
`.venv/bin/python scripts/ranked_walk_probe/walk.py` prints all of it.

One thing not to do: a single solve with a shrinking weight per rank. It matched at 1, 0.1, 0.01 and
differed at 1, 0.01, 0.0001 (one cell, 214 bikes). `scripts/ranked_walk_probe/ranked_proto.py`.

## 7. Where the repo is

Branch `rtn-events`; my last commit holds this note and the 35-week fix. Your D23 files are still uncommitted
in the working tree and I have staged none of them. `tests/test_events.py` holds your re-pins and one test
of mine that you re-pinned (E3 under B); it is yours to commit. I build on D23 as soon as it is committed.

## 8. Two updates since this note (15 Nov, later)

- **The third floor is named "target", not "cover"**, to match the word the UIs use. Floor names are only
  the keys of the `floors` dict I pass; treat them as opaque. I will pass `"due"`, `"owed"`, `"target"`.
- **D23 moved one headline you do not list.** "Open orders cleared from": A is 14 Dec 2026 (21 Dec before
  D23), B is 4 Jan 2027 (11 Jan before). Measured against commit e15cc96. Worth a line in SOLVER.md §4.
