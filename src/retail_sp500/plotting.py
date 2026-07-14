from __future__ import annotations

from collections.abc import Mapping, Sequence

import plotly.graph_objects as go

from .backtest import BacktestResult


def comparison_figure(
    results: Mapping[str, BacktestResult],
    selected: Sequence[str] | None = None,
    log_scale: bool = False,
    show_contributions: bool = True,
) -> go.Figure:
    names = list(selected) if selected is not None else list(results)
    unknown = sorted(set(names).difference(results))
    if unknown:
        raise KeyError(f"unknown strategies: {', '.join(unknown)}")

    figure = go.Figure()
    for name in names:
        history = results[name].history
        figure.add_trace(
            go.Scatter(
                x=history.index,
                y=history["portfolio_value"],
                mode="lines",
                name=name,
                hovertemplate="%{x|%Y-%m}<br>$%{y:,.0f}<extra>%{fullData.name}</extra>",
            )
        )

    if show_contributions and names:
        contributions = results[names[0]].history["cumulative_contributions"]
        figure.add_trace(
            go.Scatter(
                x=contributions.index,
                y=contributions,
                mode="lines",
                name="Capital contributed",
                line={"dash": "dash"},
                hovertemplate="%{x|%Y-%m}<br>$%{y:,.0f}<extra>Capital contributed</extra>",
            )
        )

    figure.update_layout(
        title="Portfolio value by strategy",
        xaxis_title="Month",
        yaxis_title="Portfolio value (USD)",
        hovermode="x unified",
        legend_title="Strategy",
    )
    figure.update_yaxes(type="log" if log_scale else "linear", tickprefix="$")
    return figure
