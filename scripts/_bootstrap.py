"""Make repository packages importable when scripts are run directly."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "packages" / "irrivise_core", ROOT / "services" / "api"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))
