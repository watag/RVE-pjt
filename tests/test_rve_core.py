"""Offline smoke tests for the RVE Layer 1 core.

These tests use deterministic synthetic data and must not access Yahoo Finance or
other network services.
"""
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "layer1"))

from normalize import robust_normalize, normalize_dataframe
from beta import calc_beta
from volatility import calc_volatility, calc_es


class TestNormalize(unittest.TestCase):
    def test_robust_normalize_returns_series_with_expected_length(self):
        values = pd.Series(np.arange(1.0, 9.0))
        result = robust_normalize(values, window=4)
        self.assertEqual(len(result), len(values))
        self.assertTrue(result.iloc[:3].isna().all())
        self.assertTrue(np.isfinite(result.iloc[3:]).all())

    def test_constant_series_does_not_produce_infinite_values(self):
        result = robust_normalize(pd.Series([5.0] * 8), window=4)
        self.assertFalse(np.isinf(result.to_numpy()).any())
        self.assertTrue(result.isna().all())

    def test_normalize_dataframe_preserves_original_columns(self):
        frame = pd.DataFrame({"risk": np.arange(1.0, 7.0)})
        result = normalize_dataframe(frame, ["risk"], window=3)
        self.assertIn("risk", result.columns)
        self.assertIn("risk_norm", result.columns)
        self.assertEqual(len(result), len(frame))


class TestRiskCalculations(unittest.TestCase):
    @staticmethod
    def _returns_frame(returns):
        return pd.DataFrame({
            "Date": pd.date_range("2024-01-01", periods=len(returns), freq="D"),
            "log_return": returns,
        })

    def test_volatility_and_expected_shortfall_are_finite_after_warmup(self):
        returns = np.array([-0.03, 0.01, -0.02, 0.015, 0.005, -0.01, 0.02, -0.025])
        frame = self._returns_frame(returns)
        vol = calc_volatility(frame.copy(), window=4)
        es = calc_es(frame.copy(), window=4, alpha=0.25)
        self.assertTrue(np.isnan(vol["sigma"].iloc[:3]).all())
        self.assertTrue(np.isfinite(vol["sigma"].iloc[3:]).all())
        self.assertTrue(np.isnan(es["ES"].iloc[:4]).all())
        self.assertTrue(np.isfinite(es["ES"].iloc[4:]).all())
        self.assertTrue((es["ES"].dropna() <= 0).all())

    def test_beta_is_finite_for_nonconstant_factor_returns(self):
        factor_returns = np.array([0.01, -0.02, 0.015, 0.005, -0.01, 0.02, -0.025, 0.012, -0.008])
        asset_returns = 1.5 * factor_returns + np.array([0.001, -0.001] * 4 + [0.0])
        asset = self._returns_frame(asset_returns)
        factor = self._returns_frame(factor_returns)
        result = calc_beta(asset, factor, window=4)
        self.assertTrue(result["beta"].iloc[:4].isna().all())
        self.assertTrue(np.isfinite(result["beta"].iloc[4:]).all())

    def test_beta_is_nan_when_factor_variance_is_zero(self):
        returns = np.array([0.01, -0.01, 0.02, -0.02, 0.01, 0.0])
        asset = self._returns_frame(returns)
        factor = self._returns_frame(np.zeros(len(returns)))
        result = calc_beta(asset, factor, window=3)
        self.assertTrue(result["beta"].isna().all())


class TestRepositoryConfig(unittest.TestCase):
    def test_ticker_config_has_expected_structure(self):
        with (ROOT / "config" / "tickers.yaml").open(encoding="utf-8") as stream:
            config = yaml.safe_load(stream)
        self.assertIn("tickers", config)
        self.assertIsInstance(config["tickers"], list)
        self.assertTrue(config["tickers"])
        for ticker in config["tickers"]:
            self.assertTrue(ticker.get("symbol"))
            self.assertTrue(ticker.get("name"))


if __name__ == "__main__":
    unittest.main()
