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


# Legacy calculation helpers remain importable for callers that need them.
# The supported executable pipeline is layer1_vector.main().
