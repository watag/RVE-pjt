"""Tests for incremental daily-price acquisition and history retention."""

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


FETCH_DIR = Path(__file__).resolve().parents[1] / "fetch"
sys.path.insert(0, str(FETCH_DIR))

from fetch_csv import (  # noqa: E402
    BOOTSTRAP_HISTORY_WEEKS,
    choose_download_start,
    fetch_and_save,
    merge_price_history,
)


class IncrementalFetchTests(unittest.TestCase):
    def test_first_fetch_backfills_five_year_warmup(self):
        as_of = pd.Timestamp("2026-10-24")

        start = choose_download_start(None, as_of)

        self.assertEqual(start, as_of - pd.Timedelta(weeks=BOOTSTRAP_HISTORY_WEEKS))

    def test_short_existing_history_triggers_backfill(self):
        as_of = pd.Timestamp("2026-10-24")
        existing = pd.DataFrame(
            {"Date": pd.to_datetime(["2024-01-05", "2026-10-16"]), "Close": [100, 150]}
        )

        start = choose_download_start(existing, as_of)

        self.assertEqual(start, as_of - pd.Timedelta(weeks=BOOTSTRAP_HISTORY_WEEKS))

    def test_mature_history_updates_from_recent_overlap(self):
        as_of = pd.Timestamp("2026-10-24")
        existing = pd.DataFrame(
            {"Date": pd.to_datetime(["2019-01-04", "2026-10-20"]), "Close": [80, 150]}
        )

        start = choose_download_start(existing, as_of)

        self.assertEqual(start, pd.Timestamp("2026-10-13"))

    def test_merge_preserves_history_and_replaces_overlapping_dates(self):
        existing = pd.DataFrame(
            {"Date": pd.to_datetime(["2020-01-03", "2026-10-20"]), "Close": [80, 150]}
        )
        downloaded = pd.DataFrame(
            {"Date": pd.to_datetime(["2026-10-20", "2026-10-21"]), "Close": [151, 152]}
        )

        merged = merge_price_history(existing, downloaded)

        self.assertEqual(merged["Date"].tolist(), list(pd.to_datetime([
            "2020-01-03", "2026-10-20", "2026-10-21"
        ])))
        self.assertEqual(merged["Close"].tolist(), [80, 151, 152])

    def test_fetch_saves_delta_without_dropping_older_rows(self):
        as_of = pd.Timestamp("2026-10-24")
        calls = []

        def fake_downloader(symbol, **kwargs):
            calls.append((symbol, kwargs))
            dates = pd.to_datetime(["2026-10-20", "2026-10-21"])
            return pd.DataFrame({"Close": [151, 152]}, index=pd.DatetimeIndex(dates, name="Date"))

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "7203.T.csv"
            pd.DataFrame(
                {"Date": pd.to_datetime(["2020-01-03", "2026-10-20"]), "Close": [80, 150]}
            ).to_csv(path, index=False)

            saved_path = fetch_and_save(
                "7203.T", output_dir=temp_dir, downloader=fake_downloader, as_of=as_of
            )

            saved = pd.read_csv(saved_path, parse_dates=["Date"])

        self.assertEqual(calls[0][0], "7203.T")
        self.assertEqual(calls[0][1]["start"], "2026-10-13")
        self.assertEqual(calls[0][1]["end"], "2026-10-25")
        self.assertFalse(calls[0][1]["progress"])
        self.assertEqual(saved["Date"].min(), pd.Timestamp("2020-01-03"))
        self.assertEqual(saved.loc[saved["Date"] == "2026-10-20", "Close"].iloc[0], 151)
        self.assertEqual(saved["Date"].duplicated().sum(), 0)


if __name__ == "__main__":
    unittest.main()
