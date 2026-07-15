"""Shared test configuration for the src-layout package."""

from __future__ import annotations

import sys
from pathlib import Path


# Tests run from a checkout before the package is installed in editable mode.
SOURCE_ROOT = Path(__file__).parents[1] / "src"
sys.path.insert(0, str(SOURCE_ROOT))
