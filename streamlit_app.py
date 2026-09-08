import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "frontend"))
import app  # noqa: F401,E402
