from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = (
    "01_strategy_comparison.ipynb",
    "02_parameter_experiments.ipynb",
    "03_rolling_window_analysis.ipynb",
    "04_limit_order_research.ipynb",
)


def _code_sources(notebook: dict[str, object]) -> list[str]:
    sources: list[str] = []
    for cell in notebook["cells"]:  # type: ignore[index]
        if cell["cell_type"] != "code":
            continue
        assert cell["execution_count"] is None
        assert cell["outputs"] == []
        source = cell["source"]
        sources.append("".join(source) if isinstance(source, list) else source)
    return sources


def test_committed_notebooks_are_thin_and_output_free() -> None:
    for filename in NOTEBOOKS:
        path = ROOT / "notebooks" / filename
        notebook = json.loads(path.read_text(encoding="utf-8"))
        assert notebook["nbformat"] == 4
        assert notebook["metadata"]["kernelspec"]["name"] == "retail-portfolio-backtesting"
        sources = _code_sources(notebook)
        assert sources
        assert any("retail_sp500" in source for source in sources)


def test_research_notebooks_do_not_default_to_synthetic_data() -> None:
    for filename in NOTEBOOKS[:3]:
        notebook = json.loads((ROOT / "notebooks" / filename).read_text(encoding="utf-8"))
        sources = "\n".join(_code_sources(notebook))
        assert "USE_SYNTHETIC = False" in sources


def test_limit_order_notebook_uses_real_daily_path() -> None:
    notebook = json.loads(
        (ROOT / "notebooks" / "04_limit_order_research.ipynb").read_text(encoding="utf-8")
    )
    sources = "\n".join(_code_sources(notebook))
    assert "load_or_fetch_twelve_data_daily" in sources
    assert "evaluate_limit_discount_grid" in sources
    assert "synthetic_market_data" not in sources
