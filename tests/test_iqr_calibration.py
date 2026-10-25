"""Tests for empirical normalization-threshold calibration helpers."""

import sys
import unittest
from pathlib import Path

import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from calibrate_iqr_thresholds import positive_historical_iqrs  # noqa: E402


class IqrCalibrationTests(unittest.TestCase):
    def test_uses_previous_52_values_and_excludes_current_value(self):
        values = np.append(np.arange(1.0, 53.0), 1_000_000.0)

        spreads = positive_historical_iqrs(values)

        self.assertEqual(len(spreads), 1)
        self.assertAlmostEqual(spreads[0], 25.5)

    def test_zero_iqr_is_excluded_from_positive_calibration_samples(self):
        spreads = positive_historical_iqrs(np.ones(53))

        self.assertEqual(spreads, [])

    def test_incomplete_history_window_is_excluded(self):
        values = np.arange(54.0)
        values[10] = np.nan

        spreads = positive_historical_iqrs(values)

        self.assertEqual(spreads, [])

    def test_runtime_configuration_has_all_empirically_calibrated_metric_floors(self):
        with (ROOT / "config" / "tickers.yaml").open(encoding="utf-8") as stream:
            config = yaml.safe_load(stream)
        thresholds = config["normalization"]["iqr_thresholds"]

        self.assertEqual(
            set(thresholds),
            {
                "sigma", "ES", "beta_gold", "beta_us_equity",
                "beta_japan_equity", "beta_us_treasury", "beta_japan_bond",
            },
        )
        self.assertTrue(all(np.isfinite(value) and value >= 0 for value in thresholds.values()))
        self.assertTrue((ROOT / "reports" / "rve-v1.0-iqr-calibration.md").is_file())


if __name__ == "__main__":
    unittest.main()
