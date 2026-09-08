import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent.parent / "frontend" / "pages" / "2_Video_Analysis.py"))