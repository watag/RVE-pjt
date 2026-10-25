"""Portfolio weekly return aggregation using beginning-of-week weights."""

import numpy as np
import pandas as pd

from risk_metrics import calculate_risk_vector


WEIGHT_SUM_TOLERANCE = 1e-9


def _error_frame(index: pd.Index, status: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "portfolio_return": np.nan,
            "status": status,
        },
        index=index,
    )


def calculate_portfolio_returns(
    asset_returns: pd.DataFrame,
    beginning_weights: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate weekly asset returns with each week's opening weights.

    ``beginning_weights.loc[t]`` represents holdings at the start of the week
    whose return is ``asset_returns.loc[t]``. Inputs use a unique
    ``DatetimeIndex`` with one row per week. Missing held-asset returns invalidate
    that week; available weights are never renormalized.
    """
    if not isinstance(asset_returns, pd.DataFrame):
        return _error_frame(pd.Index([]), "configuration_error")
    output_index = asset_returns.index
    if (
        not isinstance(asset_returns.index, pd.DatetimeIndex)
        or asset_returns.index.has_duplicates
        or asset_returns.columns.has_duplicates
        or not asset_returns.columns.size
    ):
        return _error_frame(output_index, "configuration_error")
    if (
        not isinstance(beginning_weights, pd.DataFrame)
        or not isinstance(beginning_weights.index, pd.DatetimeIndex)
        or beginning_weights.index.has_duplicates
        or beginning_weights.columns.has_duplicates
        or beginning_weights.index.tz != asset_returns.index.tz
        or set(beginning_weights.columns) != set(asset_returns.columns)
    ):
        return _error_frame(output_index, "configuration_error")

    returns = asset_returns.apply(pd.to_numeric, errors="coerce").astype(float).sort_index()
    weights = beginning_weights.reindex(columns=returns.columns)
    weights = weights.apply(pd.to_numeric, errors="coerce").astype(float)
    weights = weights.reindex(returns.index)

    portfolio_values: list[float] = []
    statuses: list[str] = []
    for date, asset_row in returns.iterrows():
        weight_row = weights.loc[date]
        if not np.isfinite(weight_row.to_numpy(dtype=float)).all():
            portfolio_values.append(np.nan)
            statuses.append("configuration_error")
            continue

        total_weight = float(weight_row.sum())
        if not np.isclose(total_weight, 1.0, rtol=0.0, atol=WEIGHT_SUM_TOLERANCE):
            portfolio_values.append(np.nan)
            statuses.append("configuration_error")
            continue

        active_assets = weight_row != 0.0
        held_returns = asset_row[active_assets].to_numpy(dtype=float)
        if np.isinf(held_returns).any():
            portfolio_values.append(np.nan)
            statuses.append("invalid_price")
            continue
        if np.isnan(held_returns).any():
            portfolio_values.append(np.nan)
            statuses.append("missing_price")
            continue

        value = float(np.dot(weight_row[active_assets], asset_row[active_assets]))
        if not np.isfinite(value):
            portfolio_values.append(np.nan)
            statuses.append("calculation_error")
            continue
        portfolio_values.append(value)
        statuses.append("ok")

    return pd.DataFrame(
        {"portfolio_return": portfolio_values, "status": statuses},
        index=returns.index,
    )


def calculate_portfolio_risk_vector(
    asset_returns: pd.DataFrame,
    weights: pd.DataFrame | pd.Series,
    anchor_returns: pd.DataFrame,
    iqr_thresholds=None,
    mode: str = "realized",
) -> dict:
    """Calculate a portfolio vector from its own weekly return series.

    ``realized`` requires the actual beginning-of-week weights for every week.
    ``scenario`` requires one current-weight Series, which is applied to each
    historical week and explicitly labeled as a scenario result.
    """
    if mode == "scenario" and isinstance(weights, pd.Series):
        weights = pd.DataFrame(
            np.repeat(weights.to_numpy(dtype=float)[None, :], len(asset_returns), axis=0),
            index=asset_returns.index,
            columns=weights.index,
        )
    elif mode != "realized":
        return {"analysis_mode": mode, "status": "configuration_error"}
    elif not isinstance(weights, pd.DataFrame):
        return {"analysis_mode": mode, "status": "configuration_error"}

    portfolio = calculate_portfolio_returns(asset_returns, weights)
    vector = calculate_risk_vector(
        portfolio["portfolio_return"],
        anchor_returns,
        iqr_thresholds,
        asset_statuses=portfolio["status"],
    )
    vector["analysis_mode"] = mode
    vector["portfolio_status"] = (
        "ok" if (portfolio["status"] == "ok").all() else "partial_or_invalid_history"
    )
    return vector
