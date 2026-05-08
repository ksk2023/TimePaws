from __future__ import annotations

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    ROOT = Path(__file__).resolve().parent
    SRC = ROOT / "src"
    if SRC.exists() and str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))

from winvibetime.app import main as app_main


if __name__ == "__main__":
    raise SystemExit(app_main())
