# Ranked walk

**Who waits when there is not enough, and how a planner gets to say so.**

Status: a design, backed by a working prototype. No solver code has changed. 15 Nov 2026.
The solver belongs to the solver session ([SOLVER.md](SOLVER.md)); this builds on what is written there.

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

Nothing is added to the model of the world. A floor is read from numbers the object already holds.

```
 THE OBJECT                         A POSITION                     ITS FLOORS
 stock of RW-4418 at Reno   (+)
 stock of RW-4418 at PDC    (+) ──► net inventory of RW-4418 ──►  target = forecast of the next 15 weeks
 web orders for RW-4418     (−)      (one number per week)               (the object's order arrivals)
 dealer orders for RW-4418  (−)                                   owed  = 0
 commercial orders          (−)                                   due   = −(open orders not due yet)
                                                                         (need-by dates in the order files)
```

- A **position** is a set of the object's resources, added up with signs. It exists today: the routing rule
  defines it (in scenario B there are two per bike, one at Reno and one at the PDC).
- A **floor** is one number per position per week, computed from the object. Target is computed today. Owed
  is zero. Due needs the need-by dates, which the order files have and the object does not yet carry.

So the walk does not describe the world. It says which of the world's numbers the plan must protect, and in
what order. It would carry over to any company whose world is in the object.

Is "due" worth having? The data says it is real: of 5,991 bikes on open orders, 2,385 were due before the
snapshot, 1,467 are not due yet, and 2,139 (all web orders) carry no date.

---

## 5. The walk

A **step** has three parts:

| Part | Choices |
|---|---|
| Floor | due · owed · target |
| Which bikes | all, or a selection (a line, a list), written the way a change selects resources |
| How they share | **evenly** (equally short, in weeks: today's rule) or **ranked** (one at a time, in a stated order) |

A **walk** is steps in order. The solver takes step 1 and makes its shortfall as small as it can. It holds
that result and takes step 2, and so on. Last, as today, it trims stock above target.

The three rules from the example, written as walks:

```
 Today                         1. target · all bikes · evenly

 Rank the bikes: Y first       1. target · all bikes · ranked: Y, X         ← the trap

 Customers, then stock         1. owed  · all bikes · evenly
                               2. target · all bikes · ranked: Y, X
```

And as data, a walk is a short list of records, stored with the scenario next to its changes:

```
 Step(floor="owed",  who={},                        share="even")
 Step(floor="target", who={"line_id": "mtb-carbon"}, share="ranked", order=["RW-9304", "RW-4418", "RW-6416"])
 Step(floor="target", who={},                       share="even")      # every bike not in a target step yet
```

A scenario with no walk gets today's rule, through today's code.

---

## 6. What it does on Redwheel

Scenario A, MTB carbon line. All measured with the prototype; every row passes all 9 plan checks, builds the
same 94,429 bikes, and holds all targets from 6 Sep 2027.

| Walk | Differs from today's plan | Customers | Stock |
|---|---|---|---|
| **target evenly** (today's rule, run as a walk) | **0 cells** | – | – |
| **owed evenly → target evenly** | **0 cells** | – | – |
| due evenly → owed evenly → target evenly | 35 cells, at most 24 bikes | no headline number moves | no headline number moves |
| **owed evenly → target ranked** (9304, 4418, 6416) | 117 cells | **exactly as today**: every bike's orders cleared 14 Dec 2026, fill 96.4% | RW-9304 at target 22 Feb 2027 and RW-4418 on 26 Jul, not 6 Sep; RW-6416 on 6 Sep as today. 244 bike-weeks below target, not 278 |
| owed ranked → target ranked | 159 cells | orders cleared 5 Oct, 9 Nov, 14 Dec, not all on 14 Dec; fill 97.4%; the same bike-weeks of waiting in total | as the row above |
| target ranked (the trap) | 159 cells | RW-6416's customers wait until **26 Jul 2027**; fill 94.3%; **2.8 times** the bike-weeks of waiting | RW-9304 at target 26 Oct 2026, RW-4418 on 8 Mar 2027 |

What this shows:

- **The walk contains today's rule.** The first two rows are the proof: same plan, cell for cell. Nothing
  existing has to change, and "the plan serves customers first" is a true sentence about today.
- **A ranked walk can be free for customers.** In the fourth row no customer waits a day longer; the ranking
  only decides which bike gets its safety stock first.
- **Urgency is real but small here.** Putting "due" first moves 35 cells and no headline. The three bikes on
  a line are in the same state, so there is little to reorder.
- **Ranking is a choice, not a gain.** Two bikes are healthy months early; the third is no later than today.
  Whether that is worth it is the planner's call, which is the point of making it visible.

---

## 7. How the order gets written

A planner should not have to type bike ids in order. There are two layers.

**The rule** is what a person, a file, or Claude writes:

> "After customers are served, build stock for the MTB carbon bikes with the most open orders first."

**The walk** is what code produces from the rule and the scenario's own numbers:

```
 1. owed   · all bikes  · evenly
 2. target · MTB carbon · ranked: RW-9304 (1,435 on order), RW-4418 (1,310), RW-6416 (767)
 3. target · the rest   · evenly
```

The walk is what gets saved, shown for approval, and given to the solver.

Why split it:

- **Claude picks the rule; the data sets the order.** Claude still never sees stock or orders. It names a
  measure; code looks the numbers up.
- **A static file and "prioritise the backlogged" end as the same thing:** a list. One is typed, the other
  computed.
- **The same rule gives a different walk on different data.** A stock correction changes who has the most
  open orders. The walk is recomputed with the scenario, and the planner sees the new order before it runs.

Measures a rule can name, with what they give on MTB carbon:

| Measure | RW-4418 | RW-6416 | RW-9304 | Order |
|---|---|---|---|---|
| Open orders (bikes) | 1,310 | 767 | 1,435 | 9304, 4418, 6416 |
| Orders already due at the snapshot (bikes) | 1,126 | 670 | 1,227 | 9304, 4418, 6416 |
| Weeks below target at the snapshot | 36.0 | 35.6 | 38.9 | 9304, 4418, 6416 |
| Forecast over the plan (bikes) | 16,363 | 9,822 | 12,408 | 4418, 9304, 6416 |
| Price | the same for all three | | | a tie |

Two rules the data forces: a measure must be **named**, because they disagree (forecast against open
orders); and a **tie** must mean something, because they happen (price). A tie means "share evenly".

Ranking only acts between bikes that compete for the same capacity: the bikes on one line. Ranking a road
bike against a mountain bike changes nothing.

---

## 8. What it asks of the solver

For the solver session to judge; the prototype does it from outside, without changing `engine.py`.

- One shortfall per floor, where today there is one. Same form: `shortfall >= floor − net inventory`.
- One solve per step, each adding a row that holds the step before. Then a last solve for stock above
  target and runs. The fourth walk above took 6 solves and half a second.
- No walk given: today's single solve, untouched.
- The shortcut of one solve with shrinking weights is not safe for a ranking: at weights 1, 0.1, 0.01 it
  matched the staged walk; at 1, 0.01, 0.0001 one cell differed by 214 bikes.
- One new plan check: a bike is not given units for a later step while an earlier step on its line is unmet.

## 9. What is not solved

- **Which week.** When a shortfall cannot be avoided the solver does not care which week it lands in
  (SOLVER.md, O28). A walk orders needs, not weeks.
- **Surprises.** The plan still knows every event from week 1.
- **Channels.** "Dealers before web" cannot act in scenario A: all three channels draw on one pool of stock.
- **Left for later:** priorities that change on a date; a second measure to break ties.

## 10. Where the numbers come from

`scripts/ranked_walk_probe/walk.py` prints the example in section 2 and every row of section 6.
`measures.py` gives section 7's table; `ranked_proto.py` compares the staged walk with the one-solve
shortcut. They are probes: they patch the solver from outside and will be replaced by tested code.

Background: solving priorities one level at a time is preemptive goal programming (Hillier & Lieberman,
ch. 16 supplement). SAP IBP writes demand priority as ordered segments, each fulfilled by fair share or in
sequence. Oracle writes a priority rule as ranked attributes, for example revenue, then requested date.
