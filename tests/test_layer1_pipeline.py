"""Integration tests for the v1.0 daily-price-to-vector entry point."""

import sys
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


LAYER1_DIR = Path(__file__).resolve().parents[1] / "layer1"
sys.path.insert(0, str(LAYER1_DIR))

from layer1_vector import build_risk_vector_from_daily_prices  # noqa: E402
from layer1_vector import main as run_layer1_main  # noqa: E402
from risk_metrics import ANCHORS  # noqa: E402


def prices_from_returns(dates, returns):
    close = 100.0 * np.cumprod(np.r_[1.0, 1.0 + returns])
    return pd.DataFrame({"Date": dates, "Close": close})


class Layer1PipelineTests(unittest.TestCase):
    def test_daily_prices_produce_specification_based_weekly_vector(self):
        count = 220
        dates = pd.date_range("2021-01-01", periods=count + 1, freq="W-FRI")
        step = np.arange(count, dtype=float)
        anchor_returns = {
            "gold": 0.012 * np.sin(step * 0.13) + 0.002 * np.cos(step * 0.031),
            "us_equity": 0.016 * np.sin(step * 0.17) + 0.004 * np.cos(step * 0.053),
            "japan_equity": 0.009 * np.cos(step * 0.11) + 0.003 * np.sin(step * 0.029),
            "us_treasury": 0.006 * np.sin(step * 0.07) - 0.002 * np.cos(step * 0.041),
            "japan_bond": 0.003 * np.cos(step * 0.09) + 0.001 * np.sin(step * 0.023),
        }
        asset_returns = (
            0.15 * anchor_returns["gold"]
            + 0.5 * anchor_returns["us_equity"]
            + 0.2 * anchor_returns["japan_equity"]
            - 0.25 * anchor_returns["us_treasury"]
            + 0.1 * anchor_returns["japan_bond"]
            + 0.004 * np.sin(step * 0.37)
        )
        asset_prices = prices_from_returns(dates, asset_returns)
        anchor_prices = {
            name: prices_from_returns(dates, values)
            for name, values in anchor_returns.items()
        }

        result = build_risk_vector_from_daily_prices(
            asset_prices, anchor_prices, {metric: 0.0 for metric in ["sigma", "ES", *(f"beta_{name}" for name in ANCHORS)]}
        )

        self.assertAlmostEqual(
            result["sigma"]["value"], np.std(asset_returns[-52:], ddof=1) * np.sqrt(52)
        )
        self.assertAlmostEqual(
            result["ES"]["value"], np.sort(-asset_returns[-156:])[-8:].mean()
        )
        for name in ANCHORS:
            expected_beta = np.cov(
                asset_returns[-52:], anchor_returns[name][-52:], ddof=1
            )[0, 1] / np.var(anchor_returns[name][-52:], ddof=1)
            self.assertAlmostEqual(result[f"beta_{name}"]["value"], expected_beta)
            self.assertEqual(result[f"beta_{name}"]["status"], "ok")

    def test_missing_anchor_keeps_other_daily_price_metrics_available(self):
        count = 220
        dates = pd.date_range("2021-01-01", periods=count + 1, freq="W-FRI")
        step = np.arange(count, dtype=float)
        anchors = {
            name: 0.01 * np.sin(step * (0.03 + position * 0.01))
            for position, name in enumerate(ANCHORS)
        }
        asset = 0.5 * anchors["us_equity"] + 0.004 * np.cos(step * 0.17)
        anchor_prices = {
            name: prices_from_returns(dates, values)
            for name, values in anchors.items()
            if name != "gold"
        }

        result = build_risk_vector_from_daily_prices(
            prices_from_returns(dates, asset),
            anchor_prices,
            {metric: 0.0 for metric in ["sigma", "ES", *(f"beta_{name}" for name in ANCHORS)]},
        )

        self.assertEqual(result["sigma"]["status"], "ok")
        self.assertEqual(result["ES"]["status"], "ok")
        self.assertEqual(result["beta_gold"]["status"], "configuration_error")
        self.assertEqual(result["beta_us_equity"]["status"], "ok")

    def test_main_writes_vector_from_jpy_converted_prices_and_five_anchors(self):
        import yaml

        count = 220
        dates = pd.date_range("2021-01-01", periods=count + 1, freq="W-FRI")
        step = np.arange(count, dtype=float)
        fx_returns = 0.002 * np.sin(step * 0.19) + 0.0004
        us_returns = 0.012 * np.cos(step * 0.13) + 0.001 * np.sin(step * 0.031)
        asset_returns = 0.4 * us_returns + 0.3 * fx_returns + 0.003 * np.sin(step * 0.17)
        prices = {
            "7203.T": prices_from_returns(dates, asset_returns),
            "1540.T": prices_from_returns(dates, 0.008 * np.sin(step * 0.11)),
            "1306.T": prices_from_returns(dates, 0.009 * np.cos(step * 0.09)),
            "^GSPC": prices_from_returns(dates, us_returns),
            "TLT": prices_from_returns(dates, 0.004 * np.sin(step * 0.07)),
            "2510.T": prices_from_returns(dates, 0.002 * np.cos(step * 0.05)),
            "JPY=X": prices_from_returns(dates, fx_returns),
        }
        tickers = [
            {"symbol": "7203.T", "currency": "JPY", "role": "asset"},
            {"symbol": "1540.T", "currency": "JPY", "anchor_key": "gold"},
            {"symbol": "1306.T", "currency": "JPY", "anchor_key": "japan_equity"},
            {"symbol": "^GSPC", "currency": "USD", "anchor_key": "us_equity"},
            {"symbol": "TLT", "currency": "USD", "anchor_key": "us_treasury"},
            {"symbol": "2510.T", "currency": "JPY", "anchor_key": "japan_bond"},
            {"symbol": "JPY=X", "currency": "JPY per USD", "role": "fx"},
        ]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir = root / "processed"
            data_dir.mkdir()
            output_dir = root / "layer1"
            config_path = root / "tickers.yaml"
            config_path.write_text(
                yaml.safe_dump(
                    {
                        "tickers": tickers,
                        "normalization": {"iqr_thresholds": {}},
                        "portfolio": {
                            "mode": "scenario",
                            "current_weights": {"7203.T": 1.0},
                        },
                    }
                ),
                encoding="utf-8",
            )
            for symbol, frame in prices.items():
                frame.to_csv(data_dir / f"{symbol}.csv", index=False)

            run_layer1_main(data_dir, output_dir, config_path)
            output_path = output_dir / "7203.T_risk_vector.json"
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["fx_alignment"], "exact_calendar_date_no_fill")
        self.assertEqual(payload["portfolio_mode"], "scenario")
        self.assertEqual(payload["portfolio"]["analysis_mode"], "scenario")
        self.assertAlmostEqual(
            payload["portfolio"]["sigma"]["value"], payload["asset"]["sigma"]["value"]
        )
        self.assertEqual(payload["asset"]["beta_us_equity"]["status"], "ok")
        self.assertNotIn("beta_usd_jpy", payload["asset"])
        converted_weekly = np.diff(
            prices["^GSPC"]["Close"].to_numpy() * prices["JPY=X"]["Close"].to_numpy()
        ) / (prices["^GSPC"]["Close"].to_numpy() * prices["JPY=X"]["Close"].to_numpy())[:-1]
        expected_beta = np.cov(asset_returns[-52:], converted_weekly[-52:], ddof=1)[0, 1] / np.var(
            converted_weekly[-52:], ddof=1
        )
        self.assertAlmostEqual(payload["asset"]["beta_us_equity"]["value"], expected_beta)


if __name__ == "__main__":
    unittest.main()
