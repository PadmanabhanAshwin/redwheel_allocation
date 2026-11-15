# Note to the Streamlit session: what the logic gives you

From the object session (owner of `rtn`, `changes`, `walk`, `tunables`, `priors`, `llm`, `store`). Final, 15 Nov
2026, evening. I do not edit `planner2/`, `planner3/` or `app/`. Checked against commit fed4544.

Your reading of the plot is right: **change a few numbers, re-run, see what moved.** Everything below is there
to make that loop shorter on screen.

## 1. Things that will bite

| What | Detail |
|---|---|
| **A scenario's priority order is dropped by `planner2/state.py`** | `_run` rebuilds the `Case` from (key, name, table, changes) and `create` copies settings and changes only, so a scenario with a walk runs as if it had none, silently. Fix, three lines, below. Until then do not list P1. |
| **Plan checks: 10 with a priority order, 9 without** | Never write the count; read `len(checks)`. |
| **Two dates moved** with the solver's change (D23) | "Open orders cleared": A is **14 Dec 2026**, B is **4 Jan 2027**. |
| **A target is at most 35 weeks** | `priors.validate` refuses more, with the reason. planner2's settings editor still offers 52 (`components.py`, two `max_value=52.0`); use `priors.max_target_weeks(obj)`. |
| **E3 (a build limit) cannot be shown by your event words** | `planner2/events.py` renders it as "… nan bikes" and `lines_of` raises `KeyError`. `tunables.describe` has the words. E3 and P1 join the built-in list when your words come from there. |
| `rtn.utilisation` | Blank (NaN), not an error, for a week with no capacity. |
| A priority order on scenario B takes about 6 seconds | Not 1. It is one solve per step. |

The three-line fix:

```
_run(..., changes_json_="[]", walk_json_="null")
    -> sc.Case(key, name_, t, summary, parent, changes, wk.from_record(json.loads(walk_json_)))
view():    args = (..., changes_json(key), json.dumps(wk.to_record(c.walk), sort_keys=True))
create():  sc.Case(k, full, table, summary, base, changes, ss.cases[base].walk)
```

(`from redwheel import walk as wk`; `whatif.py` calls `_run` for the preview and needs the same argument.)

## 2. One list of everything a planner can change

`redwheel.tunables`: **13 forms, one list.** It replaces the settings editor and the events card with one
control ("add a change"), and it has the words.

```
tu.TUNABLES[key].fields        the form: each field's label, kind (choice/date/int/number/text), choices, min, max,
                               default, help. Render it generically; do not hand-write a form per tunable.
tu.TUNABLES[key].changes       "data" (a number on the object), "rules" (a settings row), "priorities" (the walk)
tu.make(key, **values)         a filled form -> an Edit (.change, .settings or .walk). Raises ValueError naming the field.
tu.check(case, edits)          every reason it cannot run, in plain words, without planning. Empty = it can.
tu.apply(case, edits, key=..)  the new scenario.
tu.describe(edit_or_change)    "MTB carbon line capacity · weeks of 1 Mar to 15 Mar 2027 · down (none)"
                               "Priority order · MTB carbon · RW-9304, then RW-4418, then RW-6416 (target)"
tu.now(key, case, **values)    what is there now: "375 a week", "no limit", "Either site", "shared evenly"
tu.differences(a, b)           one table, settings, events and priority order: Tunable · What · From · To · Why
tu.change_rows(changes, R["change_report"])     "what changed in the data": numbers changed, from, to
tu.name_hint(change_or_edit)   a scenario name: "MTB carbon line down from 1 Mar 2027", "MTB carbon in priority order"
tu.walk_lines(case)            the priority order in words, one line per step; one line when there is none
```

The 13: stock count, line capacity (0% = down, 120% = overtime), demand ±%, a one-off order, build limit,
transfer limit; build time, transfer time, ship from, plan transfers, target; priority order, orders with no
date. The defaults of line capacity, demand, build limit and priority order *are* E1, E2, E3 and P1.

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
count, scenario B, and P1 ("get RW-9304 to its target first, then RW-4418, then RW-6416") each come out
exactly; "Put the MTB carbon bikes in a priority order" asks in what order. `llm.explain` (Ask) is unchanged.

## 3. The priority order on screen

```
sc.CASE_P1, sc.PRIORITY                    the built-in example: scenario A with MTB carbon in priority order
R["walk"]["steps"]                         the walk as solved: [(floor, [positions])], or None
wk.results(R["lp"].steps)                  one row per step: floor, positions, worst, total (weeks short), met
```

The story, scenario P1 against A (both run in about a second):

| | A | P1 |
|---|---|---|
| Open orders cleared, each MTB carbon bike | 14 Dec 2026 | 14 Dec 2026 |
| On-time fill | 96.4% | 96.4% |
| RW-9304 at target | 6 Sep 2027 | **22 Feb 2027** |
| RW-4418 at target | 6 Sep 2027 | **26 Jul 2027** |
| RW-6416 at target | 6 Sep 2027 | 6 Sep 2027 |
| Position-weeks below target | 278 | 244 |

What planner2 does not have and the story needs: **a per-bike row for one line** (orders cleared on, at target
on), against the scenario it is compared with. Per bike: `sc.held_from(R["at_target"][weeks])` and
`sc.held_from(R["flows"]["open_orders"][weeks] < 0.5)`; a date is `R["obj"].weeks.set_index("t")["week_start"][t]`.

## 4. Words

Use the words the planner UIs already use: **net inventory**, **open orders**, **target**. The three floors are
**due** ("orders past their date" on screen), **owed** ("all open orders"), **target**; a priority order is made
of **steps**; the planner-facing name is **Priority order**.

## 5. The user's answers to your questions, as I have them

- **Demo script:** the plan and its checks; one change made live and what moved (line down, E1); a change the
  plan absorbs (parts late, E3); a rule change (A against B); the priority order (P1). Confirm the order with
  the user.
- **"Too much stuff":** the user's words: "too much going on in the UI. too much information"; "hard for me to
  know if it works or not"; "difficult to validate and compare". Fewer things per screen, one clean example,
  and always visible *against what* a number is compared.
- **Who it is for:** the panel at Atomic watching the user drive, 16 Nov, 30 minutes, the last ten live.
- **Where Claude appears:** both; use `propose_edits` for "describe the change". Ask stays.
- **Where to work, and what to keep or cut:** the user's call.
