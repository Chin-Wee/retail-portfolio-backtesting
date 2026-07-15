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


def test_committed_notebooks_are_thin_and_output_free() -> None:
    for filename in NOTEBOOKS:
        path = ROOT / "notebooks" / filename
        notebook = json.loads(path.read_text(encoding="utf-8"))

        assert notebook["nbformat"] == 4
        assert notebook["metadata"]["kernelspec"]["name"] == "retail-portfolio-backtesting"

        code_sources = []
        for cell in notebook["cells"]:
            if cell["cell_type"] != "code":
                continue
            assert cell["execution_count"] is None
            assert cell["outputs"] == []
            source = cell["source"]
            code_sources.append("".join(source) if isinstance(source, list) else source)

        assert code_sources
        assert any("retail_sp500" in source for source in code_sources)
