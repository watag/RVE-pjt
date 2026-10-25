import json
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Mapping
import pandas as pd
from normalize import robust_normalize
from beta import calc_all_betas, load_price, calc_log_return
from volatility import calc_volatility, calc_es
from risk_metrics import ANCHORS, calculate_risk_vector
from weekly import build_weekly_returns
from fx import convert_usd_prices_to_jpy
from portfolio import calculate_portfolio_risk_vector


def build_risk_vector_from_daily_prices(
    asset_prices,
    anchor_prices,
    iqr_thresholds=None,
):
    """Build the v1.0 weekly risk vector from daily, analysis-currency prices.

    ``asset_prices`` and each value in ``anchor_prices`` must contain ``Date``
    and ``Close`` columns. Prices must already be in the same analysis currency;
    USD-to-JPY conversion and source-specific adjusted-price selection happen
    before this function. The legacy daily log-return builders below remain
    available for existing callers.
    """
    if (
        not isinstance(asset_prices, pd.DataFrame)
        or "Date" not in asset_prices.columns
        or "Close" not in asset_prices.columns
    ):
        invalid_asset = pd.Series(dtype=float, index=pd.Index([]))
        return calculate_risk_vector(invalid_asset, pd.DataFrame(), iqr_thresholds)

    weekly_asset = build_weekly_returns(asset_prices)
    if weekly_asset.index.hasnans:
        invalid_asset = pd.Series(dtype=float, index=pd.Index([]))
        return calculate_risk_vector(invalid_asset, pd.DataFrame(), iqr_thresholds)

    weekly_anchors = {}
    anchor_statuses = {}
    if isinstance(anchor_prices, Mapping):
        for name in ANCHORS:
            prices = anchor_prices.get(name)
            if (
                not isinstance(prices, pd.DataFrame)
                or "Date" not in prices.columns
                or "Close" not in prices.columns
            ):
                continue
            weekly = build_weekly_returns(prices)
            if not weekly.index.hasnans:
                weekly_anchors[name] = weekly["return"]
                anchor_statuses[name] = weekly["return_status"]

    anchor_returns = pd.DataFrame(weekly_anchors)
    return calculate_risk_vector(
        weekly_asset["return"], anchor_returns, iqr_thresholds,
        asset_statuses=weekly_asset["return_status"],
        anchor_statuses=pd.DataFrame(anchor_statuses),
    )


def build_volatility(df, norm_window=60, vol_window=120):
    df = calc_log_return(df)
    df = calc_volatility(df, window=vol_window)
    df = calc_es(df, window=vol_window)

    df["sigma_norm"] = robust_normalize(df["sigma"], window=norm_window)
    df["ES_norm"] = robust_normalize(df["ES"], window=norm_window)

    return df[["Date", "sigma_norm", "ES_norm"]]


def build_beta(asset_df, factor_dict, beta_window=120, norm_window=60):
    beta_df = calc_all_betas(asset_df, factor_dict, window=beta_window)

    beta_cols = [c for c in beta_df.columns if c.startswith("beta_")]

    for col in beta_cols:
        beta_df[col + "_norm"] = robust_normalize(
            beta_df[col],
            window=norm_window
        )

    cols = ["Date"] + [c + "_norm" for c in beta_cols]
    return beta_df[cols]


def _read_daily_prices(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["Date", "Close"])
    frame = pd.read_csv(path, parse_dates=["Date"])
    if "Close" not in frame.columns:
        return pd.DataFrame(columns=["Date", "Close"])
    return frame[["Date", "Close"]]


def _price_history_filename(symbol: str, price_field: str) -> str:
    suffix = price_field.strip().replace(" ", "_")
    return f"{symbol}.csv" if suffix == "Close" else f"{symbol}.{suffix}.csv"


def _read_weight_history(path: Path) -> pd.DataFrame:
    """Read weekly weights keyed by return week ending, with opening weights."""
    frame = pd.read_csv(path)
    if "Date" not in frame.columns:
        raise ValueError("weight_history_missing_Date_column")
    dates = pd.to_datetime(frame.pop("Date"), errors="coerce")
    if dates.isna().any():
        raise ValueError("weight_history_contains_invalid_dates")
    if dates.duplicated().any():
        raise ValueError("weight_history_contains_duplicate_dates")
    frame.index = pd.DatetimeIndex(dates, name="week_ending")
    return frame


def main(data_dir=None, output_dir=None, config_path=None):
    """Run the v1 weekly vector pipeline and write a JSON snapshot.

    Legacy builder functions remain importable for existing callers, but the
    normal executable entry point has exactly one calculation route: v1.0.
    """
    repository_root = Path(__file__).resolve().parents[1]
    data_path = Path(data_dir) if data_dir is not None else repository_root / "data" / "processed"
    result_dir = Path(output_dir) if output_dir is not None else repository_root / "data" / "layer1"
    settings_path = Path(config_path) if config_path is not None else repository_root / "config" / "tickers.yaml"

    config = fetch_config(settings_path)
    ticker_settings = config.get("tickers", [])
    assets = [item for item in ticker_settings if item.get("role") == "asset"]
    if not assets:
        assets = [item for item in ticker_settings if item.get("symbol") == "7203.T"]
    fx_settings = [item for item in ticker_settings if item.get("role") == "fx"]
    if not assets:
        raise ValueError("Configuration must define at least one role: asset ticker")

    asset_setting = assets[0]
    fx_prices = (
        _read_daily_prices(data_path / f"{fx_settings[0]['symbol']}.csv")
        if fx_settings else pd.DataFrame(columns=["Date", "Close"])
    )

    prices_by_symbol = {}
    for item in ticker_settings:
        price_field = item.get("price_field", "Close")
        prices = _read_daily_prices(
            data_path / _price_history_filename(item["symbol"], price_field)
        )
        if item.get("currency") == "USD":
            prices = convert_usd_prices_to_jpy(prices, fx_prices)
        prices_by_symbol[item["symbol"]] = prices

    asset_prices = prices_by_symbol[asset_setting["symbol"]]
    anchor_prices = {}
    source_metadata = {asset_setting["symbol"]: asset_setting.get("price_field", "Close")}
    for item in ticker_settings:
        anchor_key = item.get("anchor_key")
        if not anchor_key:
            continue
        prices = prices_by_symbol[item["symbol"]]
        source_metadata[item["symbol"]] = item.get("price_field", "Close")
        anchor_prices[anchor_key] = prices

    thresholds = config.get("normalization", {}).get("iqr_thresholds")
    vector = build_risk_vector_from_daily_prices(asset_prices, anchor_prices, thresholds)
    portfolio_result = None
    portfolio_mode = None
    portfolio_config = config.get("portfolio")
    if portfolio_config is None:
        portfolio_status = "not_configured"
        portfolio_reason = "portfolio_configuration_is_null"
    elif not isinstance(portfolio_config, dict):
        portfolio_status = "configuration_error"
        portfolio_reason = "portfolio_configuration_must_be_a_mapping_or_null"
        portfolio_result = {"status": portfolio_status, "reason": portfolio_reason}
    else:
        portfolio_mode = portfolio_config.get("mode")
        try:
            if portfolio_mode == "scenario":
                current_weights = portfolio_config.get("current_weights")
                if not isinstance(current_weights, dict) or not current_weights:
                    raise ValueError("scenario_current_weights_missing_or_invalid")
                portfolio_symbols = set(current_weights)
                weights = pd.Series(current_weights, dtype=float)
            elif portfolio_mode == "realized":
                portfolio_symbols = set(portfolio_config.get("symbols", []))
                weights_path = portfolio_config.get("weights_file")
                if not portfolio_symbols:
                    raise ValueError("realized_symbols_missing")
                if not weights_path:
                    raise ValueError("realized_weights_file_missing")
                weights = _read_weight_history(data_path / weights_path)
            else:
                raise ValueError("unsupported_portfolio_mode")

            portfolio_series = {}
            for item in ticker_settings:
                if item["symbol"] not in portfolio_symbols:
                    continue
                weekly = build_weekly_returns(prices_by_symbol[item["symbol"]])
                portfolio_series[item["symbol"]] = weekly["return"]
            portfolio_returns = pd.DataFrame(portfolio_series)
            if portfolio_returns.empty:
                raise ValueError("portfolio_has_no_configured_asset_price_series")

            anchor_series = {
                name: build_weekly_returns(prices)["return"]
                for name, prices in anchor_prices.items()
            }
            portfolio_anchors = pd.DataFrame(anchor_series)
            portfolio_result = calculate_portfolio_risk_vector(
                portfolio_returns, weights, portfolio_anchors, thresholds,
                mode=portfolio_mode,
            )
        except (OSError, TypeError, ValueError, KeyError) as error:
            portfolio_result = {
                "analysis_mode": portfolio_mode,
                "status": "configuration_error",
                "reason": str(error),
            }
        portfolio_status = portfolio_result.get(
            "portfolio_status", portfolio_result.get("status", "calculation_error")
        )
        portfolio_reason = portfolio_result.get("reason")
    result = {
        "asset_symbol": asset_setting["symbol"],
        "analysis_currency": "JPY",
        "price_fields": source_metadata,
        "fx_alignment": "exact_calendar_date_no_fill",
        "asset": vector,
        "portfolio": portfolio_result,
        "portfolio_status": portfolio_status,
        "portfolio_reason": portfolio_reason,
        "portfolio_mode": portfolio_mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    result_dir.mkdir(parents=True, exist_ok=True)
    output_path = result_dir / f"{asset_setting['symbol']}_risk_vector.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {output_path}")
    print(json.dumps(vector, ensure_ascii=False))


def fetch_config(path):
    import yaml
    with Path(path).open("r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


if __name__ == "__main__":
    main()
