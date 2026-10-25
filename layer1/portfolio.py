"""Portfolio weekly return aggregation using beginning-of-week weights."""

import numpy as np
import pandas as pd

from risk_metrics import calculate_risk_vector


WEIGHT_SUM_TOLERANCE = 1e-9


def _error_frame(index: pd.Index, status: str, reason: str | None = None) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "portfolio_return": np.nan,
            "status": status,
            "reason": reason or status,
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
        return _error_frame(pd.Index([]), "configuration_error", "asset_returns_not_dataframe")
    output_index = asset_returns.index
    if not isinstance(asset_returns.index, pd.DatetimeIndex):
        return _error_frame(output_index, "configuration_error", "asset_return_index_not_datetime")
    if asset_returns.index.has_duplicates:
        return _error_frame(output_index, "configuration_error", "duplicate_asset_return_dates")
    if asset_returns.columns.has_duplicates:
        return _error_frame(output_index, "configuration_error", "duplicate_asset_symbols")
    if not asset_returns.columns.size:
        return _error_frame(output_index, "configuration_error", "no_asset_return_columns")
    if not isinstance(beginning_weights, pd.DataFrame):
        return _error_frame(output_index, "configuration_error", "weights_not_dataframe")
    if not isinstance(beginning_weights.index, pd.DatetimeIndex):
        return _error_frame(output_index, "configuration_error", "weight_index_not_datetime")
    if beginning_weights.index.has_duplicates:
        return _error_frame(output_index, "configuration_error", "duplicate_weight_dates")
    if beginning_weights.columns.has_duplicates:
        return _error_frame(output_index, "configuration_error", "duplicate_weight_symbols")
    if beginning_weights.index.tz != asset_returns.index.tz:
        return _error_frame(output_index, "configuration_error", "weight_timezone_mismatch")
    if set(beginning_weights.columns) != set(asset_returns.columns):
        return _error_frame(output_index, "configuration_error", "weight_symbols_mismatch")

    returns = asset_returns.apply(pd.to_numeric, errors="coerce").astype(float).sort_index()
    provided_weight_dates = set(beginning_weights.index)
    weights = beginning_weights.reindex(columns=returns.columns)
    weights = weights.apply(pd.to_numeric, errors="coerce").astype(float)
    weights = weights.reindex(returns.index)

    portfolio_values: list[float] = []
    statuses: list[str] = []
    reasons: list[str] = []
    for date, asset_row in returns.iterrows():
        if date not in provided_weight_dates:
            portfolio_values.append(np.nan)
            statuses.append("configuration_error")
            reasons.append("missing_weekly_weight_row")
            continue
        weight_row = weights.loc[date]
        if not np.isfinite(weight_row.to_numpy(dtype=float)).all():
            portfolio_values.append(np.nan)
            statuses.append("configuration_error")
            reasons.append("missing_or_non_numeric_weight_value")
            continue

        total_weight = float(weight_row.sum())
        if not np.isclose(total_weight, 1.0, rtol=0.0, atol=WEIGHT_SUM_TOLERANCE):
            portfolio_values.append(np.nan)
            statuses.append("configuration_error")
            reasons.append(f"weight_sum_not_one:{total_weight:.12g}")
            continue
        if (weight_row < 0.0).any():
            portfolio_values.append(np.nan)
            statuses.append("configuration_error")
            negative_symbols = list(weight_row.index[weight_row < 0.0])
            reasons.append("negative_weights_not_supported:" + ",".join(map(str, negative_symbols)))
            continue

        active_assets = weight_row != 0.0
        held_returns = asset_row[active_assets].to_numpy(dtype=float)
        if np.isinf(held_returns).any():
            portfolio_values.append(np.nan)
            statuses.append("invalid_price")
            reasons.append("non_finite_held_asset_return")
            continue
        if np.isnan(held_returns).any():
            portfolio_values.append(np.nan)
            statuses.append("missing_price")
            missing_assets = list(asset_row.index[active_assets & asset_row.isna()])
            reasons.append("missing_held_asset_return:" + ",".join(map(str, missing_assets)))
            continue

        value = float(np.dot(weight_row[active_assets], asset_row[active_assets]))
        if not np.isfinite(value):
            portfolio_values.append(np.nan)
            statuses.append("calculation_error")
            reasons.append("portfolio_return_non_finite")
            continue
        portfolio_values.append(value)
        statuses.append("ok")
        reasons.append("ok")

    return pd.DataFrame(
        {"portfolio_return": portfolio_values, "status": statuses, "reason": reasons},
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
        if not isinstance(asset_returns, pd.DataFrame):
            return {
                "analysis_mode": mode,
                "status": "configuration_error",
                "reason": "asset_returns_not_dataframe",
            }
        weights = pd.DataFrame(
            np.repeat(weights.to_numpy(dtype=float)[None, :], len(asset_returns), axis=0),
            index=asset_returns.index,
            columns=weights.index,
        )
    elif mode != "realized":
        return {
            "analysis_mode": mode,
            "status": "configuration_error",
            "reason": "unsupported_analysis_mode",
        }
    elif not isinstance(weights, pd.DataFrame):
        return {
            "analysis_mode": mode,
            "status": "configuration_error",
            "reason": "realized_mode_requires_weekly_weight_history",
        }

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
    issues = portfolio.loc[portfolio["status"] != "ok", ["status", "reason"]]
    vector["portfolio_diagnostics"] = {
        "valid_weeks": int((portfolio["status"] == "ok").sum()),
        "invalid_weeks": int(len(issues)),
        "issues": [
            {
                "week_ending": date.isoformat(),
                "status": row.status,
                "reason": row.reason,
            }
            for date, row in issues.iterrows()
        ],
    }
    return vector
