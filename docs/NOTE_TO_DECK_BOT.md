# Note to the deck session: what you may print, final

From the object session. Final, 15 Nov 2026, evening. Everything here is pinned by a test and runs through the
product (`scenarios.run_case`), not a prototype. Checked against commit fed4544.

## 1. The object slides: two cautions that still hold

The numbers on the five object slides check out (74 resources, 80 tasks, 180 edges; week 3 builds 142 / 89 /
144; opening owed 1,425 / 1,285 / 752 and targets 823 / 857 / 515; all three MTB carbon bikes at target 6 Sep
2027 in A).

- **"RW-4418 at Reno 247 + 142 = 389"** is the object's level, and that level never ships: the solver does not
  run the ship tasks. On-hand stock that week is 0, with customers still waiting. Add "before orders ship", or
  work the example on the line's capacity row, which has no such trap.
- **The ship task as a joint input.** True of the object, but shipping is assumed, not decided. If asked "so the
  solver decides shipping?", the answer is no. The joint input the solver does decide is the frame in item 6.

## 2. The priority order: numbers you may print

Scenario **P1** (`scenarios.CASE_P1`): scenario A with orders past their date first, then every open order, then
the target; the MTB carbon bikes reach their target in order RW-9304, RW-4418, RW-6416. An order with no date
is due 7 days after it was placed.

| | A | P1 |
|---|---|---|
| Open orders cleared, each MTB carbon bike | 14 Dec 2026 | 14 Dec 2026 |
| On-time fill | 96.4% | 96.4% |
| RW-9304 / RW-4418 / RW-6416 at target | 6 Sep 2027, all three | 22 Feb 2027 / 26 Jul 2027 / 6 Sep 2027 |
| Position-weeks below target | 278 | 244 |
| Bikes built | 94,429 | 94,429 |
| Plan checks | 9 of 9 | 10 of 10 |

- One true sentence: "no customer waits a day longer, two bikes reach their target months sooner, and the
  third is no later." Each line builds the same number of bikes every week as in A; only the mix moves.
- The same order on every floor ("their customers first too"): RW-9304's orders cleared 12 Oct 2026,
  RW-4418's 9 Nov, RW-6416's 14 Dec; fill 97.4%.
- The standing rule written as a walk (one step: target, every bike, evenly) gives A's plan cell for cell.
- The two-bike example (RANKED_WALK.md §2): yes, it is arithmetic and a test.
- The trap (target in order with no "all open orders" step): the product refuses it (rule 7). Its numbers
  (RW-6416's customers waiting until 26 Jul 2027, fill 94.3%) were measured on the prototype before the rule
  closed it; say "measured before the rule" if you print them, or leave them out.

The three opening floors, week 1 (a position starts at its net inventory):

| | Starts at | Due floor | Owed floor | Target floor |
|---|---|---|---|---|
| RW-9304 | −1,425 | −146 | 0 | +823 |
| RW-4418 | −1,285 | −123 | 0 | +857 |
| RW-6416 | −752 | −56 | 0 | +515 |

Due is minus the open orders not yet due: none from week 9. In code: `walk.floors(obj, positions,
target_units, walk)["due"]`; the starting point `R["net"].at[k, 0]`; the target `R["target_units"].at[k, 1]`.

## 3. What is on the object, in one line each

- **Six numbers**, unchanged: opening, arrival, carry, amount, delay, run limit.
- **One fact beside them, in no equation:** when the opening orders are due (`obj.due`). "Six numbers" stays
  true.
- **Three kinds of order, from the files:** web = a consumer, one bike, no date (2,139 bikes open); dealer = a
  shop restocking, a requested ship date about 3 weeks ahead (2,914); commercial = a fleet, a need-by date
  about 6 weeks ahead (938). Of the dated ones, 2,385 are past their date and 1,467 not yet due.
- **The rule for no date:** 7 days after it was placed, an assumption stated in ASSUMPTIONS.md and a number a
  planner can change (shipped web orders took 2 to 10 days, median 6).

## 4. Customer-side numbers, where they live

With `R = scenarios.run_case(case)` and `s = scenarios.scorecard(R)`: `s["Open orders cleared from"]`,
`s["On-time fill rate"]`, `s["Position-weeks below target"]`, `s["All targets held from"]`. Per bike:

```
weeks = list(range(1, len(R["obj"].weeks) + 1))
week = scenarios.held_from(R["flows"]["open_orders"][weeks] < 0.5)      # position -> first week with none waiting
date = R["obj"].weeks.set_index("t")["week_start"][int(week[k])]        # k = (sku, "CMH+RENO") in A
```

Open orders are `R["flows"]["open_orders"]`, stock after shipping `R["flows"]["on_hand"]`, at-target
`R["at_target"]`.

## 5. Claude

"On the MTB carbon line, get RW-9304 to its target first, then RW-4418, then RW-6416" gives exactly P1.
"Prioritise the MTB carbon line over the road lines" is refused with the reason (lines share no capacity).
"Put the MTB carbon bikes in a priority order" gets the question "in what order?". Seven live requests, each
right on the first attempt; the earlier six (which line?, E1 and E2 in one sentence, E3, a stock count, B from
A, a conditional rule refused) still hold.

## 6. The component and supplier test

`tests/test_generality.py`: a bike built from a bought frame with a two-week lead time; builds 3, 0, 9, 4, 4, 4
and frames bought 9, 4, 4, 4, 0, 0, worked by hand. Week 2 builds nothing because no frame has arrived
although the line has room: a make needs line capacity **and** a frame, and the scarcer one sets the pace. No
new kind of resource, task or edge, no change to the solver. Say "on a small example": Redwheel's data has no
components, and whole-bike rounding does not cover a purchase yet.

## 7. Words, and what not to say

| Say | Not |
|---|---|
| net inventory (stock − open orders) | net position |
| target | cover |
| open orders; "owed" as "open orders − stock" | backlog |
| orders past their date | due (bare) |
| step | goal, tier, level |
| priority order | ranked walk (the working name of the design) |

Do not say: that the planner UI shows the priority order (it does not yet); that the order is computed from
the data (it is a list a planner writes); "dealers before web" (a priority order ranks bikes on a line, not
channels); that the plan builds ahead of a line outage; that the plan decides shipping; any number for a
surprise event.
