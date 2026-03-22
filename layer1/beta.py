import pandas as pd
import numpy as np
import os
from normalize import robust_normalize


def load_price(path):
    df = pd.read_csv(path, parse_dates=["Date"])
    df = df.sort_values("Date")
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"])
    return df


def calc_log_return(df):
    df["log_return"] = np.log(df["Close"] / df["Close"].shift(1))
    return df.dropna()


def calc_beta(asset_df, factor_df, window=120):
    df = asset_df[["Date", "log_return"]].merge(
        factor_df[["Date", "log_return"]],
        on="Date",
        suffixes=("_asset", "_factor")
    )

    betas = []

    for i in range(len(df)):
        if i < window:
            betas.append(np.nan)
            continue

        w = df.iloc[i-window:i]

        cov = np.cov(w["log_return_asset"], w["log_return_factor"])[0, 1]
        var = np.var(w["log_return_factor"])

        beta = cov / var if var != 0 else np.nan
        betas.append(beta)

    df["beta"] = betas
    return df[["Date", "beta"]]


def calc_all_betas(asset_df, factor_dict, window=120):
    result = asset_df[["Date"]].copy()

    for name, factor_df in factor_dict.items():
        beta_df = calc_beta(asset_df, factor_df, window)
        result = result.merge(beta_df, on="Date", how="left")
        result = result.rename(columns={"beta": f"beta_{name}"})

    return result


def main():
    # ===== パラメータ =====
    BETA_WINDOW = 120
    NORM_WINDOW = 60

    # ===== パス設定 =====
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = os.path.join(BASE_DIR, "data", "processed")

    # ===== 対象銘柄 =====
    asset_path = os.path.join(DATA_DIR, "7203.T.csv")

    asset = load_price(asset_path)
    asset = calc_log_return(asset)

    # ===== 因子 =====
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

    # ===== β計算 =====
    beta_df = calc_all_betas(asset, factors, window=BETA_WINDOW)

    # ===== 正規化 =====
    beta_cols = [col for col in beta_df.columns if col.startswith("beta_")]

    for col in beta_cols:
        beta_df[col + "_norm"] = robust_normalize(
            beta_df[col],
            window=NORM_WINDOW
        )

    # ===== 出力 =====
    cols_to_show = ["Date"] + beta_cols + [col + "_norm" for col in beta_cols]

    print(beta_df[cols_to_show].tail())


if __name__ == "__main__":
    main()