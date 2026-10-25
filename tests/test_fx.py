"""Tests for explicit USD-to-JPY conversion and FX status propagation."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


LAYER1_DIR = Path(__file__).resolve().parents[1] / "layer1"
sys.path.insert(0, str(LAYER1_DIR))

from fx import convert_usd_prices_to_jpy  # noqa: E402
from weekly import build_weekly_returns  # noqa: E402


class FxConversionTests(unittest.TestCase):
    def test_converts_prices_before_weekly_return_calculation(self):
        dates = pd.to_datetime(["2025-01-03", "2025-01-10"])
        usd = pd.DataFrame({"Date": dates, "Close": [100.0, 110.0]})
        fx = pd.DataFrame({"Date": dates, "Close": [150.0, 155.0]})

        jpy = convert_usd_prices_to_jpy(usd, fx)
        weekly = build_weekly_returns(jpy)

        self.assertEqual(jpy["Close"].tolist(), [15000.0, 17050.0])
        self.assertAlmostEqual(weekly.iloc[-1]["return"], 17050.0 / 15000.0 - 1.0)
        self.assertEqual(weekly.iloc[-1]["return_status"], "ok")

    def test_same_calendar_date_matches_different_intraday_timestamps(self):
        usd = pd.DataFrame(
            {"Date": pd.to_datetime(["2025-01-03 16:00"]), "Close": [100.0]}
        )
        fx = pd.DataFrame(
            {"Date": pd.to_datetime(["2025-01-03 00:00"]), "Close": [150.0]}
        )

        result = convert_usd_prices_to_jpy(usd, fx)

        self.assertEqual(result.loc[0, "Close"], 15000.0)
        self.assertEqual(result.loc[0, "price_status"], "ok")

    def test_missing_fx_is_not_filled_and_remains_distinct(self):
        dates = pd.to_datetime(["2025-01-03", "2025-01-10"])
        usd = pd.DataFrame({"Date": dates, "Close": [100.0, 110.0]})
        fx = pd.DataFrame({"Date": dates[:1], "Close": [150.0]})

        jpy = convert_usd_prices_to_jpy(usd, fx)
        weekly = build_weekly_returns(jpy)

        self.assertTrue(np.isnan(jpy.loc[1, "Close"]))
        self.assertEqual(jpy.loc[1, "price_status"], "missing_fx")
        self.assertEqual(weekly.iloc[-1]["return_status"], "missing_fx")

    def test_absent_fx_history_marks_each_valid_usd_price_missing_fx(self):
        usd = pd.DataFrame(
            {"Date": pd.to_datetime(["2025-01-03"]), "Close": [100.0]}
        )
        no_fx = pd.DataFrame(columns=["Date", "Close"])

        result = convert_usd_prices_to_jpy(usd, no_fx)

        self.assertTrue(np.isnan(result.loc[0, "Close"]))
        self.assertEqual(result.loc[0, "price_status"], "missing_fx")

    def test_duplicate_dates_fail_closed(self):
        asset = pd.DataFrame(
            {"Date": pd.to_datetime(["2025-01-03", "2025-01-03"]), "Close": [100, 101]}
        )
        fx = pd.DataFrame({"Date": pd.to_datetime(["2025-01-03"]), "Close": [150]})

        result = convert_usd_prices_to_jpy(asset, fx)

        self.assertEqual(list(result.columns), ["Date", "Close", "price_status"])
        self.assertTrue(result.empty)

    def test_nonpositive_fx_is_invalid_price_not_missing_fx(self):
        date = pd.to_datetime(["2025-01-03"])
        usd = pd.DataFrame({"Date": date, "Close": [100.0]})
        fx = pd.DataFrame({"Date": date, "Close": [0.0]})

        result = convert_usd_prices_to_jpy(usd, fx)

        self.assertTrue(np.isnan(result.loc[0, "Close"]))
        self.assertEqual(result.loc[0, "price_status"], "invalid_price")


if __name__ == "__main__":
    unittest.main()
