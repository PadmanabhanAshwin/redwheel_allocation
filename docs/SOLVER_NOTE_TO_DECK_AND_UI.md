# Solver note to the deck and Streamlit sessions

From the solver session, 15 Nov 2026. Read with the object session's [NOTE_TO_DECK_BOT.md](NOTE_TO_DECK_BOT.md) and
[NOTE_TO_STREAMLIT_BOT.md](NOTE_TO_STREAMLIT_BOT.md); I use their words. Spec: [SOLVER.md](SOLVER.md).

## 1. Two solver changes today

**D23 (committed, 0100998): weeks short is counted over the target's own window.** The number that turns units
short into weeks short is now target units ÷ target weeks per bike and week, so the solver's measure agrees with the
weeks of supply you show. What moved, all scenarios: the SKU mix by week on three lines (A: 651 bikes in a different
week, 544 on MTB carbon, the last in week 53); "open orders cleared from" a week earlier (A 14 Dec 2026, B 4 Jan 2027,
E2 14 Dec). Unchanged: every SKU total, every line's total each week, every "targets held from" date, position-weeks
below target, on-time fill, 9 of 9 checks.

**D24 (in my working tree, committing today): a priority order in the solver.** `engine.decide_walk`: the plan as
ordered **steps** over **floors** (due, owed, target), each step held at its best before the next. Today's rule is the
one-step walk and gives the same plan cell for cell (a permanent test now, not a prototype). It reaches a scenario
through `Case.walk`, which the object session is building; until that lands no UI can run one, and the deck should
show it only as the object session's note says (the two-bike example and the opening floors; the ranked results on A
are pinned tests, so their numbers are final, but hold them until the user has seen the feature).

## 2. What to read, and from where

| You want | Read | Not |
|---|---|---|
| weeks short of target, for a bike and week | `R["target_wos"] − R["wos"]`, or units short ÷ `R["weekly_demand"]` | units short ÷ any average you compute; the 121-week mean |
| the plan checks | `scenarios.checks(R)`; count them, do not write 9 or 10 | |
| a walked scenario's result | `R["walk"]` (None when there is no walk); `R["lp"].steps`: per step `floor`, `positions`, `worst`, `total` (weeks short at its best, in order) | `R["lp"].objective`, which stays the even rule's score for every plan: a yardstick, label it so |
| the tenth check | the last row of `checks(R)`, "Walk: a later step is served only when every earlier step on the line was met or held back" | |

Deck scripts: `docs/deck/dump.py` and `docs/deck/object/dump_event.py` still call `engine.decide` with the 121-week mean
and will not match `run_case`; pass `engine.window_demand(tu, tw).loc[keys]`. `dump_base.py` should read
`R["weekly_demand"]`. Slide 4's week-by-week MTB carbon builds are now 269 / 146 / 144 (RW-9304), 79 / 143 / 142
(RW-4418), 27 / 86 / 89 (RW-6416) for weeks 1–3; the 6 Sep 2027 date holds.

## 3. What the solver decides, in one line each (for slide 4 and the "why believe it" screen)

- A line below target runs full: capacity sets every date. The solver does not change that.
- On a full line the solver sets the mix: every bike on the line equally short in weeks, so customers are never
  made to wait while another bike on that line gets safety stock. It does not choose *who* waits; that is the priority
  order (D24).
- It builds ahead of what it knows (E3: 1,394 bikes before the frames gap); a rule without look-ahead cannot.
- It does not decide shipping (projected afterwards), does not know surprises (every event from week 1), and sees
  nothing after week 121.

## 4. Words

Theirs, plus three of mine: **weeks short** (of target; "units short ÷ average forecast over the target's weeks" if
someone asks), **the even rule** for today's objective when it must be named at all, **at its best** for a step that
has been minimised and held. Never "fairness term", "LP objective" or "the divisor" on a slide or a screen.

## 5. 15 Nov, late: two more scenarios, and the one file to read

**Every number the deck quotes is in `docs/deck/deck_numbers.json`**, written by `scripts/deck_numbers.py` from a run
of every scenario through `run_case` with every plan check (nine scenarios: A, B, E1–E5, P1, B+E3; all checks pass).
Per scenario: `scorecard` (bikes built, all targets held from, open orders cleared from, on-time fill, position-weeks
below target), `held_by_line`, `per_sku` (at target, orders cleared, weeks below, bike-weeks above target),
`mtb_carbon_builds_by_week` and `mtb_carbon_line_by_week` with `mtb_carbon_capacity_by_week`, `weeks_of_supply_mtb`
with `target_weeks_mtb`, the `changes` in plain fields, a walk's `walk` steps, and `against_A` (bikes built diff, SKU
totals diff, cells that differ, the line's weekly diff, other lines identical). `_meta.weeks` maps plan week to its
Monday. Regenerate with `PYTHONPATH=src .venv/bin/python scripts/deck_numbers.py`. If a number is not in the file,
it is not final.

Two scenarios added for the "something changes" part, both pinned by tests:

| | Change | What the plan does |
|---|---|---|
| **E4, a fleet order lands** | 300 RW-4418 for a commercial customer, week of 9 Nov 2026 (one number: 7 → 307) | the line is full, so the 300 are built when capacity rises (weeks 53–54); MTB carbon holds target 13 Sep 2027 not 6 Sep; every open order cleared 28 Dec 2026 not 14 Dec; fill 96.4% → 95.6%; the other lines do not move |
| **E5, RW-9304 built in lots of 50** | a fixed order quantity, the object's seventh number (121 numbers: 1 → 50) | every build of RW-9304 a whole lot (250, 150, 150, 150, 100, …); the line as full as A in every week; every line's date as A; orders cleared 21 Dec not 14 Dec; 1,744 bike-weeks of RW-9304 carried above target, the price of lots |

Story for the slide set, in this order: a line down (E1, costs 4 weeks), demand up (E2, 191 bikes and a week),
frames late (E3, absorbed), a fleet order (E4, customers wait), lots (E5, same dates, stock above target). One
sentence each: "we changed N numbers, this moved, nothing else did."

Words: "fixed order quantity" or "built in lots of 50"; not "FOQ" on a slide. Say the LP plans the flow and the
build plan is cut into lots; do not say the solver chooses lot timing (the exact version is later work).
