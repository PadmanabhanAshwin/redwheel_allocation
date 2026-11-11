# Working notes

Decisions taken and items still open. Updated as we go; newest decisions at the bottom of each list.

## Decisions

| # | Decision | Date |
|---|---|---|
| D1 | The base case (builds on pooled net inventory, no lead times in play, shipping and transfers not decided) is frozen and guarded by `tests/test_base_case.py`. New behaviour is opt-in. | 2026-11-11 |
| D2 | PDC = the Columbus distribution centre. | 2026-11-11 |
| D3 | Routing ("customer orders ship from the PDC") is a planning prior, not part of the object: the routes stay in the object, the prior says which may be used. | 2026-11-11 |
| D4 | Weeks of supply is counted the way demand faces: each stock location against the demand it serves. Stock counts once it has arrived. The factory rolls up to all demand through the transfer to the PDC. | 2026-11-11 |
| D5 | Build time is a modifiable parameter (by line or SKU eventually). First value: 1 week, the same for every line. Reno → PDC stays 1 week. | 2026-11-11 |
| D7 | Scenario A = the base case. Scenario B = routing B: web orders ship from the PDC (replenished from Reno, 1 week); dealer and commercial orders ship direct from Reno; build time 1 week; the LP decides builds and transfers. | 2026-11-11 |
| D6 | "Shipped" means factory output released to orders as soon as it is available (an assumption). | 2026-11-11 |

## Open items

| # | Item | Notes |
|---|---|---|
| O1 | Split the forecast by ship-to location | Not needed while every order ships from the PDC. Needed once a second shipping site is allowed. Method agreed in principle: historical state mix; commercial orders have no location. |
| O2 | Need-by-date phasing of the opening backlog | Open orders counted as owed now. Wanted: owed in their need-by week; orders without one (all web orders) at an agreed service level. Depends on O3. |
| O3 | Question for Redwheel: is the forecast by order-placement week or by due week? | If by due week, phasing backlog by need-by date could double count. |
| O4 | Road target step date | Brief says "in 2028"; we use 3 Jan 2028. Fiscal reading would be Sep 2028. |
| O5 | Run bookkeeping: save a case with its inputs and results, reload, compare | After the first non-trivial case works end to end. |
| O6 | LLM form that fills in a case | Exhibit candidate: "change the build time on a line". After O5. |
| O7 | Scenario list to re-run | Supplier slip (no supplier data: would be illustrative), demand spike on a SKU, line capacity down. |
| O8 | Object Encoding page: show how the raw files map into the object | Pinned by the user. |
| O9 | Build Score page needs a proper rework | Only renamed so far. |
| O10 | Shipping decided by the model rather than assumed | Today: ship as soon as stock exists, oldest orders first. |
| O11 | Code and README still say "arrows"; the UI says "edges" | Rename if wanted. |
| O12 | Near-term forecast is well below recent orders on every line | Stated on page 1; raise with Redwheel. |
| O13 | Road SKUs hold stock roughly equal to their open orders, and those orders are not shipping | Data does not say why. |
| O14 | End-of-horizon effect in scenarios with lead times | In scenario B a bike built in week 121 lands after the horizon, so the plan builds nothing in week 121, tapers in week 120 and transfers nothing in the last week. Fix: plan a few weeks past the reporting horizon (needs capacity assumed beyond the data). Guarded by a test so it is not forgotten. |
| O15 | The other pages (Build Plans, Build Score, Inventory Balance, Supply–Demand Context) show scenario A only | Make them follow a selected scenario once the scenario pages are agreed. |
| O16 | Planning priors as an editable table | Routing rule, targets and lead times currently live in `scenarios.py` (`Case`) and `config.py`. Next: one table the UI and an LLM can change. |
