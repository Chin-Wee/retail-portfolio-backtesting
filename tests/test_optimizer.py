from __future__ import annotations

import numpy as np
import pandas as pd

from retail_sp500.optimizer import (
    AutoSearchConfig,
    StrategyCandidate,
    _choose_locked_candidate,
    auto_search_dca,
)


def _asset(
    start: str = "2000-01-03",
    end: str = "2025-12-31",
    *,
    daily_growth: float = 0.0,
) -> pd.DataFrame:
    index = pd.date_range(start, end, freq="B")
    t = np.arange(len(index), dtype=float)
    close = 100.0 * np.exp(daily_growth * t)
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": np.full(len(index), 1_000_000.0),
        },
        index=index,
    )


def _small_search(**overrides: object) -> AutoSearchConfig:
    values: dict[str, object] = {
        "capital_sgd": 1_000_000.0,
        "evaluation_years": 2,
        "cash_yield_annual": 0.0,
        "market": "us",
        "coarse_deployments": (1, 3, 6),
        "coarse_buy_days": (1, 10),
        "step_months": 12,
        "minimum_windows": 11,
        "top_coarse": 3,
        "top_finalists": 4,
        "refine_month_radius": 1,
        "refine_day_radius": 1,
    }
    values.update(overrides)
    return AutoSearchConfig(**values)


def test_rising_market_auto_search_prefers_immediate_early_deployment() -> None:
    result = auto_search_dca(
        _asset(daily_growth=0.00025),
        config=_small_search(),
    )

    assert result.winner.deployment_months == 1
    assert result.winner.buy_day <= 2
    assert result.holdout["median_delta_vs_immediate"] >= -0.01


def test_auto_search_is_deterministic() -> None:
    asset = _asset(daily_growth=0.00008)
    config = _small_search()

    first = auto_search_dca(asset, config=config)
    second = auto_search_dca(asset, config=config)

    assert first.winner == second.winner
    assert first.validation == second.validation
    assert first.holdout == second.holdout


def test_search_table_never_exposes_holdout_scores_for_candidate_selection() -> None:
    result = auto_search_dca(_asset(daily_growth=0.00005), config=_small_search())

    assert not any(column.startswith("holdout_") for column in result.search_table.columns)
    assert set(result.holdout_table["deployment_months"]) == {result.winner.deployment_months}
    assert set(result.windows["partition"]) == {"selection", "validation", "holdout"}


def test_local_refinement_adds_configs_outside_the_coarse_grid() -> None:
    config = _small_search(
        coarse_deployments=(1, 6),
        coarse_buy_days=(1, 10),
        top_coarse=2,
        refine_month_radius=1,
        refine_day_radius=1,
    )
    result = auto_search_dca(_asset(daily_growth=0.0001), config=config)

    coarse_count = (
        len(config.coarse_deployments)
        * len(config.coarse_buy_days)
        * 2
    )
    assert result.candidate_count > coarse_count


def test_stable_validation_plateau_can_beat_isolated_spike() -> None:
    isolated = StrategyCandidate(12, 10, "fixed", "none")
    stable = StrategyCandidate(6, 5, "fixed", "none")
    stable_neighbor = StrategyCandidate(7, 5, "fixed", "none")

    finalists = pd.DataFrame.from_records(
        [
            {
                "candidate_key": isolated.key,
                "candidate_label": isolated.label,
                "deployment_months": isolated.deployment_months,
                "buy_day": isolated.buy_day,
                "pricing": isolated.pricing,
                "fx_method": isolated.fx_method,
                "selection_robust_score": 1.0,
                "validation_robust_score": 1.10,
            },
            {
                "candidate_key": stable.key,
                "candidate_label": stable.label,
                "deployment_months": stable.deployment_months,
                "buy_day": stable.buy_day,
                "pricing": stable.pricing,
                "fx_method": stable.fx_method,
                "selection_robust_score": 0.9,
                "validation_robust_score": 1.06,
            },
        ]
    )
    validation_pool = pd.DataFrame.from_records(
        [
            {
                "candidate_key": isolated.key,
                "candidate_label": isolated.label,
                "deployment_months": isolated.deployment_months,
                "buy_day": isolated.buy_day,
                "pricing": isolated.pricing,
                "fx_method": isolated.fx_method,
                "validation_robust_score": 1.10,
            },
            {
                "candidate_key": StrategyCandidate(11, 10, "fixed", "none").key,
                "candidate_label": "isolated neighbor",
                "deployment_months": 11,
                "buy_day": 10,
                "pricing": "fixed",
                "fx_method": "none",
                "validation_robust_score": 0.70,
            },
            {
                "candidate_key": stable.key,
                "candidate_label": stable.label,
                "deployment_months": stable.deployment_months,
                "buy_day": stable.buy_day,
                "pricing": stable.pricing,
                "fx_method": stable.fx_method,
                "validation_robust_score": 1.06,
            },
            {
                "candidate_key": stable_neighbor.key,
                "candidate_label": stable_neighbor.label,
                "deployment_months": stable_neighbor.deployment_months,
                "buy_day": stable_neighbor.buy_day,
                "pricing": stable_neighbor.pricing,
                "fx_method": stable_neighbor.fx_method,
                "validation_robust_score": 1.05,
            },
        ]
    )

    chosen = _choose_locked_candidate(finalists, validation_pool)

    assert chosen.iloc[0]["candidate_key"] == stable.key
