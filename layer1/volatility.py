import pandas as pd
import numpy as np
import glob
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


def calc_volatility(df, window=120):
    df["sigma"] = df["log_return"].rolling(window).std()
    return df


def calc_es(df, window=120, alpha=0.05):
    es_list = []
    returns = df["log_return"]

    for i in range(len(df)):
        if i < window:
            es_list.append(np.nan)
            continue

        window_data = returns.iloc[i-window:i]
        var_threshold = np.quantile(window_data, alpha)
        es = window_data[window_data <= var_threshold].mean()

        es_list.append(es)

    df["ES"] = es_list
    return df


def main():
    paths = glob.glob("../data/processed/*.csv")

    if not paths:
        print("CSVが存在しません")
        return

    for path in paths:
        df = load_price(path)
        df = calc_log_return(df)
        df = calc_volatility(df)
        df = calc_es(df)

      # 正規化（追加）
        df["sigma_norm"] = robust_normalize(df["sigma"])
        df["ES_norm"] = robust_normalize(df["ES"])


        symbol = os.path.basename(path)

        latest = df[["Date", "sigma", "ES","sigma_norm","ES_norm"]].dropna().tail(1)

        if latest.empty:
            print(f"{symbol} : データ不足（window未満）")
        else:
            print(symbol)
            print(latest)
            print("-" * 40)


if __name__ == "__main__":
    main()