# Solver note to the deck session: a slide on the priority order

From the solver session, 15 Nov 2026. The user wants one slide that shows the priority order ("ranked walk" in the
design). Every number below is a pinned test in `tests/test_engine.py` (commit cc6defd); use them. The planner's
form for entering an order is the object session's half and is not built yet, so say "in the solver" and not "in the
app". Words as in [NOTE_TO_DECK_BOT.md](NOTE_TO_DECK_BOT.md) §5: priority order, steps, open orders, target, net
inventory.

## 1. The idea in one sentence

The model of the world does not change; the question asked of it does. Today's rule asks one question: make every
bike equally short of target. A priority order asks a sequence: first make this group as little short as possible,
hold that, then the next, then the next.

## 2. How it works (for the "how the model becomes the plan" slide, or a box on this one)

```
 same object, same constraints (balance rows, capacity, run limits)
 step 1   minimise shortfall of the bikes in step 1     ->  solve, lock the answer as a new row
 step 2   minimise shortfall of the bikes in step 2     ->  solve with step 1 locked, lock
 ...
 last     trim stock above target
```

One LP solve per step, half a second in all. A step can only use capacity the earlier steps did not need. Textbook
preemptive goal programming, not invented here.

## 3. The two-bike example (the slide's picture)

One line builds 10 a week. Two bikes, X and Y. X has 10 customers waiting; Y has none. Both should hold 20.

| Builds X / Y per week | 1 | 2 | 3 | 4 | What a reader sees |
|---|---|---|---|---|---|
| Today's rule (even) | 10 / 0 | 5 / 5 | 5 / 5 | 5 / 5 | X's customers served first, then equal shares |
| "Y first" | 0 / 10 | 0 / 10 | 10 / 0 | 10 / 0 | Y at target in week 2; X's customers wait two more weeks |
| "Open orders first, then Y first" | 10 / 0 | 0 / 10 | 0 / 10 | 10 / 0 | customers first, then Y gets the line |

Row 3 is the one to point at: a priority order is two decisions, which need comes first (customers or target), and
which bike. Said in words on the slide: "The planner chooses who waits. The solver finds the best plan for that
choice, and a check proves the order was kept."

## 4. On Redwheel's data (one line of text, or a small table)

Scenario A, MTB carbon, order RW-9304, RW-4418, RW-6416, after every open order is cleared:

| | Even rule (today) | Priority order |
|---|---|---|
| RW-9304 at target | 6 Sep 2027 | 22 Feb 2027 |
| RW-4418 at target | 6 Sep 2027 | 26 Jul 2027 |
| RW-6416 at target | 6 Sep 2027 | 6 Sep 2027 |
| Every open order cleared | 14 Dec 2026 | 14 Dec 2026 |
| On-time fill | 96.4% | 96.4% |
| Bikes built | 94,429 | 94,429 |

Two bikes healthy months earlier, the third on the same date, no customer waits longer. If the order is applied to
the open orders as well, RW-9304's are cleared 5 Oct 2026, RW-4418's 9 Nov, RW-6416's 14 Dec, and fill rises to 97.4%.

## 5. Do not say

- that the plan is "better": it is a different choice, made by the planner, not by the solver;
- that it is in the app (it is in the solver and its tests; the form is being built);
- "fairness term", "LP objective", "ranked walk" on the slide: use "today's rule" and "priority order".

## 6. The forms a priority order can take, and what each answers (all measured, 15 Nov)

Every form below is the same mechanism: steps over floors, in order. A floor is any level net inventory should not
fall below, per bike and week; the solver treats the names as labels. Every row was run on the real solver with the
plan checks; "same" means identical to today's plan, cell for cell.

| Form | Question it answers | Scenario A, MTB carbon (order RW-9304, RW-4418, RW-6416) |
|---|---|---|
| **Rank bikes within a line** | "RW-9304 first: when does each bike reach target, and does anyone wait longer?" | at target 22 Feb / 26 Jul / 6 Sep 2027 (today: all 6 Sep); every order cleared 14 Dec 2026 as today; fill 96.4% as today |
| **Rank the open orders too** | "And clear RW-9304's customers first?" | orders cleared 5 Oct / 9 Nov / 14 Dec 2026; fill 97.4%; targets as the row above |
| **A ladder: a floor for everyone before anyone's full target** | "Nobody below half their target before any bike gets full cover." | 12 Jul / 16 Aug / 6 Sep 2027: the ranking, softened |
| **A cap: no bike more than N weeks short** | "Protect every bike to within 4 weeks of target first." | floor = target − 4 weeks of demand: 9 Aug / 30 Aug / 6 Sep 2027 |
| **Open orders before cover, shared evenly** | "Serve waiting customers before building stock." | **same as today**: today's rule already does this |
| **Overdue customers first** (the "due" floor) | "Serve orders past their date before the rest." | 35 cells move; position-weeks with a customer past their date 66 → 67; no date, total or fill moves. On Redwheel's data the 1,467 bikes not yet due are all due by week 9, when every line is far behind anyway, so this order has nothing to work with |
| **A line before other lines** | "MTB carbon before road." | **same as today**: lines share no capacity, so ranking across lines changes nothing |

Scenario B (web orders from the PDC, dealers and commercial from Reno), the one form that is new there:

| Form | Question | Result |
|---|---|---|
| **One pool before the other** | "Web customers first: what does it cost the dealers?" | PDC first: RW-4418 at the PDC at target 24 May 2027 (was 27 Sep), its orders cleared 19 Oct 2026 (was 4 Jan 2027); Reno's RW-4418 unchanged (27 Sep, 4 Jan); every target still held from 27 Sep 2027; fill 96.5% (was 95.3%); same 33,570 bikes transferred; 10 of 10 checks |

What the mechanism cannot express, so do not promise it: a priority that changes on a date; channel priority in
scenario A (one pool of stock serves every channel); batch sizes; a surprise (the plan knows the order from week 1).

For the slide, rows 1 and 3 together make the point: the planner states the order, and can state how hard it bites.
