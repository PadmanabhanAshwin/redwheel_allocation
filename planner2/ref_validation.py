"""Reference page from the first UI (app/views/validation.py), run unchanged."""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).parents[1] / "app" / "views" / "validation.py"))
