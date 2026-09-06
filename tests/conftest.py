"""Make the project's non-packaged source dirs importable from tests."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for sub in ("development",):
    path = str(REPO_ROOT / sub)
    if path not in sys.path:
        sys.path.insert(0, path)
