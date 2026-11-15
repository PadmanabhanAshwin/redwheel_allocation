# Ranked walk

**Who waits when there is not enough, and how a planner gets to say so.**

Status: **built and tested**, 15 Nov 2026. The planner-facing name is **Priority order**.
Code: `redwheel/walk.py` (the walk, its rules, the floors), `engine.decide_walk` (the solver part,
[SOLVER.md](SOLVER.md)), two forms in `redwheel/tunables.py`, one built-in example (scenario P1).
Sections 1 to 3 are the idea; 4 to 7 are what is built; 8 to 10 are the proof and the limits.

---

## 1. The problem

A line builds 375 MTB carbon bikes a week. Three bikes share it, and for a year the line cannot build enough
for all three. Every week, someone has to wait. The plan decides who.

Today that decision is made by a rule inside the solver: keep every bike on the line equally short. It is a
good rule. But it is the only one, it is not written anywhere a planner can see, and a planner cannot say
"this bike first".

A scenario already has two parts a planner can read and change:

| Part | It says | Example |
|---|---|---|
| The world | what is true | stock, capacity, demand, a line down in March |
| The rules | what the plan may do | a bike takes a week to build; web orders ship from the PDC |

The third part is missing:

| Part | It says | Today |
|---|---|---|
| **The purpose** | what the plan is for, and in what order | fixed inside the solver |

A ranked walk is that third part, written down: a short ordered list of what the plan must look after first.

---

## 2. A small example

Two bikes, X and Y, share a line that builds **10 a week**. No new orders arrive, to keep it simple.

- X has **10 customers waiting** (its net inventory is −10).
- Y has nobody waiting (net inventory 0).
- Each should hold **20** in stock.

So X needs 30 bikes, Y needs 20, and the line makes 10 a week. Four ways to share them, each solved by the
prototype. Cells are builds for X / Y, then net inventory X / Y at the end of the week.

| Rule | Week 1 | Week 2 | Week 3 | Week 4 | What happened |
|---|---|---|---|---|---|
| **Today**: keep both equally short | 10 / 0 → 0 / 0 | 5 / 5 → 5 / 5 | 5 / 5 → 10 / 10 | 5 / 5 → 15 / 15 | X's customers are served in week 1. Then both build stock together. |
| **Rank the bikes: Y first** | 0 / 10 → −10 / 10 | 0 / 10 → −10 / 20 | 10 / 0 → 0 / 20 | 10 / 0 → 10 / 20 | Y gets its full stock while **X's customers wait until week 3**. |
| **Customers, then stock: Y first** | 10 / 0 → 0 / 0 | 0 / 10 → 0 / 10 | 0 / 10 → 0 / 20 | 10 / 0 → 10 / 20 | X's customers are served in week 1. Then Y builds stock first. |

Three things to take from it:

1. **Today's rule already puts customers first.** X is 30 short and Y is 20 short, so X is further behind
   and gets the line until it catches up, which is exactly when its customers are served.
2. **Ranking bikes alone is a trap.** "Y first" builds Y's safety stock before X's customers. Nobody means
   that when they say priority.
3. **So a priority has two parts:** which *need* comes first (customers, or stock), and then which *bike*.

---

## 3. The idea: floors

Every bike has one number that matters: its **net inventory** (stock we hold minus orders customers have
placed). The plan's whole job is to keep that number high enough. "High enough" has levels:

```
   net inventory of RW-4418, week 1
            │
     +857 ──┼──  TARGET  the weeks-of-supply target (the next 15 weeks of forecast)
            │            below this: short of safety stock
            │
        0 ──┼──  OWED    below this: a customer is waiting for a bike
            │
     −123 ──┼──  DUE     minus the orders not due yet
            │            below this: a customer is waiting past the date they asked for
            │
   −1,285 ──┼──  where RW-4418 starts (25 in stock, 1,310 on order)
```

Each level is a **floor**. Being below a floor is a **need**, and the lower the floor, the more it hurts.
The three are called **due**, **owed** and **target**; on screen they read as overdue orders, open orders and
the weeks-of-supply target, the words the planner already uses.
RW-4418 starts under all three: 1,162 bikes to climb before nobody is waiting past their date, 123 more
before nobody is waiting at all, then 857 more to hold its target. The floors move week by week: target
follows the forecast, and due rises to zero as orders fall due.

This is why the example worked the way it did. Today's rule has one floor, target, and measures how far
below it each bike is. A bike with customers waiting is always further below than one without, so it goes
first. The other floors were there all along, implied.

---

## 4. How this connects to the object

A floor is read from the object. Two of the three needed nothing new. The third needed one fact.

```
 THE OBJECT                         A POSITION                     ITS FLOORS
 stock of RW-4418 at Reno   (+)
 stock of RW-4418 at PDC    (+) ──► net inventory of RW-4418 ──►  target = forecast of the next 15 weeks
 web orders for RW-4418     (−)      (one number per week)               (the object's order arrivals)
 dealer orders for RW-4418  (−)                                   owed  = 0
 commercial orders          (−)                                   due   = −(open orders not due yet)
                                                                         (the object's due table)
```

- A **position** is a set of the object's resources, added up with signs. The routing rule defines it (in
  scenario B there are two per bike, one at Reno and one at the PDC).
- A **floor** is one number per position per week.

**The one fact added: when the open orders are due.** The object held open orders as a count with no time.
It now also holds a small table, `obj.due`: for each group of open orders, how many, the week they are due
if the order carries a date, and when they were placed. It splits the opening level; it changes no level,
no equation and no target. The brief says targets net out the backlog, all of it, and they still do.

**What the order files say** (5,991 bikes on open orders):

| | Who orders | Date on the order | Bikes open |
|---|---|---|---|
| Web | a consumer, one bike | none | 2,139 |
| Dealer | a shop restocking its floor, about 6 bikes | requested ship date, about 3 weeks ahead | 2,914 |
| Commercial | a rental fleet or a city, about 9 bikes | need-by date, about 6 weeks ahead | 938 |

Of the dated ones, 2,385 are past their date and 1,467 are not due yet (none after week 9).

**The rule for an order with no date.** A fact cannot settle this, so it is a rule of the scenario, with a
default taken from the history:

> An order is due on its own date. If it has none, it is due **7 days** after it was placed.

Why 7: when a bike is in stock, a web order ships 2 to 10 days after it was placed (median 6). The plan is
weekly, so "7 days" and "at once" give the same plan; 14 days does not. A planner can change the number
(the form "Orders with no date"). Orders that arrive during the plan are due the week they arrive.

So: **the object holds the facts, the scenario holds the rule, the walk says what comes first.**

---

## 5. The walk

A **step** has four parts:

| Part | Choices |
|---|---|
| `floor` | due · owed · target |
| `select` | which bikes: `{}` for all, or columns of the item table, e.g. `{"line_id": "mtb-carbon"}` (the way a change selects resources) |
| `share` | **even** (equally short, in weeks: the standing rule) or **ranked** (one at a time) |
| `order` | for ranked: the bikes, first served first. Bikes of the step left out follow, sharing evenly |

A **walk** is steps in order, plus the days for an order with no date. The solver takes step 1 and makes
its shortfall as small as it can. It holds that and takes step 2, and so on. Last it trims stock above
target, as before. Scenario P1, as it is written in the code:

```
 Walk(steps=(Step("due"),
             Step("owed"),
             Step("target", {"line_id": "mtb-carbon"}, "ranked", ("RW-9304", "RW-4418", "RW-6416")),
             Step("target", {"line_id": ["road-base", "road-carbon", "mtb-base"]})),
      no_date_days=7)
```

and as the planner reads it:

```
 1. Orders past their date · every bike · shared evenly
 2. All open orders · every bike · shared evenly
 3. Target · MTB carbon line · in order: RW-9304, then RW-4418, then RW-6416
 4. Target · MTB base, Road base and Road carbon lines · shared evenly
```

A scenario with no walk runs the standing rule through the code it always ran through.

**Eight rules** keep a walk sound (`walk.check` names each one broken):

1. A floor is due, owed or target; a share is even or ranked.
2. A selection uses real columns and matches at least one bike.
3. A ranked step lists bikes of its own selection, each once.
4. On one floor a bike is in at most one step.
5. Every bike is in a target step.
6. A bike's steps climb: due, then owed, then target.
7. **A ranked target step needs an owed step for the same bikes before it.** This is the trap of section 2,
   closed: without it the first bike is built up to its target while customers of the others wait.
8. The days are a whole number, 0 to 365.

---

## 6. What it does on Redwheel

Run through the product (`scenarios.run_case`), not a prototype. Every row passes all 10 plan checks and
builds the same 94,429 bikes. Each line builds the same number of bikes every week as before: only the mix
between its bikes moves.

**Scenario A** (today: orders cleared 14 Dec 2026, fill 96.4%, 278 position-weeks below target, all targets
held from 6 Sep 2027):

| Walk | Differs from today's plan | Customers | Stock |
|---|---|---|---|
| target evenly (the standing rule, written as a walk) | **0 cells** | – | – |
| due → owed → target, all evenly | 35 cells, at most 24 bikes | no headline number moves | no headline number moves |
| **P1**: due → owed evenly, then target in order 9304, 4418, 6416 | 152 cells | **exactly as today**: every bike's orders cleared 14 Dec 2026, fill 96.4% | RW-9304 at target **22 Feb 2027**, RW-4418 **26 Jul**, not 6 Sep; RW-6416 on 6 Sep as today. 244 below, not 278 |
| the same order on every floor ("orders too") | 173 cells | orders cleared 12 Oct, 9 Nov, 14 Dec, not all on 14 Dec; fill 97.4% | as the row above |
| target in order, with no owed step (the trap) | refused by rule 7 | measured on the prototype before the rule closed it: RW-6416's customers wait until 26 Jul 2027, fill 94.3% | – |

**Scenario B** (today: orders cleared 4 Jan 2027, fill 95.3%, 722 below, held from 27 Sep 2027):

| Walk | Customers | Stock |
|---|---|---|
| due → owed → target, all evenly | as today | as today |
| P1's order | as today | RW-9304 at target **19 Apr 2027**, RW-4418 **23 Aug**, not 27 Sep. 666 below, not 722 |
| the same order on every floor | fill 96.6% | as the row above |

What this shows:

- **The walk contains the standing rule.** First row: the same plan, cell for cell.
- **A priority order can be free for customers.** In P1 no customer waits a day longer; the order only
  decides which bike gets its cover first. Two bikes are healthy months sooner; the third is no later.
- **Dates are real but small here.** Putting "due" first moves 35 cells and no headline: three of every
  four open bikes are already late, and the bikes on a line are in the same state.
- **It is a choice, not a gain.** Whether RW-9304 should come first is the planner's call. The point is that
  the choice is now visible, written down, and one line to change.

---

## 7. How the order gets written

**By list.** A planner names a line and its bikes in order, in the form "Priority order", or says it in a
sentence that Claude turns into the same form:

> "On the MTB carbon line, get RW-9304 to its target first, then RW-4418, then RW-6416."

The form has three fields: the line; the bikes, first to last; and what the order decides (who reaches the
target first, or whose orders are cleared first as well). A second form, "Orders with no date", sets the
days. Both sit in the one list of tunables (now 13), so the checks, the words and Claude come with them.

Claude was tested live on six requests: it fills the form exactly, lists one bike when only one is named,
asks "in what order?" when none is given, and says a line cannot be put ahead of another line (lines share
no capacity).

**Not built: an order computed from a measure** ("the bike with the most open orders first"). The design
allows it (compute a list, then proceed as above) but a list a planner can read is the firmer ground for
now. If it is built, these are the measures the data offers on MTB carbon, and they disagree:

| Measure | RW-4418 | RW-6416 | RW-9304 | Order |
|---|---|---|---|---|
| Open orders (bikes) | 1,310 | 767 | 1,435 | 9304, 4418, 6416 |
| Orders already due at the snapshot (bikes) | 1,126 | 670 | 1,227 | 9304, 4418, 6416 |
| Forecast over the plan (bikes) | 16,363 | 9,822 | 12,408 | 4418, 9304, 6416 |

A priority order acts only between bikes that share a line.

---

## 8. How it runs

```
 scenario.walk ──► walk.check          the eight rules
               ──► walk.resolve        a ranked step becomes one step per bike; a bike's positions stay together
               ──► walk.floors         due (from obj.due and the days), owed (0), target
               ──► engine.decide_walk  one solve per step, each held; then stock above target and runs
               ──► the tenth plan check: a later step is served only when every earlier step on the line was
                                         met or held back
```

P1 takes 6 solves and about a second on scenario A; about 6 seconds on B, which has twice the positions.

## 9. What is not solved

- **The planner UIs do not show a walk yet.** The logic, the forms and the words are ready
  ([NOTE_TO_STREAMLIT_BOT.md](NOTE_TO_STREAMLIT_BOT.md)).
- **"Stock them at the PDC."** A second choice for orders with no date: they carry no due date and are
  protected by the target at the PDC. It only acts when web ships from the PDC (scenario B), and it means
  dealers are served before web customers. Designed for, not offered yet.
- **Dealer shelf stock.** A dealer order restocks a shop, and the shops report 2,000 bikes on hand (1.9
  weeks of RW-9304). That says how much a late dealer order hurts. There is no forecast per dealer, so it is
  not used.
- **Future orders are due the week they arrive.** Last year's orders line up with the forecast by the week
  they were placed, so a future dealer order is counted about three weeks before the dealer wants it. This
  is how the base plan already works; it makes the due floor cautious.
- **Which week** an unavoidable shortfall lands in (SOLVER.md, O28), and **surprises** (the plan knows every
  event from week 1): unchanged.

## 10. Where the numbers come from

- `tests/test_walk.py`: the due table recounted from the three raw order files; the rules, each broken on
  purpose; four examples worked by hand on two bikes; every row of section 6 through `run_case`.
- `tests/test_tunables.py`, `tests/test_llm.py`, `tests/test_llm_live.py`: the forms and Claude.
- `tests/test_engine.py`: the solver part, including section 2's example.
- The prototypes this design started from (`scripts/ranked_walk_probe/`, which patched the solver from
  outside) are removed; they are in the history before commit a4b793e, and every number they produced is
  now a test.

Background: solving priorities one level at a time is preemptive goal programming (Hillier & Lieberman,
ch. 16 supplement). SAP IBP writes demand priority as ordered segments, each fulfilled by fair share or in
sequence. Oracle writes a priority rule as ranked attributes, for example revenue, then requested date.
