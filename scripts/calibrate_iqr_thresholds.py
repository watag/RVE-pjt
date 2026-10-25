"""Calibrate per-metric IQR floors from retained five-year price histories.

The calibration threshold is the configured percentile of strictly positive
IQRs from each instrument's preceding 52 valid metric observations. The current
metric observation must also be valid, but is excluded from its IQR window.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "layer1"))
sys.path.insert(0, str(REPOSITORY_ROOT / "fetch"))

from fetch_csv import price_history_filename  # noqa: E402
from fx import convert_usd_prices_to_jpy  # noqa: E402
from risk_metrics import ANCHORS, BETA_WINDOW, ES_TAIL_COUNT, ES_WINDOW, METRICS, SIGMA_WINDOW  # noqa: E402
from weekly import build_weekly_returns  # noqa: E402

NORMALIZATION_WINDOW = 52
CALIBRATION_QUANTILE = 0.05


def positive_historical_iqrs(
    metric_values: pd.Series | np.ndarray,
    window: int = NORMALIZATION_WINDOW,
) -> list[float]:
    """Return positive IQRs from valid prior windows, excluding current value."""
    values = np.asarray(metric_values, dtype=float)
    spreads: list[float] = []
    for current in range(window, len(values)):
        history = values[current - window : current]
        if not np.isfinite(values[current]) or not np.isfinite(history).all():
            continue
        q25, q75 = np.quantile(history, [0.25, 0.75], method="linear")
        spread = float(q75 - q25)
        if spread > 0.0:
            spreads.append(spread)
    return spreads


def _metric_histories(
    returns: pd.DataFrame,
    anchor_symbols: Mapping[str, str],
) -> dict[str, list[np.ndarray]]:
    histories = {metric: [] for metric in METRICS}
    for symbol in returns.columns:
        asset = returns[symbol].to_numpy(dtype=float)
        metric_series = {metric: np.full(len(asset), np.nan) for metric in METRICS}
        for end in range(len(asset)):
            if end >= SIGMA_WINDOW - 1:
                asset_window = asset[end - SIGMA_WINDOW + 1 : end + 1]
                if np.isfinite(asset_window).all():
                    metric_series["sigma"][end] = float(
                        np.std(asset_window, ddof=1) * np.sqrt(52)
                    )
                    for anchor_name, anchor_symbol in anchor_symbols.items():
                        if symbol == anchor_symbol:
                            # The anchor's own beta is identically one and
                            # would collapse the empirical IQR floor to noise.
                            continue
                        anchor_window = returns[anchor_symbol].to_numpy(dtype=float)[
                            end - BETA_WINDOW + 1 : end + 1
                        ]
                        if (
                            len(anchor_window) == BETA_WINDOW
                            and np.isfinite(anchor_window).all()
                        ):
                            variance = float(np.var(anchor_window, ddof=1))
                            if variance > np.finfo(float).eps:
                                beta = float(
                                    np.cov(asset_window, anchor_window, ddof=1)[0, 1]
                                    / variance
                                )
                                if np.isfinite(beta):
                                    metric_series[f"beta_{anchor_name}"][end] = beta

            if end >= ES_WINDOW - 1:
                es_window = asset[end - ES_WINDOW + 1 : end + 1]
                if np.isfinite(es_window).all():
                    metric_series["ES"][end] = float(
                        np.sort(-es_window)[-ES_TAIL_COUNT:].mean()
                    )

        for metric, values in metric_series.items():
            histories[metric].append(values)
    return histories


def calibrate(
    data_dir: str | Path,
    config_path: str | Path = REPOSITORY_ROOT / "config" / "tickers.yaml",
    quantile: float = CALIBRATION_QUANTILE,
) -> dict:
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be between 0 and 1")
    data_dir = Path(data_dir)
    with Path(config_path).open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    tickers = config.get("tickers", [])
    fx_settings = [item for item in tickers if item.get("role") == "fx"]
    fx_prices = None
    if fx_settings:
        fx_item = fx_settings[0]
        fx_path = data_dir / price_history_filename(
            fx_item["symbol"], fx_item.get("price_field", "Close")
        )
        fx_prices = pd.read_csv(fx_path, parse_dates=["Date"])

    instrument_prices: dict[str, pd.DataFrame] = {}
    selected_fields: dict[str, str] = {}
    for item in tickers:
        if item.get("role") != "asset" and not item.get("anchor_key"):
            continue
        symbol = item["symbol"]
        field = item.get("price_field", "Close")
        path = data_dir / price_history_filename(symbol, field)
        prices = pd.read_csv(path, parse_dates=["Date"])
        if not {"Date", "Close"}.issubset(prices.columns):
            raise ValueError(f"{path} must contain Date and Close columns")
        prices["Date"] = pd.to_datetime(prices["Date"], errors="coerce")
        prices["Close"] = pd.to_numeric(prices["Close"], errors="coerce")
        values = prices["Close"].to_numpy(dtype=float)
        if (
            prices["Date"].isna().any()
            or prices["Date"].duplicated().any()
            or not np.isfinite(values).all()
            or (values <= 0).any()
        ):
            raise ValueError(f"{path} contains invalid dates or prices")
        if item.get("currency") == "USD":
            if fx_prices is None:
                raise ValueError(f"{symbol} is USD-denominated but no FX history is configured")
            prices = convert_usd_prices_to_jpy(prices, fx_prices)
        instrument_prices[symbol] = prices
        selected_fields[symbol] = field

    anchor_symbols = {
        item["anchor_key"]: item["symbol"]
        for item in tickers if item.get("anchor_key") in ANCHORS
    }
    missing_anchors = set(ANCHORS) - set(anchor_symbols)
    if missing_anchors:
        raise ValueError(f"Missing anchor configurations: {sorted(missing_anchors)}")
    missing_symbols = set(anchor_symbols.values()) - set(instrument_prices)
    if missing_symbols:
        raise ValueError(f"Missing anchor price histories: {sorted(missing_symbols)}")

    weekly = {
        symbol: build_weekly_returns(prices)["return"]
        for symbol, prices in instrument_prices.items()
    }
    returns = pd.DataFrame(weekly).sort_index()
    metric_histories = _metric_histories(returns, anchor_symbols)
    metrics: dict[str, dict] = {}
    thresholds: dict[str, float] = {}
    for metric, series_list in metric_histories.items():
        spreads = [
            spread
            for values in series_list
            for spread in positive_historical_iqrs(values)
        ]
        if not spreads:
            raise ValueError(f"No positive historical IQR samples for {metric}")
        threshold = float(np.quantile(spreads, quantile, method="linear"))
        thresholds[metric] = threshold
        metrics[metric] = {
            "threshold": threshold,
            "positive_iqr_sample_count": len(spreads),
            "positive_iqr_min": float(np.min(spreads)),
            "positive_iqr_median": float(np.median(spreads)),
            "positive_iqr_max": float(np.max(spreads)),
        }

    return {
        "method": "linear_quantile_of_positive_prior_52_metric_value_iqrs",
        "quantile": quantile,
        "normalization_window": NORMALIZATION_WINDOW,
        "history_start": str(returns.index.min().date()),
        "history_end": str(returns.index.max().date()),
        "weekly_period_count": len(returns),
        "instruments": list(instrument_prices),
        "price_fields": selected_fields,
        "fx_alignment": "exact_calendar_date_no_fill",
        "thresholds": thresholds,
        "metrics": metrics,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=REPOSITORY_ROOT / "data" / "processed")
    parser.add_argument("--config", type=Path, default=REPOSITORY_ROOT / "config" / "tickers.yaml")
    parser.add_argument("--quantile", type=float, default=CALIBRATION_QUANTILE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = calibrate(args.data_dir, args.config, args.quantile)
    content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
