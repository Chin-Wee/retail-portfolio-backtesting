from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from .broker import BrokerFeeConfig, ibkr_pro_preset
from .currency import prior_fx_close
from .data import validate_daily
from .dca import DcaConfig, _run_dca_window_validated
from .engine import _first_salary_session as first_salary_session

Pricing = Literal["fixed", "tiered"]
FxMethod = Literal["manual_spot", "autofx", "none"]
Market = Literal["us", "lse_usd"]


@dataclass(frozen=True, order=True)
class StrategyCandidate:
    deployment_months: int
    buy_day: int
    pricing: Pricing
    fx_method: FxMethod

    @property
    def key(self) -> str:
        return (
            f"m{self.deployment_months:02d}-d{self.buy_day:02d}-"
            f"{self.pricing}-{self.fx_method}"
        )

    @property
    def label(self) -> str:
        deployment = (
            "Lump sum" if self.deployment_months == 1 else f"{self.deployment_months}-month DCA"
        )
        fx = {
            "manual_spot": "manual FX",
            "autofx": "AutoFX",
            "none": "no FX",
        }[self.fx_method]
        return f"{deployment}, buy day {self.buy_day}, {self.pricing.title()} + {fx}"


@dataclass(frozen=True)
class AutoSearchConfig:
    capital_sgd: float = 1_000_000.0
    evaluation_years: int = 5
    cash_yield_annual: float = 0.0
    market: Market = "us"
    extra_trade_cost_bps: float = 0.0
    coarse_deployments: tuple[int, ...] = (1, 3, 6, 12, 18, 24, 36)
    coarse_buy_days: tuple[int, ...] = (1, 8, 15, 22)
    step_months: int = 6
    minimum_windows: int = 15
    top_coarse: int = 6
    top_finalists: int = 10
    refine_month_radius: int = 2
    refine_day_radius: int = 2

    def __post_init__(self) -> None:
        if self.capital_sgd <= 0.0:
            raise ValueError("capital_sgd must be positive")
        if self.evaluation_years < 1:
            raise ValueError("evaluation_years must be positive")
        if self.cash_yield_annual <= -1.0:
            raise ValueError("cash_yield_annual must be greater than -100%")
        if self.extra_trade_cost_bps < 0.0:
            raise ValueError("extra_trade_cost_bps cannot be negative")
        if self.step_months < 1:
            raise ValueError("step_months must be positive")
        if self.minimum_windows < 11:
            raise ValueError("minimum_windows must be at least 11")
        if not self.coarse_deployments or min(self.coarse_deployments) < 1:
            raise ValueError("coarse deployments must be positive")
        if not self.coarse_buy_days or not all(1 <= day <= 25 for day in self.coarse_buy_days):
            raise ValueError("automatic buy-day search must stay between 1 and 25")
        if min(self.top_coarse, self.top_finalists) < 1:
            raise ValueError("search finalist counts must be positive")
        if min(self.refine_month_radius, self.refine_day_radius) < 0:
            raise ValueError("refinement radii cannot be negative")


@dataclass
class AutoSearchResult:
    winner: StrategyCandidate
    selection: dict[str, float | int]
    validation: dict[str, float | int]
    holdout: dict[str, float | int]
    search_table: pd.DataFrame
    holdout_table: pd.DataFrame
    windows: pd.DataFrame
    candidate_count: int
    step_months: int
    stability_label: str
    overfit_warning: str | None


def _candidate_from_row(row: object) -> StrategyCandidate:
    return StrategyCandidate(
        int(getattr(row, "deployment_months")),
        int(getattr(row, "buy_day")),
        str(getattr(row, "pricing")),
        str(getattr(row, "fx_method")),
    )


def _complete_windows(
    asset: pd.DataFrame,
    *,
    evaluation_years: int,
    step_months: int,
) -> pd.DataFrame:
    months = asset.index.to_period("M").unique()
    records: list[dict[str, object]] = []
    for offset in range(0, len(months), step_months):
        month = months[offset]
        start = first_salary_session(asset.index, month, 1)
        if start is None:
            continue
        start = pd.Timestamp(start)
        target_end = start + pd.DateOffset(years=evaluation_years)
        if pd.Timestamp(asset.index[-1]) < target_end:
            break
        eligible = asset.index[(asset.index >= start) & (asset.index <= target_end)]
        if len(eligible) == 0:
            continue
        records.append(
            {
                "window": len(records),
                "start": start,
                "end": pd.Timestamp(eligible[-1]),
            }
        )
    return pd.DataFrame.from_records(records)


def _search_windows(asset: pd.DataFrame, config: AutoSearchConfig) -> tuple[pd.DataFrame, int]:
    windows = _complete_windows(
        asset,
        evaluation_years=config.evaluation_years,
        step_months=config.step_months,
    )
    used_step = config.step_months
    if len(windows) < config.minimum_windows and config.step_months != 1:
        windows = _complete_windows(
            asset,
            evaluation_years=config.evaluation_years,
            step_months=1,
        )
        used_step = 1
    if len(windows) < config.minimum_windows:
        raise ValueError(
            "not enough complete historical windows for automatic tuning; "
            "use a shorter evaluation horizon or load more history"
        )
    return windows, used_step


def _split_windows(windows: pd.DataFrame) -> pd.DataFrame:
    ordered = windows.sort_values("start").reset_index(drop=True).copy()
    count = len(ordered)
    holdout_n = max(3, round(count * 0.20))
    validation_n = max(3, round(count * 0.20))
    selection_n = count - validation_n - holdout_n
    if selection_n < 5:
        raise ValueError("automatic tuning requires at least five selection windows")

    ordered["partition"] = "selection"
    ordered.loc[selection_n : selection_n + validation_n - 1, "partition"] = "validation"
    ordered.loc[selection_n + validation_n :, "partition"] = "holdout"
    return ordered


def _broker(candidate: StrategyCandidate, config: AutoSearchConfig) -> BrokerFeeConfig:
    return ibkr_pro_preset(
        market=config.market,
        pricing=candidate.pricing,
        fx_method=candidate.fx_method,
        extra_trade_cost_bps=config.extra_trade_cost_bps,
    )


def _run_candidate(
    asset: pd.DataFrame,
    fx_rates: pd.Series,
    candidate: StrategyCandidate,
    config: AutoSearchConfig,
    windows: pd.DataFrame,
) -> pd.DataFrame:
    dca_config = DcaConfig(
        capital_sgd=config.capital_sgd,
        deployment_months=(candidate.deployment_months,),
        evaluation_years=config.evaluation_years,
        buy_day=candidate.buy_day,
        cash_yield_annual=config.cash_yield_annual,
    )
    broker = _broker(candidate, config)
    records: list[dict[str, object]] = []
    for window in windows.itertuples(index=False):
        result = _run_dca_window_validated(
            asset,
            fx_rates,
            start=pd.Timestamp(window.start),
            deployment_months=candidate.deployment_months,
            config=dca_config,
            broker=broker,
            evaluation_end=pd.Timestamp(window.end),
            cash_start=pd.Timestamp(window.start),
        )
        result["window"] = int(window.window)
        records.append(result)
    return pd.DataFrame.from_records(records)


def _benchmark_candidate(candidate: StrategyCandidate) -> StrategyCandidate:
    return StrategyCandidate(1, 1, candidate.pricing, candidate.fx_method)


def _metrics(
    candidate_results: pd.DataFrame,
    benchmark_results: pd.DataFrame,
    *,
    capital_sgd: float,
) -> dict[str, float | int]:
    joined = candidate_results.merge(
        benchmark_results[["window", "ending_wealth_sgd"]].rename(
            columns={"ending_wealth_sgd": "benchmark_wealth_sgd"}
        ),
        on="window",
        how="inner",
        validate="one_to_one",
    )
    if joined.empty:
        raise ValueError("candidate and benchmark have no common windows")

    ending_ratio = joined["ending_wealth_sgd"].astype(float) / capital_sgd
    returns = ending_ratio - 1.0
    benchmark = joined["benchmark_wealth_sgd"].astype(float)
    delta_pct = joined["ending_wealth_sgd"].astype(float) / benchmark - 1.0
    win_rate = float((delta_pct > 0.0).mean())
    median_return = float(returns.median())
    p10_return = float(returns.quantile(0.10))
    median_delta = float(delta_pct.median())
    p10_delta = float(delta_pct.quantile(0.10))
    robust_score = (
        0.50 * median_return
        + 0.30 * p10_return
        + 0.15 * median_delta
        + 0.05 * (win_rate - 0.50)
    )
    return {
        "windows": int(len(joined)),
        "median_return": median_return,
        "p10_return": p10_return,
        "win_rate_vs_immediate": win_rate,
        "median_delta_vs_immediate": median_delta,
        "p10_delta_vs_immediate": p10_delta,
        "median_ending_wealth_sgd": float(joined["ending_wealth_sgd"].median()),
        "p10_ending_wealth_sgd": float(joined["ending_wealth_sgd"].quantile(0.10)),
        "median_fees_sgd": float(joined["total_fees_sgd"].median()),
        "robust_score": float(robust_score),
    }


def _candidate_grid(config: AutoSearchConfig, *, has_fx: bool) -> set[StrategyCandidate]:
    max_months = config.evaluation_years * 12
    deployments = [month for month in config.coarse_deployments if month <= max_months]
    if 1 not in deployments:
        deployments.append(1)
    fx_methods: tuple[FxMethod, ...] = ("manual_spot", "autofx") if has_fx else ("none",)
    return {
        StrategyCandidate(month, day, pricing, fx_method)
        for month in deployments
        for day in config.coarse_buy_days
        for pricing in ("fixed", "tiered")
        for fx_method in fx_methods
    }


def _refine_candidates(
    seeds: list[StrategyCandidate],
    config: AutoSearchConfig,
    *,
    month_radius: int | None = None,
    day_radius: int | None = None,
) -> set[StrategyCandidate]:
    month_radius = config.refine_month_radius if month_radius is None else month_radius
    day_radius = config.refine_day_radius if day_radius is None else day_radius
    max_months = config.evaluation_years * 12
    refined: set[StrategyCandidate] = set(seeds)
    for seed in seeds:
        month_min = max(1, seed.deployment_months - month_radius)
        month_max = min(max_months, seed.deployment_months + month_radius)
        day_min = max(1, seed.buy_day - day_radius)
        day_max = min(25, seed.buy_day + day_radius)
        for month in range(month_min, month_max + 1):
            for day in range(day_min, day_max + 1):
                refined.add(StrategyCandidate(month, day, seed.pricing, seed.fx_method))
    return refined


def _direct_neighbors(
    candidate: StrategyCandidate,
    candidates: set[StrategyCandidate],
) -> list[StrategyCandidate]:
    return [
        other
        for other in candidates
        if other != candidate
        and other.pricing == candidate.pricing
        and other.fx_method == candidate.fx_method
        and abs(other.deployment_months - candidate.deployment_months) <= 1
        and abs(other.buy_day - candidate.buy_day) <= 1
    ]


def _sort_metrics(frame: pd.DataFrame, score_column: str) -> pd.DataFrame:
    return frame.sort_values(
        [score_column, "deployment_months", "buy_day", "candidate_key"],
        ascending=[False, True, True, True],
    ).reset_index(drop=True)


def _choose_locked_candidate(
    finalists: pd.DataFrame,
    validation_pool: pd.DataFrame,
) -> pd.DataFrame:
    pool_by_key = validation_pool.set_index("candidate_key")
    candidate_objects = {
        row.candidate_key: _candidate_from_row(row)
        for row in validation_pool.itertuples(index=False)
    }
    available = set(candidate_objects.values())
    rows: list[dict[str, object]] = []
    for finalist in finalists.itertuples(index=False):
        candidate = candidate_objects[str(finalist.candidate_key)]
        neighbors = _direct_neighbors(candidate, available)
        neighbor_scores = [
            float(pool_by_key.loc[neighbor.key, "validation_robust_score"])
            for neighbor in neighbors
            if neighbor.key in pool_by_key.index
        ]
        validation_score = float(finalist.validation_robust_score)
        neighborhood = (
            float(pd.Series(neighbor_scores, dtype=float).median())
            if neighbor_scores
            else validation_score
        )
        row = finalist._asdict()
        row.update(
            {
                "neighborhood_robust_score": neighborhood,
                "neighbor_count": len(neighbor_scores),
                "stability_gap": validation_score - neighborhood,
                "locked_score": 0.75 * validation_score + 0.25 * neighborhood,
            }
        )
        rows.append(row)
    return _sort_metrics(pd.DataFrame.from_records(rows), "locked_score")


def _evaluate_set(
    asset: pd.DataFrame,
    fx_rates: pd.Series,
    candidates: set[StrategyCandidate],
    config: AutoSearchConfig,
    windows: pd.DataFrame,
    partition_name: str,
) -> pd.DataFrame:
    benchmark_cache: dict[tuple[Pricing, FxMethod], pd.DataFrame] = {}
    rows: list[dict[str, object]] = []
    for candidate in sorted(candidates):
        broker_key = (candidate.pricing, candidate.fx_method)
        try:
            if broker_key not in benchmark_cache:
                benchmark_cache[broker_key] = _run_candidate(
                    asset,
                    fx_rates,
                    _benchmark_candidate(candidate),
                    config,
                    windows,
                )
            result = _run_candidate(asset, fx_rates, candidate, config, windows)
        except ValueError:
            continue
        metrics = _metrics(
            result,
            benchmark_cache[broker_key],
            capital_sgd=config.capital_sgd,
        )
        rows.append(
            {
                "candidate_key": candidate.key,
                "candidate_label": candidate.label,
                "deployment_months": candidate.deployment_months,
                "buy_day": candidate.buy_day,
                "pricing": candidate.pricing,
                "fx_method": candidate.fx_method,
                **{f"{partition_name}_{key}": value for key, value in metrics.items()},
            }
        )
    if not rows:
        raise ValueError(f"no valid candidates were available for {partition_name}")
    return pd.DataFrame.from_records(rows)


def auto_search_dca(
    asset_daily: pd.DataFrame,
    *,
    config: AutoSearchConfig = AutoSearchConfig(),
    fx_daily: pd.DataFrame | None = None,
) -> AutoSearchResult:
    """Search DCA and IBKR settings without using the holdout to choose the winner."""

    asset = validate_daily(asset_daily)
    fx_rates = (
        pd.Series(1.0, index=asset.index, name="fx_close", dtype=float)
        if fx_daily is None
        else prior_fx_close(asset.index, fx_daily)
    )
    windows, used_step = _search_windows(asset, config)
    windows = _split_windows(windows)
    selection_windows = windows.loc[windows["partition"] == "selection", ["window", "start", "end"]]
    validation_windows = windows.loc[windows["partition"] == "validation", ["window", "start", "end"]]
    holdout_windows = windows.loc[windows["partition"] == "holdout", ["window", "start", "end"]]

    coarse = _candidate_grid(config, has_fx=fx_daily is not None)
    coarse_metrics = _sort_metrics(
        _evaluate_set(asset, fx_rates, coarse, config, selection_windows, "selection"),
        "selection_robust_score",
    )
    coarse_seeds = [
        _candidate_from_row(row)
        for row in coarse_metrics.head(config.top_coarse).itertuples(index=False)
    ]

    refined = coarse | _refine_candidates(coarse_seeds, config)
    selection_metrics = _sort_metrics(
        _evaluate_set(asset, fx_rates, refined, config, selection_windows, "selection"),
        "selection_robust_score",
    )
    finalist_selection = selection_metrics.head(config.top_finalists).copy()
    finalists = {
        _candidate_from_row(row)
        for row in finalist_selection.itertuples(index=False)
    }

    validation_candidates = set(finalists) | _refine_candidates(
        list(finalists),
        config,
        month_radius=1,
        day_radius=1,
    )
    validation_metrics = _evaluate_set(
        asset,
        fx_rates,
        validation_candidates,
        config,
        validation_windows,
        "validation",
    )
    finalist_validation = finalist_selection.merge(
        validation_metrics,
        on=[
            "candidate_key",
            "candidate_label",
            "deployment_months",
            "buy_day",
            "pricing",
            "fx_method",
        ],
        how="inner",
        validate="one_to_one",
    )
    if finalist_validation.empty:
        raise ValueError("none of the selection finalists remained valid on validation windows")

    locked = _choose_locked_candidate(finalist_validation, validation_metrics)
    winner_row = locked.iloc[0]
    winner = StrategyCandidate(
        int(winner_row["deployment_months"]),
        int(winner_row["buy_day"]),
        str(winner_row["pricing"]),
        str(winner_row["fx_method"]),
    )

    holdout_metrics = _evaluate_set(
        asset,
        fx_rates,
        {winner},
        config,
        holdout_windows,
        "holdout",
    )
    holdout_row = holdout_metrics.iloc[0]
    winner_results = _run_candidate(asset, fx_rates, winner, config, holdout_windows)

    selection = {
        str(key).removeprefix("selection_"): value
        for key, value in winner_row.items()
        if str(key).startswith("selection_")
    }
    validation = {
        str(key).removeprefix("validation_"): value
        for key, value in winner_row.items()
        if str(key).startswith("validation_")
    }
    holdout = {
        str(key).removeprefix("holdout_"): value
        for key, value in holdout_row.items()
        if str(key).startswith("holdout_")
    }

    stability_gap = abs(float(winner_row["stability_gap"]))
    if stability_gap <= 0.01 and int(winner_row["neighbor_count"]) >= 3:
        stability_label = "High"
    elif stability_gap <= 0.03:
        stability_label = "Moderate"
    else:
        stability_label = "Low"

    overfit_warning: str | None = None
    validation_delta = float(validation["median_delta_vs_immediate"])
    holdout_delta = float(holdout["median_delta_vs_immediate"])
    if holdout_delta < validation_delta - 0.05:
        overfit_warning = (
            "The locked strategy weakened materially on the newest holdout starts. "
            "Treat the recommendation as low-confidence rather than retuning to the holdout."
        )
    elif float(holdout["p10_return"]) < float(validation["p10_return"]) - 0.10:
        overfit_warning = (
            "Downside performance weakened materially on the newest holdout starts. "
            "The app has not retuned the strategy to those results."
        )

    locked = locked.copy()
    locked["is_recommended"] = locked["candidate_key"] == winner.key
    return AutoSearchResult(
        winner=winner,
        selection=selection,
        validation=validation,
        holdout=holdout,
        search_table=locked,
        holdout_table=winner_results,
        windows=windows,
        candidate_count=len(refined),
        step_months=used_step,
        stability_label=stability_label,
        overfit_warning=overfit_warning,
    )
