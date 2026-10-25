"""Tests for the weekly RVE v1.0 risk-vector calculation core."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


LAYER1_DIR = Path(__file__).resolve().parents[1] / "layer1"
sys.path.insert(0, str(LAYER1_DIR))

from risk_metrics import ANCHORS, METRICS, calculate_risk_vector  # noqa: E402


def make_weekly_returns(length=220):
    step = np.arange(length, dtype=float)
    anchors = pd.DataFrame(
        {
            "gold": 0.012 * np.sin(step * 0.13) + 0.002 * np.cos(step * 0.031),
            "us_equity": 0.016 * np.sin(step * 0.17) + 0.004 * np.cos(step * 0.053),
            "japan_equity": 0.009 * np.cos(step * 0.11) + 0.003 * np.sin(step * 0.029),
            "us_treasury": 0.006 * np.sin(step * 0.07) - 0.002 * np.cos(step * 0.041),
            "japan_bond": 0.003 * np.cos(step * 0.09) + 0.001 * np.sin(step * 0.023),
        },
        index=pd.date_range("2020-01-03", periods=length, freq="W-FRI"),
    )
    asset = pd.Series(
        0.15 * anchors["gold"]
        + 0.5 * anchors["us_equity"]
        + 0.2 * anchors["japan_equity"]
        - 0.25 * anchors["us_treasury"]
        + 0.1 * anchors["japan_bond"]
        + 0.004 * np.sin(step * 0.37),
        index=anchors.index,
        name="asset",
    )
    return asset, anchors


def thresholds(value=0.0):
    return {metric: value for metric in METRICS}


class WeeklyRiskVectorTests(unittest.TestCase):
    def test_calculates_annualized_sigma_es_and_five_anchor_betas(self):
        asset, anchors = make_weekly_returns()

        result = calculate_risk_vector(asset, anchors, thresholds(1e-12))
        latest_asset = asset.to_numpy()[-52:]
        latest_losses = -asset.to_numpy()[-156:]

        self.assertAlmostEqual(
            result["sigma"]["value"], np.std(latest_asset, ddof=1) * np.sqrt(52)
        )
        self.assertAlmostEqual(
            result["ES"]["value"], np.sort(latest_losses)[-8:].mean()
        )
        self.assertEqual(
            [name for name in result if name.startswith("beta_")],
            [f"beta_{name}" for name in ANCHORS],
        )
        for anchor_name in ANCHORS:
            expected = np.cov(
                latest_asset,
                anchors[anchor_name].to_numpy()[-52:],
                ddof=1,
            )[0, 1] / np.var(anchors[anchor_name].to_numpy()[-52:], ddof=1)
            self.assertAlmostEqual(result[f"beta_{anchor_name}"]["value"], expected)
            self.assertEqual(result[f"beta_{anchor_name}"]["status"], "ok")

    def test_reports_insufficient_history_at_metric_boundaries(self):
        asset_51, anchors_51 = make_weekly_returns(51)
        result_51 = calculate_risk_vector(asset_51, anchors_51, thresholds())
        self.assertEqual(result_51["sigma"]["status"], "insufficient_history")
        self.assertEqual(result_51["beta_gold"]["status"], "insufficient_history")

        asset_155, anchors_155 = make_weekly_returns(155)
        result_155 = calculate_risk_vector(asset_155, anchors_155, thresholds())
        self.assertEqual(result_155["ES"]["status"], "insufficient_history")
        self.assertEqual(result_155["sigma"]["status"], "ok")

    def test_missing_week_is_not_filled_with_zero(self):
        asset, anchors = make_weekly_returns()
        asset.iloc[-1] = np.nan
        anchors.loc[anchors.index[-1], "gold"] = np.nan

        result = calculate_risk_vector(asset, anchors, thresholds())

        self.assertEqual(result["sigma"]["status"], "missing_price")
        self.assertEqual(result["ES"]["status"], "missing_price")
        self.assertEqual(result["beta_gold"]["status"], "missing_price")

    def test_missing_fx_status_is_not_collapsed_into_missing_price(self):
        asset, anchors = make_weekly_returns()
        statuses = pd.Series("ok", index=asset.index)
        statuses.iloc[-1] = "missing_fx"
        asset.iloc[-1] = np.nan

        result = calculate_risk_vector(
            asset, anchors, thresholds(), asset_statuses=statuses
        )

        self.assertEqual(result["sigma"]["status"], "missing_fx")
        self.assertEqual(result["ES"]["status"], "missing_fx")

    def test_infinite_return_is_invalid_price(self):
        asset, anchors = make_weekly_returns()
        asset.iloc[-1] = np.inf

        result = calculate_risk_vector(asset, anchors, thresholds())

        self.assertEqual(result["sigma"]["status"], "invalid_price")

    def test_missing_fx_on_one_anchor_does_not_hide_other_metrics(self):
        asset, anchors = make_weekly_returns()
        anchor_status = pd.DataFrame("ok", index=anchors.index, columns=anchors.columns)
        anchor_status.loc[anchors.index[-1], "us_equity"] = "missing_fx"
        anchors.loc[anchors.index[-1], "us_equity"] = np.nan

        result = calculate_risk_vector(
            asset, anchors, thresholds(), anchor_statuses=anchor_status
        )

        self.assertEqual(result["sigma"]["status"], "ok")
        self.assertEqual(result["beta_us_equity"]["status"], "missing_fx")
        self.assertEqual(result["beta_gold"]["status"], "ok")

    def test_zero_variance_anchor_has_its_own_status(self):
        asset, anchors = make_weekly_returns()
        anchors["gold"] = 0.01

        result = calculate_risk_vector(asset, anchors, thresholds())

        self.assertEqual(result["beta_gold"]["value"], None)
        self.assertEqual(result["beta_gold"]["status"], "zero_variance")
        self.assertEqual(result["sigma"]["status"], "ok")

    def test_normalization_uses_previous_52_metric_values(self):
        asset, anchors = make_weekly_returns()
        result = calculate_risk_vector(asset, anchors, thresholds(1e-12))
        returns = asset.to_numpy()
        prior_sigma = [
            np.std(returns[position - 51 : position + 1], ddof=1) * np.sqrt(52)
            for position in range(len(returns) - 53, len(returns) - 1)
        ]
        expected = (
            result["sigma"]["value"] - np.median(prior_sigma)
        ) / (np.quantile(prior_sigma, 0.75) - np.quantile(prior_sigma, 0.25))

        self.assertAlmostEqual(result["sigma"]["normalized"], expected)
        self.assertEqual(result["sigma"]["normalization_status"], "ok")

    def test_iqr_threshold_equality_and_missing_configuration(self):
        asset, anchors = make_weekly_returns()
        returns = asset.to_numpy()
        prior_sigma = [
            np.std(returns[position - 51 : position + 1], ddof=1) * np.sqrt(52)
            for position in range(len(returns) - 53, len(returns) - 1)
        ]
        sigma_iqr = np.quantile(prior_sigma, 0.75) - np.quantile(prior_sigma, 0.25)

        equal_thresholds = thresholds(0.0)
        equal_thresholds["sigma"] = sigma_iqr
        equal_result = calculate_risk_vector(asset, anchors, equal_thresholds)
        self.assertEqual(
            equal_result["sigma"]["normalization_status"], "iqr_below_threshold"
        )
        self.assertIsNone(equal_result["sigma"]["normalized"])

        missing_result = calculate_risk_vector(asset, anchors)
        self.assertEqual(missing_result["sigma"]["status"], "ok")
        self.assertEqual(
            missing_result["sigma"]["normalization_status"], "configuration_error"
        )

    def test_missing_anchor_configuration_does_not_hide_other_metrics(self):
        asset, anchors = make_weekly_returns()
        result = calculate_risk_vector(asset, anchors.drop(columns="gold"), thresholds())

        self.assertEqual(result["sigma"]["status"], "ok")
        self.assertEqual(result["beta_gold"]["status"], "configuration_error")
        self.assertEqual(result["beta_us_equity"]["status"], "ok")

    def test_malformed_anchor_dates_do_not_hide_asset_only_metrics(self):
        asset, anchors = make_weekly_returns()
        malformed = anchors.copy()
        malformed.index = malformed.index.where(
            np.arange(len(malformed)) != 1, malformed.index[0]
        )

        result = calculate_risk_vector(asset, malformed, thresholds())

        self.assertEqual(result["sigma"]["status"], "ok")
        self.assertEqual(result["ES"]["status"], "ok")
        self.assertEqual(result["beta_gold"]["status"], "configuration_error")


if __name__ == "__main__":
    unittest.main()
