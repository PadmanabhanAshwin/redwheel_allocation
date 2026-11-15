# Assumptions

Each entry: statement · fact (file + evidence) or assumption (rationale) · where it is used.

The full table of what comes from the files and what is assumed is in the README ("What comes from the files
and what is assumed"). The entries below are the ones a priority order rests on (15 Nov 2026).

## When an order is due

| Statement | Fact or assumption | Used |
|---|---|---|
| A dealer order is due on its requested ship date; a commercial order on its need-by date. | **Fact.** `dealer_orders_export.csv` ("Requested Ship Date"), `Commercial_PO_Log.csv` ("Need By"). Dealers ask about 3 weeks ahead (median 3.0), commercial accounts about 6 (median 5.9). No dated order asks for a date before it was placed. | `aux_fns.build_due` → `obj.due` |
| Web orders carry no date. | **Fact.** `dtc_web_orders.csv` has an order date and a ship date only. All 2,139 undated open bikes are web orders, one bike per line, a consumer each. | `obj.due` (the `due` column is blank) |
| An order with no date is due 7 days after it was placed. | **Assumption, a rule of the scenario** (`Walk.no_date_days`, the form "Orders with no date"). Evidence for 7: every shipped web order shipped 2 to 10 days after it was placed, median 6. The plan is weekly, so 0 and 7 days give the same plan; 14 does not. Where it matters (the five bikes that are short) the typical open web order is 6 to 9 weeks old, so it is overdue under any reasonable number. | `walk.not_due` |
| An order that arrives during the plan is due the week it arrives. | **Assumption.** The forecast lines up with the week orders are placed, not the week they are wanted: last year's dealer and commercial orders by week placed correlate 0.94 with the forecast for the same calendar weeks with no shift; by date asked they fit best when moved 3 weeks earlier. So a future dealer order counts about 3 weeks before the dealer wants it. This is cautious (it never understates urgency) and is how the base plan already nets orders. | `walk.not_due`; the base plan |
| Open orders booked for later weeks are not also inside the forecast. | **Assumption**, on the same evidence (and 52-week totals: 21,315 forecast against 21,780 ordered last year, dealer and commercial). If the forecast were by date wanted, 1,467 bikes would be counted twice in weeks 1 to 9. | the base plan |
| Dealer orders restock shops; the shops' own stock is not used to judge how late an order may be. | **Assumption.** `dealer_stock_report.csv` gives 2,000 bikes on dealers' floors (1.9 weeks of RW-9304, 100 of RW-9324), but there is no forecast per dealer to set it against. | not used |
| Targets net out all open orders, whatever their dates. | **Fact, the brief:** "These targets should net out existing backlog". The due dates change what comes first when a line is short; they do not change net inventory or a target. | `scenarios.run_case` |
