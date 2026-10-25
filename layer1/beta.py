import pandas as pd
import numpy as np


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
        how="left",
        suffixes=("_asset", "_factor")
    )

    df["log_return_factor"] = df["log_return_factor"].ffill().bfill()

    betas = []

    for i in range(len(df)):
        if i < window:
            betas.append(np.nan)
            continue

        w = df.iloc[i-window:i]

        if w["log_return_factor"].isna().any():
            betas.append(np.nan)
            continue

        cov = np.cov(w["log_return_asset"], w["log_return_factor"])[0, 1]
        var = np.var(w["log_return_factor"])

        if var == 0 or np.isnan(var):
            betas.append(np.nan)
            continue

        beta = cov / var
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


# Legacy calculation helpers remain importable for callers that need them.
# The supported executable pipeline is layer1_vector.main().
