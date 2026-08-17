from __future__ import annotations

import ast
from pathlib import Path


def test_hifire_page_parses_and_exposes_required_controls() -> None:
    path = Path("pages/1_HiFIRE_Plan.py")
    source = path.read_text(encoding="utf-8")
    ast.parse(source)

    assert "Singapore HiFIRE Life Plan" in source
    assert "expected gross monthly salary" in source
    assert "monthly living expenses" in source
    assert "HDB / BTO housing" in source
    assert "Include a car purchase" in source
    assert "Number of children" in source
    assert "Run HiFIRE life plan" in source
    assert "project_life_plan" in source
