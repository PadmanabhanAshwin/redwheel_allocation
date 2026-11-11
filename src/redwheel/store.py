"""Saved scenarios: a scenario's name, description, parent and priors table as one JSON file. Results are not
stored: a run takes about a second and is recomputed from the table."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from redwheel import priors
from redwheel.config import OUT_DIR
from redwheel.scenarios import Case

FOLDER = OUT_DIR / "scenarios"


def save(case: Case, folder: Path | None = None) -> Path:
    folder = folder or FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{case.key}.json"
    path.write_text(json.dumps({"key": case.key, "name": case.name, "summary": case.summary, "parent": case.parent,
                                "priors": priors.normalise(case.priors).to_dict("records")}, indent=1))
    return path


def load_all(folder: Path | None = None) -> dict:
    """{key: Case} for every saved scenario, in key order."""
    folder = folder or FOLDER
    out = {}
    for path in sorted(folder.glob("*.json")) if folder.exists() else []:
        d = json.loads(path.read_text())
        out[d["key"]] = Case(d["key"], d["name"], pd.DataFrame(d["priors"], columns=priors.COLUMNS),
                             d.get("summary", ""), d.get("parent", ""))
    return out


def delete(key: str, folder: Path | None = None) -> None:
    ((folder or FOLDER) / f"{key}.json").unlink(missing_ok=True)
