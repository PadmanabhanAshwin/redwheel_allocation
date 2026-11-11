# Redwheel build planner

Master data → allocation engine → planner UI for Redwheel's weekly build plan (Sep 2026 – Dec 2028).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Run

```bash
python -m redwheel.master     # build + validate master tables -> outputs/
pytest                        # closure checks against independently derived figures
streamlit run app/app.py      # planner UI
```

## Layout

| Path | What |
|---|---|
| `data/` | The nine CSVs exactly as Redwheel shared them (never edited) |
| `src/redwheel/` | `config` (dates, policy) · `master` (step 1, #%% cells) · engine (to come) |
| `app/` | Streamlit UI |
| `docs/` | Assumptions and data-quality log |
| `scripts/explore/` | Original profiling scripts (reference only) |
| `outputs/` | Generated tables (git-ignored) |

Dependencies: one `requirements.txt`, direct dependencies pinned.
