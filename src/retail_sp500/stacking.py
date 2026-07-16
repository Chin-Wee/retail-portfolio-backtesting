from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .engine import _drawdown, _period_metrics, _returns_to_wealth, return_metrics
from .models import ComparisonResult, LabConfig, StackResult

def _combine_curves(comparison: ComparisonResult, weights: Mapping[str, float]) -> pd.DataFrame:
    if not weights:
        raise ValueError("at least one strategy weight is required")
    total = float(sum(weights.values()))
    if total <= 0.0:
        raise ValueError("strategy weights must sum to a positive value")
    normalized = {key: float(weight) / total for key, weight in weights.items() if weight > 0.0}
    unknown = sorted(set(normalized).difference(comparison.runs))
    if unknown:
        raise KeyError(f"unknown strategy keys: {', '.join(unknown)}")

    values = []
    common_index: pd.DatetimeIndex | None = None
    contribution: pd.Series | None = None
    for key, weight in normalized.items():
        curve = comparison.runs[key].curve
        common_index = curve.index if common_index is None else common_index.intersection(curve.index)
        values.append((weight, curve["portfolio_value"]))
        if contribution is None:
            contribution = curve["contribution"]
    assert common_index is not None and contribution is not None

    portfolio_value = pd.Series(0.0, index=common_index)
    for weight, value in values:
        portfolio_value = portfolio_value.add(weight * value.reindex(common_index), fill_value=0.0)
    contribution = contribution.reindex(common_index).fillna(0.0)
    capital = portfolio_value.shift(1).fillna(0.0) + contribution
    daily_return = portfolio_value / capital - 1.0
    wealth = _returns_to_wealth(daily_return)
    return pd.DataFrame(
        {
            "portfolio_value": portfolio_value,
            "contribution": contribution,
            "daily_return": daily_return,
            "wealth_index": wealth,
            "drawdown": _drawdown(wealth),
        },
        index=common_index,
    )


def build_stack(
    comparison: ComparisonResult,
    *,
    config: LabConfig = LabConfig(),
    approved_strategies: Sequence[str] | None = None,
) -> StackResult:
    """Greedily add strategies only when they improve pre-holdout Calmar.

    The final holdout period is never used for strategy or weight selection.
    """

    candidates = [key for key in comparison.runs if key != "immediate"]
    if approved_strategies is not None:
        approved = set(approved_strategies)
        candidates = [key for key in candidates if key in approved]
    else:
        worth = set(comparison.metrics.loc[comparison.metrics["worth_testing"], "key"])
        candidates = [key for key in candidates if key in worth]

    baseline_selection = _period_metrics(
        comparison.runs["immediate"].curve,
        None,
        comparison.holdout_start,
    )
    weights: dict[str, float] = {"immediate": 1.0}
    current_curve = _combine_curves(comparison, weights)
    current_metrics = _period_metrics(current_curve, None, comparison.holdout_start)
    steps: list[dict[str, object]] = []

    while candidates and len(weights) < config.stack_max_components:
        best: tuple[float, str, float, dict[str, float], pd.DataFrame] | None = None
        for key in candidates:
            for alpha in np.arange(0.1, 0.61, 0.1):
                trial = {name: weight * (1.0 - float(alpha)) for name, weight in weights.items()}
                trial[key] = trial.get(key, 0.0) + float(alpha)
                curve = _combine_curves(comparison, trial)
                metrics = _period_metrics(curve, None, comparison.holdout_start)
                if metrics["annualized_return"] < (
                    baseline_selection["annualized_return"] + config.stack_return_floor_delta
                ):
                    continue
                improvement = float(metrics["calmar_ratio"] - current_metrics["calmar_ratio"])
                if best is None or improvement > best[0]:
                    best = (improvement, key, float(alpha), trial, curve)

        if best is None or best[0] < config.stack_min_calmar_improvement:
            break
        improvement, key, alpha, weights, current_curve = best
        current_metrics = _period_metrics(current_curve, None, comparison.holdout_start)
        steps.append(
            {
                "step": len(steps) + 1,
                "added_key": key,
                "added_strategy": comparison.specs[key].label,
                "added_weight": alpha,
                "selection_calmar_improvement": improvement,
                "selection_calmar_ratio": current_metrics["calmar_ratio"],
                "selection_annualized_return": current_metrics["annualized_return"],
            }
        )
        candidates.remove(key)

    weights_series = pd.Series(weights, dtype=float).sort_values(ascending=False)
    full = return_metrics(current_curve["daily_return"])
    selection = _period_metrics(current_curve, None, comparison.holdout_start)
    holdout = _period_metrics(current_curve, comparison.holdout_start, None)
    metrics: dict[str, float | int] = {
        **full,
        **{f"selection_{key}": value for key, value in selection.items()},
        **{f"holdout_{key}": value for key, value in holdout.items()},
        "ending_value": float(current_curve["portfolio_value"].iloc[-1]),
        "components": int(len(weights_series)),
    }
    return StackResult(
        weights=weights_series,
        curve=current_curve,
        metrics=metrics,
        selection_steps=pd.DataFrame.from_records(steps),
    )


def comparison_figures(
    comparison: ComparisonResult,
    stack: StackResult | None = None,
    *,
    top_n: int = 8,
) -> dict[str, go.Figure]:
    metrics = comparison.metrics.copy()
    calmar = metrics.melt(
        id_vars=["strategy", "key"],
        value_vars=["selection_calmar_ratio", "holdout_calmar_ratio"],
        var_name="period",
        value_name="period_calmar",
    )
    calmar["period"] = calmar["period"].map(
        {
            "selection_calmar_ratio": "Selection",
            "holdout_calmar_ratio": "Holdout",
        }
    )
    metrics["holdout_drawdown_magnitude"] = metrics["holdout_max_drawdown"].abs()
    figures: dict[str, go.Figure] = {
        "selection_calmar": px.bar(
            metrics.sort_values("selection_calmar_ratio"),
            x="selection_calmar_ratio",
            y="strategy",
            color="family",
            orientation="h",
            title="Selection-period Calmar ratio",
            labels={
                "strategy": "Strategy",
                "selection_calmar_ratio": "Calmar ratio",
                "family": "Strategy family",
            },
        ),
        "selection_return_drawdown": px.scatter(
            metrics.assign(selection_drawdown_magnitude=metrics["selection_max_drawdown"].abs()),
            x="selection_drawdown_magnitude",
            y="selection_annualized_return",
            text="strategy",
            color="family",
            hover_data={"selection_calmar_ratio": ":.3f", "forced_fill_rate": ":.1%"},
            title="Selection-period return versus drawdown",
            labels={
                "selection_drawdown_magnitude": "Maximum drawdown magnitude",
                "selection_annualized_return": "Annualized return",
                "family": "Strategy family",
            },
        ),
        "calmar": px.bar(
            calmar.sort_values("period_calmar"),
            x="period_calmar",
            y="strategy",
            color="period",
            barmode="group",
            orientation="h",
            title="Strategy Calmar ratio: selection versus untouched holdout",
            labels={"strategy": "Strategy", "period_calmar": "Calmar ratio", "period": "Period"},
        ),
        "return_drawdown": px.scatter(
            metrics,
            x="holdout_drawdown_magnitude",
            y="holdout_annualized_return",
            text="strategy",
            color="family",
            hover_data={"holdout_calmar_ratio": ":.3f", "forced_fill_rate": ":.1%"},
            title="Holdout annualized return versus maximum drawdown",
            labels={
                "holdout_drawdown_magnitude": "Maximum drawdown magnitude",
                "holdout_annualized_return": "Annualized return",
                "family": "Strategy family",
            },
        ),
        "fill": px.scatter(
            metrics.loc[metrics["key"] != "immediate"],
            x="natural_fill_rate",
            y="weighted_execution_savings",
            color="family",
            hover_name="strategy",
            size="average_wait_sessions",
            title="Fill reliability versus achieved execution savings",
            labels={
                "natural_fill_rate": "Natural fill rate",
                "weighted_execution_savings": "Execution savings versus immediate",
                "family": "Strategy family",
            },
        ),
    }
    figures["selection_return_drawdown"].update_xaxes(tickformat=".1%")
    figures["selection_return_drawdown"].update_yaxes(tickformat=".1%")
    figures["return_drawdown"].update_xaxes(tickformat=".1%")
    figures["return_drawdown"].update_yaxes(tickformat=".1%")
    figures["fill"].update_xaxes(tickformat=".1%")
    figures["fill"].update_yaxes(tickformat=".2%")

    top_keys = (
        metrics.sort_values("selection_calmar_ratio", ascending=False)
        .head(top_n)["key"]
        .tolist()
    )
    if "immediate" not in top_keys:
        top_keys.append("immediate")
    curve_frames = []
    for key in top_keys:
        curve = comparison.runs[key].curve[["wealth_index", "drawdown"]].copy()
        curve["strategy"] = comparison.specs[key].label
        curve_frames.append(curve.reset_index())
    if stack is not None:
        stacked = stack.curve[["wealth_index", "drawdown"]].copy()
        stacked["strategy"] = "Selected stack"
        curve_frames.append(stacked.reset_index())
    curves = pd.concat(curve_frames, ignore_index=True)
    figures["wealth"] = px.line(
        curves,
        x="date",
        y="wealth_index",
        color="strategy",
        title="Contribution-neutral wealth paths",
        labels={"date": "Date", "wealth_index": "Growth of one unit", "strategy": "Strategy"},
    )
    figures["drawdown"] = px.line(
        curves,
        x="date",
        y="drawdown",
        color="strategy",
        title="Drawdown paths",
        labels={"date": "Date", "drawdown": "Drawdown", "strategy": "Strategy"},
    )
    figures["drawdown"].update_yaxes(tickformat=".1%")
    if stack is not None:
        weights = stack.weights.rename("weight").reset_index().rename(columns={"index": "key"})
        weights["strategy"] = weights["key"].map(
            {key: comparison.specs[key].label for key in comparison.specs}
        )
        figures["stack_weights"] = px.bar(
            weights.sort_values("weight"),
            x="weight",
            y="strategy",
            orientation="h",
            title="Selected strategy stack",
            labels={"weight": "Portfolio weight", "strategy": "Strategy"},
        )
        figures["stack_weights"].update_xaxes(tickformat=".0%")
    return figures


def export_results(
    comparison: ComparisonResult,
    stack: StackResult,
    *,
    output_dir: str | Path = "results/portfolio",
) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    comparison.metrics.to_csv(output / "strategy_metrics.csv", index=False)
    comparison.curves.to_csv(output / "strategy_curves.csv", index=False)
    stack.weights.rename("weight").to_csv(output / "stack_weights.csv", header=True)
    stack.curve.reset_index().to_csv(output / "stack_curve.csv", index=False)
    stack.selection_steps.to_csv(output / "stack_selection_steps.csv", index=False)
    (output / "stack_metrics.json").write_text(
        json.dumps(stack.metrics, indent=2, default=float),
        encoding="utf-8",
    )
    for name, figure in comparison_figures(comparison, stack).items():
        figure.write_html(output / f"{name}.html", include_plotlyjs="cdn")
    return output
