"""Make repository packages importable when scripts are run directly."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "packages" / "irrivise_core", ROOT / "services" / "api"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))

# Windows consoles default to a legacy code page that cannot print characters such as "−", "³" or "Σ"
# used in result summaries; print UTF-8 instead of crashing.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")
