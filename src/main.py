"""Redwheel — the pipeline, step by step. Run cell by cell in VS Code (Shift+Enter)."""
# %% setup
import pandas as pd

from redwheel import aux_fns, read, rtn
from redwheel.config import CHANNELS
from redwheel.utils import DQ

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 20)

# %% 1.1 orders: read three channels, union, flag backlog
orders = aux_fns.union_orders(read.read_dtc(), read.read_dealer(), read.read_commercial())

print(f"{len(orders):,} lines |", orders["channel"].value_counts().to_dict())
print("duplicate ids:", orders.duplicated(["channel", "order_id"]).sum())
print("fulfilled w/o ship date:", (orders.fulfilled & orders.ship_date.isna()).sum(),
      "| unfulfilled with ship date:", (~orders.fulfilled & orders.ship_date.notna()).sum(),
      "| ship before order:", (orders.ship_date < orders.order_date).sum())
print("skus with conflicting attributes:",
      int((orders.groupby("sku")[["class", "trim", "size"]].nunique() > 1).any(axis=1).sum()))


#%%
backlog = orders[orders.open_at_snapshot].pivot_table(
    index="sku", columns="channel", values="qty", aggfunc="sum", fill_value=0,
    margins=True, margins_name="total")
backlog

# %% 1.2 inventory: plant + dealer stock in one table, nettable flag
inventory = aux_fns.union_inventory(read.read_plant_inventory(), read.read_dealer_stock())

print("dealer count dates:", inventory.loc[~inventory.nettable, "as_of_date"].min().date(),
      "->", inventory.loc[~inventory.nettable, "as_of_date"].max().date())
dealers_inv = set(inventory.loc[~inventory.nettable, "location_code"])
dealers_ord = set(orders.loc[orders.channel == "dealer", "party_id"])
print("dealers in stock report:", len(dealers_inv), "| in orders:", len(dealers_ord),
      "| in one but not the other:", len(dealers_inv ^ dealers_ord))
print("skus not in orders:", set(inventory.sku) - set(orders.sku))

inventory.pivot_table(index="sku", columns="location_code", values="on_hand", aggfunc="sum",
                      fill_value=0)[["RENO-FG", "CMH-DC"]].assign(
    dealers=inventory[~inventory.nettable].groupby("sku").on_hand.sum())

# %% 1.3 capacity + forecast
capacity = aux_fns.build_capacity(read.read_capacity())
forecast = aux_fns.union_forecast(*(read.read_forecast(c) for c in CHANNELS))

for name, df, key in [("capacity", capacity, ["week_start", "line_id"]),
                      ("forecast", forecast, ["week_start", "sku", "channel"])]:
    wk = df.week_start.drop_duplicates().sort_values()
    print(f"{name}: {wk.iloc[0].date()} -> {wk.iloc[-1].date()}, {len(wk)} weeks",
          "| all Mondays:", (wk.dt.dayofweek == 0).all(),
          "| gaps:", int((wk.diff().dt.days.dropna() != 7).sum()),
          "| dup keys:", int(df.duplicated(key).sum()))
print("forecast negatives:", int((forecast.forecast_units < 0).sum()),
      "| rows per week:", forecast.groupby("week_start").size().unique())

# capacity is flat within a fiscal year (Sep-Aug): one value per line per FY
fy = capacity.week_start.dt.year - (capacity.week_start.dt.month < 9)
capacity.groupby(["line_id", fy]).capacity_units.agg(["min", "max"]).unstack()

# %% 1.4 dimensions: sku, line, week, policy
dim_sku = aux_fns.build_dim_sku(orders)
dim_line = aux_fns.build_dim_line(dim_sku)
dim_week = aux_fns.build_dim_week(forecast)
dim_location = aux_fns.build_dim_location(dim_line)
dim_policy = aux_fns.build_dim_policy()

print("every fact sku in dim_sku:",
      set(orders.sku) | set(inventory.sku) | set(forecast.sku) <= set(dim_sku.sku))
print("every capacity line in dim_line:", set(capacity.line_id) <= set(dim_line.line_id))
print("plan weeks:", int(dim_week.in_plan_horizon.sum()), "| total weeks:", len(dim_week))
print(dim_line, "\n", dim_policy)
print(dim_location[["location_id", "location_class", "parent", "ours"]])
dim_sku

# %% 1.5 opening position: nettable on-hand - backlog, per sku
opening = aux_fns.build_opening_position(orders, inventory)
print("total backlog:", opening.backlog.sum(), "| total net:", opening.net0.sum())
opening

# %% data-quality log
pd.DataFrame.from_dict(DQ, orient="index")

# %% 2.1 the object: descriptions (item, location, week)
m = {"fact_orders": orders, "fact_inventory": inventory, "fact_capacity": capacity,
     "fact_forecast": forecast, "dim_sku": dim_sku, "dim_location": dim_location}
items = dim_sku.rename(columns={"sku": "item"})
weeks = (dim_week[dim_week.in_plan_horizon].rename(columns={"week_idx": "t"})[["t", "week_start"]]
         .reset_index(drop=True))
print(len(items), "items |", len(dim_location), "locations |", len(weeks), "weeks:",
      weeks.week_start.iloc[0].date(), "->", weeks.week_start.iloc[-1].date())

# %% 2.2 resources: generated from the location classes
resources = rtn.generate_resources(items, dim_location)
print(len(resources), "resources")
resources.groupby(["kind", "location"]).size().unstack(fill_value=0)

# %% 2.3 tasks + arrows: generated from what is built where and what can go where
routing, routes = aux_fns.build_routing(dim_sku), aux_fns.build_routes()
tasks, arrows = rtn.generate_tasks(routing, routes, items, dim_location)
print(routes, "\n")
print(len(tasks), "tasks", tasks.kind.value_counts().to_dict(), "|", len(arrows), "arrows")
arrows[arrows.task_id.str.contains("RW-9304")]          # every arrow touching one SKU

# %% 2.4 numbers: opening levels and weekly arrivals
obj = rtn.RTN(items=items, locations=dim_location, weeks=weeks,
              resources=resources, tasks=tasks, arrows=arrows,
              opening=aux_fns.build_opening(m, resources),
              arrivals=aux_fns.build_arrivals(m, resources, weeks))
rtn.validate(obj)
kind_loc = resources.set_index("resource_id")[["kind", "location"]]
print("arrivals: forecast", int(obj.arrivals[kind_loc.kind == "order"].values.sum()),
      "| capacity", int(obj.arrivals[kind_loc.kind == "capacity"].values.sum()))
obj.opening.groupby([kind_loc.kind, kind_loc.location]).sum().unstack(fill_value=0)

# %% 2.5 run the equation with no plan: nothing built, nothing shipped
X = rtn.levels(obj)
npos = rtn.net_position(obj, X)
print("opening net position matches 1.5:",
      npos[0].astype(int).equals(opening.set_index("sku").net0.rename_axis("item")))
npos[[0, 1, 13, 26, 52, 121]].astype(int)                # weeks 0, 1, 13, 26, 52, 121

# %%
