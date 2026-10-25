"""Risk vector calculations for aligned weekly simple returns."""

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd


ANCHORS = {
    "gold": "gold",
    "us_equity": "us_equity",
    "japan_equity": "japan_equity",
    "us_treasury": "us_treasury",
    "japan_bond": "japan_bond",
}
METRICS = ("sigma", "ES", *(f"beta_{name}" for name in ANCHORS))
SIGMA_WINDOW = 52
ES_WINDOW = 156
BETA_WINDOW = 52
NORMALIZATION_WINDOW = 52
ES_TAIL_COUNT = 8
ANNUALIZATION_WEEKS = 52


def _record(value: float | None, status: str, normalized: float | None = None,
            normalization_status: str | None = None) -> dict[str, Any]:
    return {
        "value": value,
        "status": status,
        "normalized": normalized,
        "normalization_status": normalization_status or status,
        "window_weeks": None,
        "observation_count": 0,
    }


def _window_for(metric: str) -> int:
    if metric == "sigma":
        return SIGMA_WINDOW
    if metric == "ES":
        return ES_WINDOW
    return BETA_WINDOW


def _empty_vector(status: str) -> dict[str, Any]:
    result = {}
    for name in METRICS:
        item = _record(None, status, normalization_status=status)
        item["window_weeks"] = _window_for(name)
        result[name] = item
    return result


def _observation_count(frame: pd.DataFrame, metric: str, end: int) -> int:
    """Count finite observations in the latest nominal estimation window."""
    start = max(0, end - _window_for(metric) + 1)
    window = frame.iloc[start : end + 1]
    if metric.startswith("beta_"):
        anchor_name = metric.removeprefix("beta_")
        if anchor_name not in window.columns:
            return 0
        values = window[["asset", anchor_name]].to_numpy(dtype=float)
        return int(np.isfinite(values).all(axis=1).sum())
    return int(np.isfinite(window["asset"].to_numpy(dtype=float)).sum())


def _invalid_numeric_status(values: np.ndarray) -> str | None:
    if np.isinf(values).any():
        return "invalid_price"
    if np.isnan(values).any():
        return "missing_price"
    return None


def _window_status(window: pd.DataFrame, columns: list[str]) -> str:
    """Return a specific source status for a window containing missing values."""
    candidates: list[str] = []
    for column in columns:
        status_column = f"{column}_status"
        values = window[column].to_numpy(dtype=float)
        if status_column in window:
            statuses = window[status_column].astype(str).to_numpy()
            candidates.extend(statuses[~np.isfinite(values)].tolist())
        else:
            statuses = np.full(len(values), "ok", dtype=object)
        if np.isinf(values).any():
            candidates.append("invalid_price")
        if np.isnan(values).any() and not np.isin(
            statuses[~np.isfinite(values)], ["missing_fx", "invalid_price", "configuration_error"]
        ).any():
            candidates.append("missing_price")
    for status in ("missing_fx", "invalid_price", "missing_price", "configuration_error"):
        if status in candidates:
            return status
    return "missing_price"


def _metric_at(frame: pd.DataFrame, metric: str, end: int) -> tuple[float | None, str]:
    """Calculate one metric at row ``end`` using a trailing inclusive window."""
    if metric == "sigma":
        window_size = SIGMA_WINDOW
    elif metric == "ES":
        window_size = ES_WINDOW
    else:
        window_size = BETA_WINDOW

    start = end - window_size + 1
    if start < 0:
        return None, "insufficient_history"

    window = frame.iloc[start : end + 1]
    if metric == "sigma" or metric == "ES":
        values = window["asset"].to_numpy(dtype=float)
        invalid_status = _invalid_numeric_status(values)
        if invalid_status:
            return None, _window_status(window, ["asset"])

        if metric == "sigma":
            value = float(np.std(values, ddof=1) * np.sqrt(ANNUALIZATION_WEEKS))
            return (value, "ok") if np.isfinite(value) else (None, "calculation_error")

        losses = -values
        value = float(np.sort(losses)[-ES_TAIL_COUNT:].mean())
        return (value, "ok") if np.isfinite(value) else (None, "calculation_error")

    anchor_name = metric.removeprefix("beta_")
    if anchor_name not in frame.columns:
        return None, "configuration_error"

    paired = window[["asset", anchor_name]].to_numpy(dtype=float)
    invalid_status = _invalid_numeric_status(paired)
    if invalid_status:
        return None, _window_status(window, ["asset", anchor_name])

    asset_values = paired[:, 0]
    anchor_values = paired[:, 1]
    variance = float(np.var(anchor_values, ddof=1))
    if not np.isfinite(variance):
        return None, "calculation_error"
    if variance <= np.finfo(float).eps:
        return None, "zero_variance"

    covariance = float(np.cov(asset_values, anchor_values, ddof=1)[0, 1])
    value = covariance / variance
    return (float(value), "ok") if np.isfinite(value) else (None, "calculation_error")


def _threshold_for(metric: str, thresholds: Mapping[str, float] | None) -> float | None:
    if not isinstance(thresholds, Mapping) or metric not in thresholds:
        return None
    try:
        threshold = float(thresholds[metric])
    except (TypeError, ValueError):
        return None
    if not np.isfinite(threshold) or threshold < 0:
        return None
    return threshold


def _normalize_metric(
    frame: pd.DataFrame,
    metric: str,
    current_value: float | None,
    current_status: str,
    threshold: float | None,
    current_position: int | None = None,
    prior_metric_values: list[tuple[float | None, str]] | None = None,
) -> tuple[float | None, str]:
    if threshold is None:
        return None, "configuration_error"
    if current_status != "ok" or current_value is None:
        return None, current_status

    history_values = []
    if current_position is None:
        current_position = len(frame) - 1
    if prior_metric_values is None:
        prior_metric_values = [
            _metric_at(frame, metric, position)
            for position in range(current_position)
        ]
    for value, status in reversed(prior_metric_values):
        if status == "ok" and value is not None and np.isfinite(value):
            history_values.append(value)
            if len(history_values) == NORMALIZATION_WINDOW:
                break
    if len(history_values) < NORMALIZATION_WINDOW:
        return None, "insufficient_history"

    values = np.asarray(history_values, dtype=float)
    median = float(np.median(values))
    q25, q75 = np.quantile(values, [0.25, 0.75], method="linear")
    iqr = float(q75 - q25)
    if iqr <= threshold:
        return None, "iqr_below_threshold"

    normalized = float((current_value - median) / iqr)
    return (normalized, "ok") if np.isfinite(normalized) else (None, "calculation_error")


def _prepare_frame(
    asset_returns: pd.Series,
    anchor_returns: pd.DataFrame,
    asset_statuses: pd.Series | None,
    anchor_statuses: pd.DataFrame | None,
) -> tuple[pd.DataFrame | None, str | None]:
    if (
        not isinstance(asset_returns, pd.Series)
        or not isinstance(asset_returns.index, pd.DatetimeIndex)
        or asset_returns.index.has_duplicates
    ):
        return None, "configuration_error"
    asset = pd.to_numeric(asset_returns, errors="coerce").astype(float).sort_index()
    if asset.empty:
        return pd.DataFrame(index=asset.index, columns=["asset"], dtype=float), None
    anchors_are_valid = (
        isinstance(anchor_returns, pd.DataFrame)
        and isinstance(anchor_returns.index, pd.DatetimeIndex)
        and not anchor_returns.index.has_duplicates
        and not anchor_returns.columns.has_duplicates
        and anchor_returns.index.tz == asset.index.tz
    )
    if anchors_are_valid:
        available_anchors = [
            name for name in ANCHORS.values() if name in anchor_returns.columns
        ]
        anchors = anchor_returns[available_anchors].copy()
        for column in anchors.columns:
            anchors[column] = pd.to_numeric(anchors[column], errors="coerce").astype(float)
        anchors = anchors.sort_index().reindex(asset.index)
    else:
        # Keep asset-only metrics available when anchor input is malformed.
        anchors = pd.DataFrame(index=asset.index)

    frame = pd.concat([asset.rename("asset"), anchors], axis=1)
    if isinstance(asset_statuses, pd.Series):
        frame["asset_status"] = asset_statuses.reindex(asset.index).fillna("missing_price").astype(str)
    if isinstance(anchor_statuses, pd.DataFrame):
        for column in anchors.columns:
            if column in anchor_statuses:
                frame[f"{column}_status"] = (
                    anchor_statuses[column].reindex(asset.index).fillna("missing_price").astype(str)
                )
    return frame, None


def _vector_at(
    frame: pd.DataFrame,
    position: int,
    iqr_thresholds: Mapping[str, float] | None,
    metric_cache: dict[str, list[tuple[float | None, str]]] | None = None,
) -> dict[str, Any]:
    as_of = frame.index[position].isoformat()
    result: dict[str, Any] = {"as_of": as_of}
    for metric in METRICS:
        if metric_cache is None:
            value, status = _metric_at(frame, metric, position)
            prior_metric_values = None
        else:
            value, status = metric_cache[metric][position]
            prior_metric_values = metric_cache[metric][:position]
        threshold = _threshold_for(metric, iqr_thresholds)
        normalized, normalization_status = _normalize_metric(
            frame,
            metric,
            value,
            status,
            threshold,
            current_position=position,
            prior_metric_values=prior_metric_values,
        )
        item = _record(value, status, normalized, normalization_status)
        item["window_weeks"] = _window_for(metric)
        item["observation_count"] = _observation_count(frame, metric, position)
        result[metric] = item
    return result


def calculate_risk_vector(
    asset_returns: pd.Series,
    anchor_returns: pd.DataFrame,
    iqr_thresholds: Mapping[str, float] | None = None,
    asset_statuses: pd.Series | None = None,
    anchor_statuses: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Calculate the latest 7D vector from aligned weekly simple returns."""
    frame, error = _prepare_frame(
        asset_returns, anchor_returns, asset_statuses, anchor_statuses
    )
    if error:
        return {"as_of": None, **_empty_vector(error)}
    if frame.empty:
        return {"as_of": None, **_empty_vector("insufficient_history")}
    return _vector_at(frame, len(frame) - 1, iqr_thresholds)


def calculate_risk_vector_history(
    asset_returns: pd.Series,
    anchor_returns: pd.DataFrame,
    iqr_thresholds: Mapping[str, float] | None = None,
    asset_statuses: pd.Series | None = None,
    anchor_statuses: pd.DataFrame | None = None,
    history_weeks: int = 52,
) -> list[dict[str, Any]]:
    """Return one vector per final weekly row, preserving gaps and statuses."""
    if not isinstance(history_weeks, int) or history_weeks <= 0:
        raise ValueError("history_weeks_must_be_positive")
    frame, error = _prepare_frame(
        asset_returns, anchor_returns, asset_statuses, anchor_statuses
    )
    if error or frame is None or frame.empty:
        return []
    metric_cache = {
        metric: [_metric_at(frame, metric, position) for position in range(len(frame))]
        for metric in METRICS
    }
    start = max(0, len(frame) - history_weeks)
    return [
        _vector_at(frame, position, iqr_thresholds, metric_cache)
        for position in range(start, len(frame))
    ]
