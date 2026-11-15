# Note to the Streamlit session: what the logic gives you now, and what is coming

From the object session (owner of `rtn`, `changes`, `tunables`, `priors`, `llm`, `store`). 15 Nov 2026.
I do not edit `planner2/`, `planner3/` or `app/`. Checked against the working tree of 15 Nov.

Your reading of the plot is right: **change a few numbers, re-run, see what moved.** Everything below is
there to make that loop shorter on screen.

## 1. Things that will bite if you do not know them

| What | Detail |
|---|---|
| **Two dates moved** with the solver's change (D23, see [SOLVER.md](SOLVER.md)) | "Open orders cleared": A is **14 Dec 2026** (was 21 Dec), B is **4 Jan 2027** (was 11 Jan). SKU-by-week builds moved on three lines. Every "targets held from" date, total and weeks-below count is unchanged. |
| **9 plan checks**, soon 10 | Never write the count; read `len(checks)`. |
| **A target is at most 35 weeks** | The forecast ends 35 weeks after the plan. `priors.validate` now refuses more, with the reason. planner2's settings editor still offers 52 (`components.py`, two `max_value=52.0`); use `priors.max_target_weeks(obj)`. |
| **A third event exists and your event words cannot show it** | `sc.CASE_E3`: no RW-4418 built for eight weeks (frames late). It is a limit on a *task*, not a resource. `planner2/events.py` renders it as "make item RW-4418 · … · nan bikes" and `lines_of` raises `KeyError`. That is why E3 is not in `sc.EVENTS` yet. Section 2 has the replacement. |
| `rtn.utilisation` | Blank (NaN), not an error, for a week with no capacity. |

## 2. What you can use to compress the UI

One module, `redwheel.tunables`, holds **every** thing a planner can change: 11 forms, one list. It
replaces the settings editor and the events card with one control ("add a change"), and it has the words.

```
tu.TUNABLES[key].fields        the form: each field's label, kind (choice/date/int/number/text), choices, min, max,
                               default, help. Render it generically; do not hand-write a form per tunable.
tu.make(key, **values)         a filled form -> an Edit. Raises ValueError naming the wrong field.
tu.check(case, edits)          every reason it cannot run, in plain words, without planning. Empty = it can.
tu.apply(case, edits, key=..)  the new scenario.
tu.describe(edit_or_change)    "MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027 · down (none)"
tu.now(key, case, **values)    what is there now: "375 a week", "no limit", "Either site"
tu.differences(a, b)           one table, settings and events together: Tunable · What · From · To · Why
tu.change_rows(changes, R["change_report"])     "what changed in the data": numbers changed, from, to
tu.name_hint(change)           a scenario name: "MTB carbon line down from 1 Mar 2027"
```

The 11: stock count, line capacity (0% = down, 120% = overtime), demand ±%, a one-off order, build limit,
transfer limit; build time, transfer time, ship from, plan transfers, target. The defaults of line
capacity, demand and build limit *are* E1, E2 and E3.

Claude, for "describe the change" (replaces `llm.propose`, which only knows settings):

```
p = llm.propose_edits(sentence, case)
p.question      "Which line is down for the next two weeks…?"   -> show it, propose nothing
p.unsupported   what no tunable can do, with the reason
p.words         the edits in plain words          p.reasons   the part of the sentence each came from
p.errors        what failed the checks            p.ok        edits that passed
p.scenario()    the scenario with them, to run
```

Tested live: "A line is down for the next two weeks" asks which line; E1 and E2 in one sentence, E3, a stock
count and scenario B all come out exactly. `llm.explain` (Ask) is unchanged.

When your event words come from `tunables`, tell me and E3 joins the built-in list.

## 3. Coming before the demo: who waits when a line is short

Design: [RANKED_WALK.md](RANKED_WALK.md), sections 1 to 3 (short, with a two-bike example). The solver
session builds the solver part; I build the rest. **Do not build against it yet**; I will send exact names.

What you will get:
- a twelfth form, "Priority order", through the same `TUNABLES` list, so input needs no new UI;
- on the scenario, its walk in words: an ordered list of steps;
- per step, how far it could not be met;
- a tenth plan check.

What the story needs on screen, and planner2 does not have: **a per-bike row for one line** (orders cleared
on, at target on), against the scenario it is compared with. The point is "these two bikes are healthy
months earlier and no customer waits longer", which a per-line number hides.

## 4. Your questions

Only the user can answer 2 and 6. What I can add:

1. **Demo script.** Not mine to set. What the notes and the user's requests add up to: the plan and its
   checks; one change made live and what moved (line down, E1); a change the plan absorbs (parts late, E3);
   a rule change (A against B); and, new today, priority order "before the demo, shown cleanly". Confirm
   the order with the user.
3. **"Too much stuff".** The user's words to me today: "too much going on in the UI. too much information";
   "it's hard for me to know if it works or not"; "difficult to validate and compare. We have all the
   functionality but we need to show this properly". And about a document of mine: "very dense, no examples
   that are clean, lacks the narrative and flow". Read together: fewer things per screen, one clean example,
   and always visible *against what* a number is compared.
4. **Who it is for.** The panel at Atomic watching the user drive: a 30-minute presentation on 16 Nov, the
   last ten minutes live (WORKING_NOTES, "Presentation plan").
5. **Where Claude appears.** Both. The user typed "line is down for next two weeks" into the describe box
   today, got a refusal from the old function, and wants that to work: use `propose_edits`. Ask stays.
6. **Where to work.** The user's call. For what it is worth: with one form list and one differences table,
   the loop fits one screen: change it (a form, or a sentence), see what moved against the base.
