"""Redwheel build plan — planner UI.   Run:  streamlit run app/app.py

Navigation: an overview, then one section per scenario (summary, then the plan in detail), then the model.
Every page ends with links to the previous and next page, in the same order as the navigation."""
import importlib
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))       # pages import the shared ui module

from redwheel import scenarios as sc                  # noqa: E402

st.set_page_config(page_title="Redwheel build plan", layout="wide")

SCENARIO_PAGES = [("scenario_summary", "Summary", "summary"), ("network", "Network", "network"),
                  ("build_plan", "Build Plans", "build-plans"),
                  ("build_score", "Build Score", "build-score"), ("balance", "Inventory Balance by SKU", "balance")]


def scenario_page(module: str, title: str, slug: str, key: str) -> st.Page:
    def page():
        importlib.import_module(f"views.{module}").render(key)
    page.__name__ = f"{slug}_{key}"
    return st.Page(page, title=title, url_path=f"{key.lower()}-{slug}")


sections = {"Overview": [st.Page("views/context.py", title="Supply–Demand Context", default=True),
                         st.Page("views/scenario_list.py", title="Scenarios"),
                         st.Page("views/scenario_compare.py", title="Scenario Comparison")]}
for key, case in sc.CASES.items():
    sections[case.name] = [scenario_page(*p, key) for p in SCENARIO_PAGES]
sections["Model"] = [st.Page("views/object_encoding.py", title="Object Encoding"),
                     st.Page("views/demand.py", title="Demand Sources"),
                     st.Page("views/validation.py", title="Model Validation")]

current = st.navigation(sections, position="top")
current.run()

# ---------------- previous / next, in navigation order ----------------
flow = [(section, p) for section, pages in sections.items() for p in pages]
i = next(n for n, (_, p) in enumerate(flow) if p.url_path == current.url_path)
st.divider()
left, _, right = st.columns([2, 1, 2])
if i > 0:
    section, p = flow[i - 1]
    left.page_link(p, label=f"← {section} · {p.title}")
if i < len(flow) - 1:
    section, p = flow[i + 1]
    right.page_link(p, label=f"Next: {section} · {p.title} →")
