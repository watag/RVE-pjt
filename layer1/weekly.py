"""Daily-to-weekly price preparation for RVE.

Prices must be in their analysis currency before calling this module (for
example, USD assets converted to JPY with an aligned FX rate).
"""

import numpy as np
import pandas as pd


OUTPUT_COLUMNS = ("price_date", "price", "price_status", "return", "return_status")


def _empty_result(index: pd.Index, status: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "price_date": pd.NaT,
            "price": np.nan,
            "price_status": status,
            "return": np.nan,
            "return_status": status,
        },
        index=index,
        columns=OUTPUT_COLUMNS,
    )


def _configuration_error() -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.NaT], name="week_ending")
    return _empty_result(index, "configuration_error")


def build_weekly_returns(
    daily_prices: pd.DataFrame,
    date_column: str = "Date",
    price_column: str = "Close",
) -> pd.DataFrame:
    """Return Friday-indexed weekly closes and simple returns.

    Each week's close is the final dated observation in that Friday-ending
    week, so Friday holidays use the last available trading day's price. The
    actual observation date is retained in ``price_date``. Missing weeks are
    represented explicitly and are never forward-filled. A return is produced
    only when both this week and the immediately preceding week have valid
    prices. ``daily_prices`` must already be converted to the desired currency.
    """
    if (
        not isinstance(daily_prices, pd.DataFrame)
        or date_column not in daily_prices.columns
        or price_column not in daily_prices.columns
        or daily_prices.empty
    ):
        return _configuration_error()

    dates = pd.to_datetime(daily_prices[date_column], errors="coerce")
    if dates.isna().any() or getattr(dates.dt, "tz", None) is not None:
        return _configuration_error()
    if dates.duplicated().any():
        return _configuration_error()

    prices = pd.to_numeric(daily_prices[price_column], errors="coerce")
    frame = pd.DataFrame({"price_date": dates, "price": prices}).sort_values(
        "price_date"
    )
    frame["week_ending"] = frame["price_date"].dt.to_period("W-FRI").dt.end_time.dt.normalize()

    # Use the final source row, including a missing/invalid close, rather than
    # silently falling back to an earlier observation in the same week.
    weekly = frame.groupby("week_ending", sort=True).tail(1).set_index("week_ending")
    complete_index = pd.date_range(
        weekly.index.min(), weekly.index.max(), freq="W-FRI", name="week_ending"
    )
    weekly = weekly.reindex(complete_index)

    price_status: list[str] = []
    for value in weekly["price"].to_numpy(dtype=float):
        if np.isnan(value):
            price_status.append("missing_price")
        elif not np.isfinite(value) or value <= 0:
            price_status.append("invalid_price")
        else:
            price_status.append("ok")
    weekly["price_status"] = price_status
    weekly.loc[weekly["price_status"] == "invalid_price", "price"] = np.nan

    returns: list[float] = []
    return_status: list[str] = []
    for position, (_, row) in enumerate(weekly.iterrows()):
        if position == 0:
            returns.append(np.nan)
            return_status.append("insufficient_history")
            continue
        current_status = row["price_status"]
        previous_status = weekly["price_status"].iloc[position - 1]
        if current_status != "ok":
            returns.append(np.nan)
            return_status.append(current_status)
        elif previous_status != "ok":
            returns.append(np.nan)
            return_status.append(previous_status)
        else:
            previous_price = float(weekly["price"].iloc[position - 1])
            value = float(row["price"] / previous_price - 1.0)
            if np.isfinite(value):
                returns.append(value)
                return_status.append("ok")
            else:
                returns.append(np.nan)
                return_status.append("calculation_error")

    weekly["return"] = returns
    weekly["return_status"] = return_status
    return weekly.loc[:, OUTPUT_COLUMNS]
