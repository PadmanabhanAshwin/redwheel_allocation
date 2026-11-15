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
