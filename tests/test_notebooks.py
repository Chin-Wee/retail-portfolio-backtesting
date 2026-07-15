from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = (
    "01_strategy_comparison.ipynb",
    "02_parameter_experiments.ipynb",
    "03_rolling_window_analysis.ipynb",
    "04_limit_order_research.ipynb",
    "05_calmar_ratio_exploration.ipynb",
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


def test_every_notebook_uses_real_daily_data_only() -> None:
    forbidden = ("synthetic_market_data", "load_shiller_data", "BacktestConfig", "USE_SYNTHETIC")
    for filename in NOTEBOOKS:
        notebook = json.loads((ROOT / "notebooks" / filename).read_text(encoding="utf-8"))
        sources = "\n".join(_code_sources(notebook))
        assert "load_or_fetch_twelve_data_daily" in sources
        assert "TWELVE_DATA_API_KEY" in sources
        for token in forbidden:
            assert token not in sources


def test_notebooks_end_in_strategy_charts_and_calmar_exploration() -> None:
    combined = {
        filename: "\n".join(
            _code_sources(json.loads((ROOT / "notebooks" / filename).read_text(encoding="utf-8")))
        )
        for filename in NOTEBOOKS
    }
    assert "intraday_low_from_previous_close" in combined[NOTEBOOKS[0]]
    assert "evaluate_recurring_limit_grid" in combined[NOTEBOOKS[1]]
    assert "calmar_by_discount_figure" in combined[NOTEBOOKS[1]]
    assert "walk_forward_recurring_limit_selection" in combined[NOTEBOOKS[2]]
    assert '"ending_excess_value", "calmar_ratio"' in combined[NOTEBOOKS[2]]
    assert "compare_recurring_limit_strategies" in combined[NOTEBOOKS[3]]
    assert "strategy_calmar_ranking_figure" in combined[NOTEBOOKS[3]]
    assert "strategy_wealth_figure" in combined[NOTEBOOKS[3]]
    assert "strategy_drawdown_figure" in combined[NOTEBOOKS[3]]
    assert "calmar_by_discount_figure" in combined[NOTEBOOKS[4]]
    assert "strategy_return_drawdown_figure" in combined[NOTEBOOKS[4]]


def test_shell_scripts_reference_daily_calmar_and_graph_workflow() -> None:
    setup = (ROOT / "scripts" / "setup_jupyter.sh").read_text(encoding="utf-8")
    runner = (ROOT / "scripts" / "run_daily_limit_research.sh").read_text(encoding="utf-8")
    assert "TWELVE_DATA_API_KEY" in setup
    assert "sp500-limit-orders" in setup
    assert "05_calmar_ratio_exploration.ipynb" in setup
    assert "selection-metric" in runner
    assert "calmar_ratio" in runner
