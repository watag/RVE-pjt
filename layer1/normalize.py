import pandas as pd
import numpy as np


def robust_normalize(series, window=120):
    median = series.rolling(window).median()
    q75 = series.rolling(window).quantile(0.75)
    q25 = series.rolling(window).quantile(0.25)
    iqr = q75 - q25

    # ゼロ割防止
    iqr = iqr.replace(0, np.nan)

    normalized = (series - median) / iqr
    return normalized


def normalize_dataframe(df, columns, window=120):
    result = df.copy()

    for col in columns:
        result[col + "_norm"] = robust_normalize(result[col], window)

    return result