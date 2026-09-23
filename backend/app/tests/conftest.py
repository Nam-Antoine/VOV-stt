"""Pytest setup: make ``app`` importable no matter where pytest is invoked from."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def raw_doc() -> dict:
    """A small but complete PLAN §5 raw JSON document, fillers included."""
    return json.loads((FIXTURES / "sample_raw.json").read_text(encoding="utf-8"))
