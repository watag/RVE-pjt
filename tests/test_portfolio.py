"""Tests for weekly portfolio returns and risk-vector integration."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


LAYER1_DIR = Path(__file__).resolve().parents[1] / "layer1"
sys.path.insert(0, str(LAYER1_DIR))

from portfolio import calculate_portfolio_returns  # noqa: E402
from risk_metrics import METRICS, calculate_risk_vector  # noqa: E402


class PortfolioReturnTests(unittest.TestCase):
    def test_uses_each_weeks_beginning_weights(self):
        dates = pd.date_range("2025-01-03", periods=3, freq="W-FRI")
        returns = pd.DataFrame(
            {"a": [0.10, -0.05, 0.03], "b": [-0.02, 0.04, 0.06]}, index=dates
        )
        weights = pd.DataFrame(
            {"a": [0.6, 0.4, 0.5], "b": [0.4, 0.6, 0.5]}, index=dates
        )

        result = calculate_portfolio_returns(returns, weights)

        np.testing.assert_allclose(result["portfolio_return"], [0.052, 0.004, 0.045])
        self.assertEqual(result["status"].tolist(), ["ok", "ok", "ok"])

    def test_does_not_renormalize_when_a_held_asset_return_is_missing(self):
        dates = pd.date_range("2025-01-03", periods=1, freq="W-FRI")
        returns = pd.DataFrame({"a": [0.10], "b": [np.nan]}, index=dates)
        weights = pd.DataFrame({"a": [0.5], "b": [0.5]}, index=dates)

        result = calculate_portfolio_returns(returns, weights)

        self.assertTrue(np.isnan(result.loc[dates[0], "portfolio_return"]))
        self.assertEqual(result.loc[dates[0], "status"], "missing_price")

    def test_zero_weight_missing_return_does_not_invalidate_week(self):
        dates = pd.date_range("2025-01-03", periods=1, freq="W-FRI")
        returns = pd.DataFrame({"a": [0.04], "b": [np.nan]}, index=dates)
        weights = pd.DataFrame({"a": [1.0], "b": [0.0]}, index=dates)

        result = calculate_portfolio_returns(returns, weights)

        self.assertEqual(result.loc[dates[0], "portfolio_return"], 0.04)
        self.assertEqual(result.loc[dates[0], "status"], "ok")

    def test_rejects_weights_that_do_not_sum_to_one(self):
        dates = pd.date_range("2025-01-03", periods=1, freq="W-FRI")
        returns = pd.DataFrame({"a": [0.04], "b": [0.02]}, index=dates)
        weights = pd.DataFrame({"a": [0.6], "b": [0.3]}, index=dates)

        result = calculate_portfolio_returns(returns, weights)

        self.assertTrue(np.isnan(result.loc[dates[0], "portfolio_return"]))
        self.assertEqual(result.loc[dates[0], "status"], "configuration_error")

    def test_missing_weekly_weights_are_not_carried_forward(self):
        dates = pd.date_range("2025-01-03", periods=2, freq="W-FRI")
        returns = pd.DataFrame({"a": [0.04, 0.02]}, index=dates)
        weights = pd.DataFrame({"a": [1.0]}, index=dates[:1])

        result = calculate_portfolio_returns(returns, weights)

        self.assertEqual(result.loc[dates[0], "status"], "ok")
        self.assertEqual(result.loc[dates[1], "status"], "configuration_error")

    def test_portfolio_returns_feed_the_existing_risk_vector_calculator(self):
        count = 220
        dates = pd.date_range("2020-01-03", periods=count, freq="W-FRI")
        step = np.arange(count, dtype=float)
        asset_returns = pd.DataFrame(
            {
                "a": 0.012 * np.sin(step * 0.13),
                "b": 0.009 * np.cos(step * 0.17),
            },
            index=dates,
        )
        weights = pd.DataFrame({"a": 0.6, "b": 0.4}, index=dates)
        anchors = pd.DataFrame(
            {
                "gold": 0.01 * np.sin(step * 0.11),
                "us_equity": 0.015 * np.cos(step * 0.09),
                "japan_equity": 0.008 * np.sin(step * 0.07),
                "us_treasury": 0.004 * np.cos(step * 0.05),
                "japan_bond": 0.002 * np.sin(step * 0.03),
            },
            index=dates,
        )

        portfolio = calculate_portfolio_returns(asset_returns, weights)
        thresholds = {metric: 0.0 for metric in METRICS}
        vector = calculate_risk_vector(portfolio["portfolio_return"], anchors, thresholds)

        self.assertTrue((portfolio["status"] == "ok").all())
        self.assertEqual(vector["sigma"]["status"], "ok")
        self.assertEqual(vector["ES"]["status"], "ok")
        self.assertEqual(vector["beta_us_equity"]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
