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

## 6. The final run (15 Nov, night): read this, then `docs/deck/deck_numbers.json`, once

The numbers file is final. It was written by `scripts/deck_numbers.py` after the last solver change, and the script
refuses to write it unless every scenario passes every plan check and 14 consistency rules hold between the
scenarios and their changes (listed in the file under `_meta.consistency`, all "holds": true). Regenerate only if
the code changes.

| Scenario | What changed | Bikes built | MTB carbon at target | Every order cleared | On-time fill | Lines touched |
|---|---|---|---|---|---|---|
| **A** | nothing (the base) | 94,429 | 6 Sep 2027 | 14 Dec 2026 | 96.4% | – |
| **B** | web orders ship from the PDC; a week to build | 94,429 | 27 Sep 2027 | 4 Jan 2027 | 95.3% | all four (a different rule) |
| **E1** | MTB carbon line down 3 weeks (1–15 Mar 2027) | 94,429 | 4 Oct 2027 | 14 Dec 2026 | 96.4% | MTB carbon only (77 cells) |
| **E2** | RW-4418 dealer orders +30%, Jan–Mar 2027 | 94,620 | 13 Sep 2027 | 14 Dec 2026 | 96.4% | MTB carbon only (103 cells) |
| **E3** | no RW-4418 for 8 weeks (frames late), Oct–Dec 2027 | 94,429 | 6 Sep 2027 | 14 Dec 2026 | 96.4% | MTB carbon only (13 cells) |
| **E4** | a fleet order: 300 RW-4418, week of 9 Nov 2026 | 94,729 | 13 Sep 2027 | 28 Dec 2026 | 95.6% | MTB carbon only (86 cells) |
| **E5** | RW-9304 built in lots of 50 | 94,462 | 6 Sep 2027 | 21 Dec 2026 | 96.3% | MTB carbon only (225 cells) |
| **P1** | priority order: past-due orders, then all orders, then RW-9304 → RW-4418 → RW-6416 | 94,429 | 6 Sep 2027 | 14 Dec 2026 | 96.4% | MTB carbon (138 cells), road carbon (14) |
| **B+E3** | E3's frames late, under B's rules | 94,429 | 27 Dec 2027 | 4 Jan 2027 | 95.3% | MTB carbon only (16 cells vs B) |

**Three facts for the "why believe it" slide, each pinned by a test:**
1. *Optimal, proved.* Every LP solve of every scenario is certified from its own duals (feasible plan, feasible duals,
   duality gap ≤ 1e-15), and a second algorithm (interior point) finds the same optimum.
2. *The only optimal plan.* Pulled toward any other plan, the optimum does not move by more than a bike: nothing in
   these plans is an accident of the solver's path.
3. *Consistent.* Each event's footprint is exactly where its change is: E2 and E4 build exactly the bikes they add,
   E1 makes back all 1,125 lost bikes, E3 and E5 move no date, the other lines are identical cell for cell.

**Two corrections to earlier wording:**
- E1's re-mix of the three MTB carbon bikes in weeks 25–57 is the objective's doing, not a tie: with 1,125 bikes lost,
  every week until the catch-up is further from target than in A, and sharing that evenly needs a different split.
  Say "the line shares the loss", not "the solver happens to swap bikes".
- P1's ranking moves only MTB carbon (117 cells on its own). Its first step, "orders past their date first", covers
  every line and re-mixes road carbon in 14 cells in weeks 3–7 (at most 11 bikes in a cell). Say which step did what.

## 7. 15 Nov, last: R+ is the build plan (supersedes the story in §5 and the table's role in §6)

Read `docs/deck/deck_numbers.json` again, once. It now has 15 scenarios, 24 consistency rules (all hold) and
`_meta.story`, which says what to show. §6's numbers are unchanged; only their role changes.

**The story.** A ships a bike the week it is built, and no plant does that. **R** is A with a week from the line to
stock that can ship, and it shows why build time matters. **R+** gives the carbon lines two weeks and the base lines
one: it is the build plan. Both build times are assumptions, because the data has no lead times; say so once.
Stock stays pooled at Reno and the PDC, because the order files record no ship-from site. B's routing is therefore a
what-if, not the plan.

| Scenario | What changed | Bikes built | MTB carbon at target | Every order cleared | On-time fill |
|---|---|---|---|---|---|
| A | nothing (ships the week it is built) | 94,429 | 6 Sep 2027 | 14 Dec 2026 | 96.4% |
| **R** | a week to build, every line | 94,429 | 20 Sep 2027 | 28 Dec 2026 | 95.5% |
| **R+** (the plan) | carbon lines 2 weeks, base lines 1 | 94,429 | 4 Oct 2027 | 11 Jan 2027 | 94.8% |
| R+E1 | MTB carbon line down 3 weeks (1–15 Mar 2027) | 94,429 | 1 Nov 2027 (+4 weeks, as on A) | 11 Jan 2027 | 94.8% |
| R+E4 | a fleet order: 300 RW-4418, week of 9 Nov 2026 | 94,729 | 11 Oct 2027 (+1, as on A) | 25 Jan 2027 (+2, as on A) | 94.0% |
| R+C27 | closed for Christmas: 20 + 27 Dec 2027 | 94,429 | 4 Oct 2027 | 11 Jan 2027 | 94.8% |
| R+C26 | closed for Christmas: 21 + 28 Dec 2026 | 94,429 | 25 Oct 2027 | 8 Feb 2027 | 93.8% |

**The live set, on R+:** line down, fleet order, then Christmas 2027 and Christmas 2026. Deck only: B, P1, E5 (lots of 50).
Cut: E2. E1, E3 and E4 on A stay in the file for reference: R+E1 and R+E4 move exactly as far as E1 and E4 move A.

**Christmas, the pair that makes the point (one change each: every line's capacity 0 for two weeks):**
- *2027, absorbed.* The lines have room in the autumn. Each line builds ahead as late as it can: the carbon lines run
  full from 25 Oct 2027 (MTB carbon 305 → 580 a week), road base from 1 Nov, MTB base from 29 Nov. Together they build
  ahead exactly what R+ would have built in the two closed weeks: 1,928 bikes. Stock above target builds up, peaks
  in the closure (MTB carbon +1,051 in the week of 27 Dec 2027), and is back to R+'s level on every line by 10 Jan
  2028. No customer waits longer in any week, and every date and the fill are unchanged. Chart it from `builds_by_line_by_week` with `capacity_by_line_by_week`, R+ against R+C27, weeks
  55–72, plus `stock_above_target_by_line_by_week`.
- *2026, it hurts.* The lines are already full, clearing the opening backlog, so nothing can be built ahead (road
  base, the one line with room, builds 229 ahead). Only MTB carbon customers wait: from 4 Jan to 1 Feb 2027, up to 724
  bikes, 2,169 bike-weeks. Everything is delivered by 8 Feb. **December's deliveries are not hit:** those bikes were on
  the line before the closure, so with two weeks to build the closure costs January. Chart it from
  `owed_by_line_by_week["mtb-carbon"]`, R+ against R+C26.

**The most deliveries by any date, proved (for the "why believe it" slide).** For A, R, R+ and the four R+ events,
we solved for the fewest bikes any plan could leave owed, on each line in each of the 121 weeks (484 certified solves
per scenario). The plan matches it every time (`deliveries` block, `largest_gap_bikes`: 0). Say: "No plan delivers
more by any date." Do not say the solver maximises deliveries; it does not have to, because its plan already
delivers the most. A plan that builds 100 bikes later shows a gap of 100 (the test).

**Corrections and caveats:**
- §6 fact 2 becomes: "Pulled toward any other plan, the optimum moves by under 2 bikes: what the solver's tolerance
  allows." On R+ the 1.85 bikes it allows go to a build in the last week that never lands.
- With a build time, the last weeks build nothing, because their bikes would land after week 121 (R: week 121;
  R+: weeks 120–121 on the carbon lines, 121 on the base lines). End a builds chart at week 119, or label those weeks.
- Words: "two weeks from the line to stock" or "two weeks to build"; "closed for Christmas"; "built ahead". Not
  "lead-time offset" or "cutoff objective".

**For the UI:** `scenarios.R_CASES` holds R, R+ and the four R+ events. Their keys contain "+", so quote them
anywhere a key goes into a URL or a widget key. The run is `sc.run_case(case)` as for every scenario, and the proof
is `sc.most_delivered(R)` (about 7 s; precomputed in the file).
