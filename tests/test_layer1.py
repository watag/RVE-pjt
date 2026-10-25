"""Regression tests for the Layer 1 behavior restored from origin/dev."""

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


LAYER1_DIR = Path(__file__).resolve().parents[1] / "layer1"
sys.path.insert(0, str(LAYER1_DIR))

from beta import calc_beta, calc_log_return, load_price  # noqa: E402
from layer1_vector import build_beta, build_volatility  # noqa: E402
from normalize import robust_normalize  # noqa: E402
from volatility import calc_es, calc_volatility  # noqa: E402


class Layer1CalculationTests(unittest.TestCase):
    def test_load_price_sorts_dates_before_calc_log_return(self):
        prices = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2025-01-02", "2025-01-01", "2025-01-03"]),
                "Close": [121.0, 100.0, 110.0],
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "prices.csv"
            prices.to_csv(path, index=False)
            sorted_prices = load_price(path)
        result = calc_log_return(sorted_prices)

        self.assertEqual(result["Date"].tolist(), list(pd.to_datetime(["2025-01-02", "2025-01-03"])))
        np.testing.assert_allclose(result["log_return"], [np.log(1.21), np.log(110 / 121)])

    def test_volatility_uses_rolling_sample_standard_deviation(self):
        returns = pd.DataFrame({"log_return": [1.0, 2.0, 4.0]})

        result = calc_volatility(returns, window=2)

        self.assertTrue(np.isnan(result.loc[0, "sigma"]))
        self.assertAlmostEqual(result.loc[1, "sigma"], np.std([1.0, 2.0], ddof=1))
        self.assertAlmostEqual(result.loc[2, "sigma"], np.std([2.0, 4.0], ddof=1))

    def test_es_uses_prior_window_and_signed_lower_tail_mean(self):
        returns = pd.DataFrame({"log_return": [-4.0, -3.0, -2.0, -1.0, 0.0, 1.0]})

        result = calc_es(returns, window=4, alpha=0.25)

        self.assertTrue(result["ES"].iloc[:4].isna().all())
        self.assertEqual(result.loc[4, "ES"], -4.0)
        self.assertEqual(result.loc[5, "ES"], -3.0)

    def test_robust_normalize_uses_rolling_median_and_iqr(self):
        result = robust_normalize(pd.Series([1.0, 2.0, 3.0, 4.0]), window=3)

        self.assertTrue(result.iloc[:2].isna().all())
        self.assertEqual(result.iloc[2], 1.0)
        self.assertEqual(result.iloc[3], 1.0)

    def test_robust_normalize_returns_nan_for_zero_iqr(self):
        result = robust_normalize(pd.Series([5.0, 5.0, 5.0]), window=3)

        self.assertTrue(np.isnan(result.iloc[2]))

    def test_beta_uses_date_join_and_preserves_legacy_covariance_variance_ratio(self):
        dates = pd.date_range("2025-01-01", periods=3)
        asset = pd.DataFrame({"Date": dates, "log_return": [1.0, 4.0, 6.0]})
        factor = pd.DataFrame({"Date": dates, "log_return": [1.0, 2.0, 3.0]})

        result = calc_beta(asset, factor, window=2)

        self.assertTrue(np.isnan(result.loc[0, "beta"]))
        self.assertTrue(np.isnan(result.loc[1, "beta"]))
        # origin/dev uses sample covariance divided by population variance.
        self.assertAlmostEqual(result.loc[2, "beta"], np.cov([1.0, 4.0], [1.0, 2.0])[0, 1] / np.var([1.0, 2.0]))

    def test_beta_forward_and_backward_fills_missing_factor_returns(self):
        dates = pd.date_range("2025-01-01", periods=4)
        asset = pd.DataFrame({"Date": dates, "log_return": [2.0, 4.0, 6.0, 8.0]})
        factor = pd.DataFrame({"Date": dates, "log_return": [np.nan, 2.0, 3.0, 4.0]})

        result = calc_beta(asset, factor, window=2)

        # Backfill makes the first two factor returns equal, so the first
        # computable beta is NaN; the next window yields this legacy result.
        self.assertTrue(np.isnan(result.loc[2, "beta"]))
        self.assertAlmostEqual(result.loc[3, "beta"], 4.0)

    def test_layer1_builders_return_expected_normalized_columns(self):
        dates = pd.date_range("2025-01-01", periods=8)
        prices = pd.DataFrame({"Date": dates, "Close": [100, 102, 99, 103, 105, 101, 106, 110]})
        factor = pd.DataFrame({"Date": dates, "Close": [50, 51, 52, 50, 53, 54, 52, 55]})
        asset_returns = calc_log_return(prices)
        factor_returns = calc_log_return(factor)

        volatility = build_volatility(prices.copy(), norm_window=2, vol_window=2)
        betas = build_beta(asset_returns, {"market": factor_returns}, beta_window=2, norm_window=2)

        self.assertEqual(volatility.columns.tolist(), ["Date", "sigma_norm", "ES_norm"])
        self.assertEqual(betas.columns.tolist(), ["Date", "beta_market_norm"])
        self.assertEqual(len(volatility), len(prices) - 1)
        self.assertEqual(len(betas), len(asset_returns))


if __name__ == "__main__":
    unittest.main()
