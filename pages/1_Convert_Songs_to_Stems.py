import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "frontend"))
runpy.run_path(str(Path(__file__).resolve().parent.parent / "frontend" / "pages" / "1_Convert_Songs_to_Stems.py"))