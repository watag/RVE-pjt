import pandas as pd
import numpy as np
import os
from collections.abc import Mapping
from normalize import robust_normalize
from beta import calc_all_betas, load_price, calc_log_return
from volatility import calc_volatility, calc_es
from risk_metrics import ANCHORS, calculate_risk_vector
from weekly import build_weekly_returns


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

    anchor_returns = pd.DataFrame(weekly_anchors)
    return calculate_risk_vector(
        weekly_asset["return"], anchor_returns, iqr_thresholds
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


def main():
    # ===== パラメータ =====
    VOL_WINDOW = 120
    BETA_WINDOW = 120
    NORM_WINDOW = 60

    # ===== パス =====
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = os.path.join(BASE_DIR, "data", "processed")
    OUTPUT_DIR = os.path.join(BASE_DIR, "data", "layer1")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ===== 対象銘柄 =====
    asset_name = "7203.T.csv"
    asset_path = os.path.join(DATA_DIR, asset_name)

    asset_df = load_price(asset_path)

    # ===== volatility =====
    vol_df = build_volatility(asset_df.copy(), NORM_WINDOW, VOL_WINDOW)

    # ===== factor =====
    factor_files = {
        "gold": "1540.T.csv",
        "topix": "1306.T.csv",
        "sp500": "^GSPC.csv",
        "ust": "TLT.csv",
        "jgb": "2510.T.csv",
        "usd_jpy": "JPY=X.csv",
    }

    factors = {}
    for name, filename in factor_files.items():
        path = os.path.join(DATA_DIR, filename)
        df = load_price(path)
        df = calc_log_return(df)
        factors[name] = df

    # ===== beta =====
    asset_return_df = calc_log_return(asset_df.copy())
    beta_df = build_beta(asset_return_df, factors, BETA_WINDOW, NORM_WINDOW)

    # ===== merge =====
    layer1 = vol_df.merge(beta_df, on="Date", how="inner")

    # ===== 出力 =====
    output_path = os.path.join(OUTPUT_DIR, asset_name.replace(".csv", "_layer1.csv"))
    layer1.to_csv(output_path, index=False)

    print("Saved:", output_path)
    print(layer1.tail())


if __name__ == "__main__":
    main()
