"""Daily USD-to-JPY price conversion with explicit FX quality status."""

from __future__ import annotations

import numpy as np
import pandas as pd


def convert_usd_prices_to_jpy(
    usd_prices: pd.DataFrame,
    usd_jpy: pd.DataFrame,
    date_column: str = "Date",
    price_column: str = "Close",
) -> pd.DataFrame:
    """Convert USD prices using an exact calendar-date USD/JPY quote.

    No forward-fill or stale FX quote is used. Dates with no matching quote
    remain present with ``price_status='missing_fx'`` and a null converted price.
    Returned prices retain the ``Date``/``Close`` schema consumed by Layer 1.
    """
    required = {date_column, price_column}
    if (
        not isinstance(usd_prices, pd.DataFrame)
        or not required.issubset(usd_prices.columns)
        or not isinstance(usd_jpy, pd.DataFrame)
        or not required.issubset(usd_jpy.columns)
        or usd_prices.empty
    ):
        return pd.DataFrame(columns=[date_column, price_column, "price_status"])

    asset_dates = pd.to_datetime(usd_prices[date_column], errors="coerce")
    if not asset_dates.isna().any() and getattr(asset_dates.dt, "tz", None) is None:
        asset_dates = asset_dates.dt.normalize()
    if (
        asset_dates.isna().any()
        or getattr(asset_dates.dt, "tz", None) is not None
        or asset_dates.duplicated().any()
    ):
        return pd.DataFrame(columns=[date_column, price_column, "price_status"])

    asset_values = pd.to_numeric(usd_prices[price_column], errors="coerce")
    if usd_jpy.empty:
        statuses = [
            "invalid_price" if not np.isfinite(value) or value <= 0 else "missing_fx"
            for value in asset_values
        ]
        return pd.DataFrame(
            {
                date_column: asset_dates,
                price_column: np.nan,
                "price_status": statuses,
            }
        )

    fx_dates = pd.to_datetime(usd_jpy[date_column], errors="coerce")
    if not fx_dates.isna().any() and getattr(fx_dates.dt, "tz", None) is None:
        fx_dates = fx_dates.dt.normalize()
    if (
        fx_dates.isna().any()
        or getattr(fx_dates.dt, "tz", None) is not None
        or fx_dates.duplicated().any()
    ):
        return pd.DataFrame(columns=[date_column, price_column, "price_status"])

    asset = pd.DataFrame(
        {
            date_column: asset_dates,
            "_usd": asset_values,
        }
    )
    fx = pd.DataFrame(
        {
            date_column: fx_dates,
            "_fx": pd.to_numeric(usd_jpy[price_column], errors="coerce"),
            "_fx_present": True,
        }
    )
    joined = asset.merge(fx, on=date_column, how="left", validate="one_to_one")

    statuses: list[str] = []
    converted: list[float] = []
    for usd, rate, fx_present in zip(
        joined["_usd"], joined["_fx"], joined["_fx_present"]
    ):
        if not np.isfinite(usd) or usd <= 0:
            converted.append(np.nan)
            statuses.append("invalid_price")
        elif pd.isna(fx_present):
            converted.append(np.nan)
            statuses.append("missing_fx")
        elif not np.isfinite(rate) or rate <= 0:
            converted.append(np.nan)
            statuses.append("invalid_price")
        else:
            converted.append(float(usd * rate))
            statuses.append("ok")

    return pd.DataFrame(
        {
            date_column: joined[date_column],
            price_column: converted,
            "price_status": statuses,
        }
    )
