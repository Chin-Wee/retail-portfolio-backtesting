from __future__ import annotations

import ast
from pathlib import Path


def test_streamlit_app_source_parses() -> None:
    source = Path("app.py").read_text(encoding="utf-8")
    ast.parse(source, filename="app.py")


def test_auto_strategy_is_the_default_product_tab() -> None:
    source = Path("app.py").read_text(encoding="utf-8")
    assert '["Auto strategy", "Personal plan", "Manual DCA"]' in source
    assert "auto_search_dca(" in source
