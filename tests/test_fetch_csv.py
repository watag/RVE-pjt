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
    _as_daily_frame,
    price_history_filename,
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
        self.assertFalse(calls[0][1]["auto_adjust"])
        self.assertEqual(saved["Date"].min(), pd.Timestamp("2020-01-03"))
        self.assertEqual(saved.loc[saved["Date"] == "2026-10-20", "Close"].iloc[0], 151)
        self.assertEqual(saved["Date"].duplicated().sum(), 0)

    def test_selects_configured_adjusted_price_without_close_fallback(self):
        dates = pd.to_datetime(["2025-01-03"])
        downloaded = pd.DataFrame(
            {"Close": [110.0], "Adj Close": [100.0]},
            index=pd.DatetimeIndex(dates, name="Date"),
        )

        selected = _as_daily_frame(downloaded, "ETF", price_field="Adj Close")

        self.assertEqual(selected["Close"].tolist(), [100.0])
        self.assertEqual(price_history_filename("ETF", "Adj Close"), "ETF.Adj_Close.csv")

    def test_adjusted_history_does_not_overwrite_legacy_close_history(self):
        as_of = pd.Timestamp("2026-10-24")
        with tempfile.TemporaryDirectory() as temp_dir:
            close_path = Path(temp_dir) / "ETF.csv"
            close_path.write_text("Date,Close\n2020-01-03,100\n", encoding="utf-8")
            before = close_path.read_bytes()

            def fake_downloader(symbol, **kwargs):
                self.assertFalse(kwargs["auto_adjust"])
                return pd.DataFrame(
                    {"Close": [110.0], "Adj Close": [105.0]},
                    index=pd.DatetimeIndex([as_of], name="Date"),
                )

            adjusted_path = fetch_and_save(
                "ETF", output_dir=temp_dir, downloader=fake_downloader,
                as_of=as_of, price_field="Adj Close",
            )

            self.assertEqual(adjusted_path.name, "ETF.Adj_Close.csv")
            self.assertEqual(close_path.read_bytes(), before)

    def test_empty_download_fails_without_rewriting_existing_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "7203.T.csv"
            existing = pd.DataFrame(
                {"Date": pd.to_datetime(["2020-01-03"]), "Close": [80.0]}
            )
            existing.to_csv(path, index=False)
            before = path.read_bytes()

            def empty_downloader(symbol, **kwargs):
                return pd.DataFrame(columns=["Close"])

            with self.assertRaisesRegex(ValueError, "existing history was not changed"):
                fetch_and_save(
                    "7203.T", output_dir=temp_dir,
                    downloader=empty_downloader, as_of="2026-10-24",
                )

            self.assertEqual(path.read_bytes(), before)

    def test_duplicate_dates_within_one_history_are_rejected(self):
        duplicate = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2025-01-03", "2025-01-03"]),
                "Close": [100.0, 101.0],
            }
        )

        with self.assertRaisesRegex(ValueError, "duplicate dates"):
            merge_price_history(duplicate, pd.DataFrame(columns=["Date", "Close"]))

    def test_invalid_dates_are_not_silently_dropped(self):
        invalid = pd.DataFrame({"Date": ["not-a-date"], "Close": [100.0]})

        with self.assertRaisesRegex(ValueError, "invalid dates"):
            merge_price_history(invalid, pd.DataFrame(columns=["Date", "Close"]))

    def test_missing_nonfinite_and_nonpositive_prices_are_rejected(self):
        for value in (None, float("nan"), float("inf"), 0.0, -1.0):
            with self.subTest(value=value):
                invalid = pd.DataFrame(
                    {"Date": pd.to_datetime(["2025-01-03"]), "Close": [value]}
                )
                with self.assertRaisesRegex(ValueError, "prices"):
                    merge_price_history(invalid, pd.DataFrame(columns=["Date", "Close"]))

    def test_invalid_download_does_not_rewrite_existing_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "7203.T.csv"
            pd.DataFrame(
                {"Date": pd.to_datetime(["2020-01-03"]), "Close": [80.0]}
            ).to_csv(path, index=False)
            before = path.read_bytes()

            def invalid_downloader(symbol, **kwargs):
                return pd.DataFrame(
                    {"Close": [0.0]},
                    index=pd.DatetimeIndex(["2026-10-20"], name="Date"),
                )

            with self.assertRaisesRegex(ValueError, "non-positive prices"):
                fetch_and_save(
                    "7203.T", output_dir=temp_dir,
                    downloader=invalid_downloader, as_of="2026-10-24",
                )

            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
