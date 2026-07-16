from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_repository_has_one_thin_notebook() -> None:
    notebooks = sorted((ROOT / "notebooks").glob("*.ipynb"))
    assert [path.name for path in notebooks] == ["retail_portfolio.ipynb"]
    notebook = json.loads(notebooks[0].read_text(encoding="utf-8"))
    assert notebook["metadata"]["kernelspec"]["name"] == "retail-portfolio"
    code = []
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            assert cell["execution_count"] is None
            assert cell["outputs"] == []
            code.append("".join(cell["source"]))
    combined = "\n".join(code)
    assert "compare_strategies" in combined
    assert "build_stack" in combined
    assert "APPROVED_STRATEGIES" in combined
