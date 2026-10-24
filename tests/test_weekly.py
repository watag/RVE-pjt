"""Tests for daily price alignment to the RVE Friday weekly index."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


LAYER1_DIR = Path(__file__).resolve().parents[1] / "layer1"
sys.path.insert(0, str(LAYER1_DIR))

from weekly import build_weekly_returns  # noqa: E402


class WeeklyPricePreparationTests(unittest.TestCase):
    def test_uses_last_observation_when_friday_is_a_market_holiday(self):
        prices = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2025-01-02", "2025-01-06", "2025-01-09"]),
                "Close": [100.0, 105.0, 110.0],
            }
        )

        result = build_weekly_returns(prices)

        self.assertEqual(
            result.index.tolist(), list(pd.to_datetime(["2025-01-03", "2025-01-10"]))
        )
        self.assertEqual(result.loc["2025-01-03", "price_date"], pd.Timestamp("2025-01-02"))
        self.assertEqual(result.loc["2025-01-10", "price_date"], pd.Timestamp("2025-01-09"))
        self.assertAlmostEqual(result.loc["2025-01-10", "return"], 0.1)
        self.assertEqual(result["return_status"].tolist(), ["insufficient_history", "ok"])

    def test_missing_week_is_explicit_and_does_not_bridge_returns(self):
        prices = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2025-01-03", "2025-01-13", "2025-01-22"]),
                "Close": [100.0, 110.0, 121.0],
            }
        )

        result = build_weekly_returns(prices)

        self.assertEqual(
            result["price_status"].tolist(), ["ok", "missing_price", "ok", "ok"]
        )
        self.assertEqual(
            result["return_status"].tolist(),
            ["insufficient_history", "missing_price", "missing_price", "ok"],
        )
        self.assertTrue(np.isnan(result.loc["2025-01-10", "price"]))
        self.assertTrue(np.isnan(result.loc["2025-01-17", "return"]))
        self.assertAlmostEqual(result.loc["2025-01-24", "return"], 0.1)

    def test_nonpositive_final_weekly_price_is_invalid_without_earlier_fallback(self):
        prices = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2025-01-06", "2025-01-09", "2025-01-13"]),
                "Close": [100.0, 0.0, 110.0],
            }
        )

        result = build_weekly_returns(prices)

        self.assertEqual(result.loc["2025-01-10", "price_status"], "invalid_price")
        self.assertEqual(
            result.loc["2025-01-10", "return_status"], "insufficient_history"
        )
        self.assertTrue(np.isnan(result.loc["2025-01-10", "price"]))
        self.assertEqual(result.loc["2025-01-17", "return_status"], "invalid_price")

    def test_duplicate_daily_date_is_configuration_error(self):
        prices = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2025-01-03", "2025-01-03"]),
                "Close": [100.0, 101.0],
            }
        )

        result = build_weekly_returns(prices)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["price_status"], "configuration_error")

    def test_missing_close_on_final_observation_is_not_skipped(self):
        prices = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2025-01-06", "2025-01-09"]),
                "Close": [100.0, np.nan],
            }
        )

        result = build_weekly_returns(prices)

        self.assertEqual(result.iloc[0]["price_status"], "missing_price")
        self.assertTrue(np.isnan(result.iloc[0]["price"]))


if __name__ == "__main__":
    unittest.main()
