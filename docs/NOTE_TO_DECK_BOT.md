# Note to the deck session: what changed in the object, and what the slides should say

From the object session (owner of `rtn`, `changes`, `tunables`, `priors`, `llm`). 15 Nov 2026.
I do not edit `docs/deck/`. Checked against the working tree of 15 Nov and the text of `deck.html` as it
stands. The solver session's note to you is in [SOLVER.md](SOLVER.md) §6; this adds the object's side.

## 1. Lines on the slides that are now wrong

| Slide | It says | Now |
|---|---|---|
| 1 | "8 of 8 plan checks pass" | **9 of 9**. The new check: no task runs above its limit. A tenth arrives with section 3. |
| 3 | "Week 3 of the plan: 375 − 155 − 92 − 128 = 0" | **375 − 142 − 89 − 144 = 0** after the solver's change (D23). `object.html` already has these. |
| 6, "Not built yet": *Who gets scarce bikes*, "the solver would decide the ship tasks, with channel priorities" | Being built before the demo, and it is not ship tasks or channels. See section 3. |
| 6, "Not built yet": *Components, suppliers*, "No data. Would be new resources and a buy task." | Half built. See section 2. |

If the deck shows "open orders cleared" anywhere: A is **14 Dec 2026** (was 21 Dec) and B is **4 Jan 2027**
(was 11 Jan) since D23.

Slide 5 is right as it stands: 1,125 bikes, made up from 6 Sep 2027, MTB carbon at 15 weeks from 4 Oct 2027,
the other three lines unchanged, 94,429 built.

## 2. New since the deck was written, and usable

**A sixth number on the object.** Beside opening level, arrivals, carry, amount and delay: a **run limit**,
the most a task can run in a week. Parts late is a limit of zero on one make task.

**A third event, E3: frames for RW-4418 late for eight weeks from 25 Oct 2027.**
- 8 numbers change (the limit, no limit → 0).
- The plan builds the 1,394 bikes it would have made in those weeks in the five weeks before, while the
  line has room. No other bike, date or total moves.
- Solved a second way, as a separate frames supply that RW-4418 uses up, it gives the identical plan.
  This is the tested version of slide 4's "a frame supplier would be one more edge".
- Under scenario B's rules the same event is *not* fully absorbed (all targets held from 27 Dec 2027, not
  27 Sep). Say "absorbed in scenario A".

So the three events tell three stories: a line down **costs four weeks**; demand up 30% **costs one week
and 191 bikes**; parts late **is absorbed**.

**A component and a supplier, on a toy network.** One bike made from one frame, frames bought with a
two-week lead time: it plans correctly through the same object and solver with no code change. Not in
Redwheel's data, and whole-bike rounding does not cover it yet. Say "tested on a small example".

**One list of everything a planner can change.** 11 forms (`redwheel/tunables.py`): stock count, line
capacity, demand, a one-off order, build limit, transfer limit; build time, transfer time, ship from, plan
transfers, target. The README has the table.

**Claude fills the forms.** A sentence in, checked edits out; Claude never sees stock, orders or forecasts,
and never changes the plan itself. Live results, each right first time:

| The planner types | What comes back |
|---|---|
| "A line is down for the next two weeks." | A question: which line? |
| "The MTB carbon line is down for the next two weeks." | Capacity 0 for the weeks of 7 and 14 Sep 2026 |
| "The road carbon line is down for all of March 2027." | The five weeks from 1 Mar |
| Line down and demand up, in one sentence | Both events, exactly |
| "When the PDC runs short of a bike, let Reno ship that web order instead." | Cannot be done with these forms, and why |

## 3. Coming before the demo: who waits when a line is short

The user wants this shown. Design and a two-bike example that fits one slide:
[RANKED_WALK.md](RANKED_WALK.md), sections 1 to 3.

The idea in three lines:
- Every bike has one number, net inventory, and three floors under it: a customer waiting past their date,
  a customer waiting, short of safety stock.
- A planner writes an ordered list: which floor first, and which bikes, shared evenly or in a stated order.
- Today's plan is the one-line list "safety stock, shared evenly", and comes out identical, cell for cell.

Numbers so far (scenario A, MTB carbon ranked by open orders, customers served evenly first):
no customer waits a day longer than today; RW-9304 reaches target 28 weeks early and RW-4418 six weeks
early; RW-6416 as today; 244 bike-weeks below target against 278.

**These are from a prototype.** They become final when the solver session's code lands; I will tell you.
Do not print them before that.

## 4. What not to say

- "The plan builds ahead of the line outage." It cannot: the line is already full. It makes the bikes up
  afterwards (slide 5 has this right).
- "Every other week is built as in A" for E1. True of the line's total and of the other three lines; the
  three bikes on the line swap a few units around the outage.
- "A general model" without the two limits: whole-bike rounding and the scenario code are written for
  Redwheel's lines, sites and channels. The object and the solver are general.
- "The plan decides shipping." It does not: 120 of the 180 edges are shipping, and the solver never runs
  them. Orders ship as soon as stock exists, oldest first, by assumption.
- Any number for a *surprise* event. The plan knows every event from week 1 (slide 5 says so). I measured
  the difference once, before D23; it needs measuring again before it goes on a slide.

## 5. Where the numbers are held

Every number above is pinned by a test, so if a test changes, the slide is stale:
`tests/test_events.py` (E1, E2, E3 and E3 under B), `tests/test_base_case.py` (94,429, 278, the dates),
`tests/test_tunables.py` (the forms), `tests/test_llm_live.py` (the Claude table).
379 tests run offline, plus 13 against the real model.
