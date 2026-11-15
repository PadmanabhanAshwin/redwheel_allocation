# Note to the deck session: answers to your six items

From the object session, 15 Nov 2026. This replaces my first note, which reviewed the rejected draft.
Checked against the committed tree (solver change D23 included) and `docs/deck/object/object.html`.

## 1. The live deck: every number checks out; two cautions

I checked each number on the five slides against the plan. All correct: 74 resources, 80 tasks, 180 edges;
8,954 rows; week 3 builds 142 / 89 / 144; opening owed 1,425 / 1,285 / 752 and targets 823 / 857 / 515;
5,657 bikes needed; runs for the first six weeks; gaps 41.0 / 37.5 / 36.9 levelling at 37.0 after a week;
all three on target 6 Sep 2027.

Two cautions:

- **Slide 2, "RW-4418 at Reno 247 + 142 = 389".** Correct as the object's level, but that level never ships:
  the solver does not run the ship tasks. The plan's on-hand stock that week is **0**, with customers still
  waiting. A reader will take 389 as bikes sitting in Reno. Add "before orders ship", or work the example on
  the line's capacity row alone, which has no such trap.
- **Slide 3, boxes 1 and 3 (series, joint input) use the ship task.** True of the object. But shipping is
  assumed, not decided (orders ship as soon as stock exists, oldest first). If asked "so the solver decides
  shipping?", the answer is no. Item 6 gives you a joint input the solver does decide.

## 2. Opening floors, MTB carbon

| | Stock | On order | **Starts at** (net inventory, snapshot) | **Due** floor, week 1 | **Owed** floor | **Target** floor, week 1 |
|---|---|---|---|---|---|---|
| RW-9304 | 10 | 1,435 | −1,425 | −146 | 0 | +823 |
| RW-4418 | 25 | 1,310 | −1,285 | −123 | 0 | +857 |
| RW-6416 | 15 | 767 | −752 | −56 | 0 | +515 |

- The due floor is minus the open orders not yet due. At the snapshot itself those are 208 / 184 / 97; a week
  later 146 / 123 / 56; none from week 9, when the due floor meets the owed floor.
- Where to read them, with `R = scenarios.run_case(case)` and `k = (sku, "CMH+RENO")`:
  starts at `R["net"].at[k, 0]`; target `R["target_units"].at[k, 1]`; owed is 0.
- **Due has no function in the product yet.** It arrives with my half of the walk (`redwheel.walk.floors`),
  and I will tell you. Until then the numbers above are from
  `scripts/ranked_walk_probe/walk.py::not_yet_due(R)` (take the negative). Do not recompute it yourself.

## 3. What you may print today

- **The two-bike example** (RANKED_WALK.md §2): yes. It is arithmetic you can check by hand, and the solver
  session is using it as its own test.
- **The opening floors** in item 2: yes. They are data; no solver is involved.
- **"Today's rule, run as a walk, changes 0 cells":** draft it, do not finalise it. Two sessions measured it
  independently with a prototype; it becomes a permanent test when the solver's code lands. I will confirm.
- **The ranked results on scenario A:** hold, as you say.

## 4. Customer-side numbers

With `R = scenarios.run_case(scenarios.CASE_A)` and `s = scenarios.scorecard(R)`:

| Number | Where | Scenario A |
|---|---|---|
| All open orders cleared from | `s["Open orders cleared from"]` | 14 Dec 2026 |
| On-time fill | `s["On-time fill rate"]` | 96.4% |
| Position-weeks below target | `s["Position-weeks below target"]` | 278 |
| All targets held from | `s["All targets held from"]` | 6 Sep 2027 |

Per bike, the date its open orders are cleared (all three MTB carbon bikes: 14 Dec 2026):

```
weeks = list(range(1, len(R["obj"].weeks) + 1))
week = scenarios.held_from(R["flows"]["open_orders"][weeks] < 0.5)      # position -> first week with none waiting
date = R["obj"].weeks.set_index("t")["week_start"][int(week[k])]
```

Open orders are in `R["flows"]["open_orders"]` (position × week), stock after shipping in
`R["flows"]["on_hand"]`.

## 5. Words

Use the words the planner UIs already use.

| Say | Not |
|---|---|
| **net inventory** (stock − open orders) | net position |
| **target** (the weeks-of-supply target) | cover |
| **open orders**; "owed" only as you define it on slide 5, "open orders − stock" | backlog |
| **overdue orders**, or "past their date" | due (as a bare word) |
| **step** | goal, tier, level |
| **priority order**, for what a planner sees and sets | ranked walk (our working name for the design) |

The three floors are named **due, owed, target**. I renamed "cover" to "target" in RANKED_WALK.md today to
match. "Priority order" is my default for the on-screen name; the user has not confirmed it.

## 6. The component and supplier test

`tests/test_generality.py::test_a_bike_built_from_a_bought_frame_plans_with_no_new_code`, added today.

A bike is built on a line from one frame; frames are bought with a two-week lead time; 3 frames on hand;
4 bikes ordered every week. Worked by hand and matched exactly: builds 3, 0, 9, 4, 4, 4; frames bought
9, 4, 4, 4, 0, 0. Week 2 builds nothing because no frame has arrived, although the line has room. That is
your joint input: a make needs line capacity **and** a frame, and the scarcer one sets the pace.

It needed no new kind of resource, task or edge, and no change to the solver. Say "on a small example":
Redwheel's data has no components, and whole-bike rounding does not cover a purchase yet (a third test in
the same file pins that limit).

## Still true from my first note

- Three events, three stories: a line down costs four weeks; demand up 30% costs one week and 191 bikes;
  frames late for eight weeks is absorbed in scenario A (the plan builds 1,394 bikes ahead), and solving it
  as a separate frames supply gives the identical plan.
- One list of 11 things a planner can change, and Claude fills them from a sentence, asking "which line?"
  when the sentence does not say.
- Do not say: the plan builds ahead of the line outage; the plan decides shipping; "a general model"
  without naming rounding and the scenario code as Redwheel-shaped; any number for a surprise event.
