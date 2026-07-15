from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def _require(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in frame]
    if missing:
        raise KeyError(f"plot data is missing: {', '.join(missing)}")


def calmar_by_discount_figure(grid: pd.DataFrame) -> go.Figure:
    _require(grid, ("discount", "calmar_ratio", "baseline_calmar_ratio"))
    plotted = grid.copy()
    horizon_column = (
        "wait_horizon"
        if "wait_horizon" in plotted
        else "max_wait_sessions"
        if "max_wait_sessions" in plotted
        else None
    )
    if horizon_column is not None and plotted[horizon_column].nunique() > 1:
        figure = px.line(
            plotted,
            x="discount",
            y="calmar_ratio",
            color=horizon_column,
            markers=True,
            title="Calmar ratio by limit distance and expiry horizon",
            labels={
                "discount": "Limit below preceding close",
                "calmar_ratio": "Calmar ratio",
                horizon_column: "Maximum wait sessions",
            },
        )
        baseline = plotted[["discount", "baseline_calmar_ratio"]].drop_duplicates("discount")
        figure.add_trace(
            go.Scatter(
                x=baseline["discount"],
                y=baseline["baseline_calmar_ratio"],
                mode="lines",
                name="Immediate open",
                line={"dash": "dash"},
                hovertemplate="Discount %{x:.2%}<br>Calmar %{y:.3f}<extra></extra>",
            )
        )
    else:
        figure = go.Figure()
        figure.add_trace(
            go.Scatter(
                x=plotted["discount"],
                y=plotted["calmar_ratio"],
                mode="lines+markers",
                name="Limit strategy",
                hovertemplate="Discount %{x:.2%}<br>Calmar %{y:.3f}<extra></extra>",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=plotted["discount"],
                y=plotted["baseline_calmar_ratio"],
                mode="lines",
                name="Immediate open",
                line={"dash": "dash"},
                hovertemplate="Discount %{x:.2%}<br>Calmar %{y:.3f}<extra></extra>",
            )
        )
        figure.update_layout(title="Calmar ratio by limit distance")
    figure.update_layout(
        xaxis_title="Limit below preceding close",
        yaxis_title="Calmar ratio",
        hovermode="x unified",
    )
    figure.update_xaxes(tickformat=".1%")
    return figure


def return_drawdown_figure(grid: pd.DataFrame) -> go.Figure:
    _require(grid, ("discount", "annualized_return", "max_drawdown", "calmar_ratio"))
    plotted = grid.copy()
    plotted["drawdown_magnitude"] = -plotted["max_drawdown"]
    horizon_column = (
        "wait_horizon"
        if "wait_horizon" in plotted
        else "max_wait_sessions"
        if "max_wait_sessions" in plotted and plotted["max_wait_sessions"].nunique() > 1
        else None
    )
    labels = {
        "drawdown_magnitude": "Maximum drawdown magnitude",
        "annualized_return": "Annualized compounded return",
    }
    color_column = horizon_column
    if horizon_column is not None:
        color_column = "wait_horizon_label"
        plotted[color_column] = plotted[horizon_column].astype(str)
        labels[color_column] = "Maximum wait sessions"
    figure = px.scatter(
        plotted,
        x="drawdown_magnitude",
        y="annualized_return",
        color=color_column,
        hover_data={"discount": ":.2%", "calmar_ratio": ":.3f"},
        title="Annualized return versus maximum drawdown",
        labels=labels,
    )
    figure.update_xaxes(tickformat=".1%")
    figure.update_yaxes(tickformat=".1%")
    return figure


def wealth_index_figure(curve: pd.DataFrame) -> go.Figure:
    _require(curve, ("wealth_index", "baseline_wealth_index"))
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=curve.index, y=curve["wealth_index"], mode="lines", name="Limit strategy"))
    figure.add_trace(
        go.Scatter(x=curve.index, y=curve["baseline_wealth_index"], mode="lines", name="Immediate open")
    )
    figure.update_layout(
        title="Contribution-neutral wealth index",
        xaxis_title="Date",
        yaxis_title="Growth of one unit",
        hovermode="x unified",
    )
    return figure


def drawdown_figure(curve: pd.DataFrame) -> go.Figure:
    _require(curve, ("drawdown", "baseline_drawdown"))
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=curve.index, y=curve["drawdown"], mode="lines", name="Limit strategy"))
    figure.add_trace(
        go.Scatter(x=curve.index, y=curve["baseline_drawdown"], mode="lines", name="Immediate open")
    )
    figure.update_layout(
        title="Drawdown from running peak",
        xaxis_title="Date",
        yaxis_title="Drawdown",
        hovermode="x unified",
    )
    figure.update_yaxes(tickformat=".1%")
    return figure


def strategy_calmar_ranking_figure(metrics: pd.DataFrame) -> go.Figure:
    _require(metrics, ("strategy", "calmar_ratio"))
    plotted = metrics.dropna(subset=["calmar_ratio"]).sort_values("calmar_ratio")
    return px.bar(
        plotted,
        x="calmar_ratio",
        y="strategy",
        orientation="h",
        title="Investment strategies ranked by Calmar ratio",
        labels={"strategy": "Strategy", "calmar_ratio": "Calmar ratio"},
        hover_data={
            column: format_spec
            for column, format_spec in {
                "annualized_return": ":.2%",
                "max_drawdown": ":.2%",
                "ending_excess_value": ":,.0f",
            }.items()
            if column in plotted
        },
    )


def strategy_return_drawdown_figure(metrics: pd.DataFrame) -> go.Figure:
    _require(metrics, ("strategy", "annualized_return", "max_drawdown", "calmar_ratio"))
    plotted = metrics.dropna(subset=["annualized_return", "max_drawdown"]).copy()
    plotted["drawdown_magnitude"] = -plotted["max_drawdown"]
    figure = px.scatter(
        plotted,
        x="drawdown_magnitude",
        y="annualized_return",
        text="strategy",
        hover_name="strategy",
        hover_data={"calmar_ratio": ":.3f"},
        title="Investment strategy return versus drawdown",
        labels={
            "drawdown_magnitude": "Maximum drawdown magnitude",
            "annualized_return": "Annualized compounded return",
        },
    )
    figure.update_traces(textposition="top center")
    figure.update_xaxes(tickformat=".1%")
    figure.update_yaxes(tickformat=".1%")
    return figure


def strategy_wealth_figure(curves: pd.DataFrame) -> go.Figure:
    _require(curves, ("date", "strategy", "wealth_index"))
    figure = px.line(
        curves,
        x="date",
        y="wealth_index",
        color="strategy",
        title="Contribution-neutral wealth by investment strategy",
        labels={"date": "Date", "wealth_index": "Growth of one unit", "strategy": "Strategy"},
    )
    figure.update_layout(hovermode="x unified")
    return figure


def strategy_drawdown_figure(curves: pd.DataFrame) -> go.Figure:
    _require(curves, ("date", "strategy", "drawdown"))
    figure = px.line(
        curves,
        x="date",
        y="drawdown",
        color="strategy",
        title="Drawdown by investment strategy",
        labels={"date": "Date", "drawdown": "Drawdown", "strategy": "Strategy"},
    )
    figure.update_yaxes(tickformat=".1%")
    figure.update_layout(hovermode="x unified")
    return figure


def walk_forward_discount_figure(walk_forward: pd.DataFrame) -> go.Figure:
    _require(walk_forward, ("test_start", "selected_discount"))
    color = "selection_metric" if "selection_metric" in walk_forward and walk_forward["selection_metric"].nunique() > 1 else None
    figure = px.line(
        walk_forward,
        x="test_start",
        y="selected_discount",
        color=color,
        markers=True,
        title="Walk-forward selected limit distance",
        labels={"test_start": "Test period", "selected_discount": "Selected discount"},
    )
    figure.update_yaxes(tickformat=".1%")
    return figure


def walk_forward_calmar_figure(walk_forward: pd.DataFrame) -> go.Figure:
    _require(walk_forward, ("test_start", "test_calmar_ratio", "test_baseline_calmar_ratio"))
    figure = go.Figure()
    if "selection_metric" in walk_forward and walk_forward["selection_metric"].nunique() > 1:
        for metric, subset in walk_forward.groupby("selection_metric", sort=False):
            figure.add_trace(
                go.Scatter(
                    x=subset["test_start"],
                    y=subset["test_calmar_ratio"],
                    mode="lines+markers",
                    name=f"Selected by {metric}",
                )
            )
        baseline = walk_forward.drop_duplicates("test_start")
    else:
        figure.add_trace(
            go.Scatter(
                x=walk_forward["test_start"],
                y=walk_forward["test_calmar_ratio"],
                mode="lines+markers",
                name="Selected limit strategy",
            )
        )
        baseline = walk_forward
    figure.add_trace(
        go.Scatter(
            x=baseline["test_start"],
            y=baseline["test_baseline_calmar_ratio"],
            mode="lines+markers",
            name="Immediate open",
            line={"dash": "dash"},
        )
    )
    figure.update_layout(
        title="Out-of-sample Calmar ratio by test period",
        xaxis_title="Test period",
        yaxis_title="Calmar ratio",
        hovermode="x unified",
    )
    return figure
