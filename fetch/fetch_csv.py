"""Incrementally download and retain daily close history from Yahoo Finance."""

from collections.abc import Callable
from pathlib import Path

import pandas as pd


MIN_NORMALIZED_ES_RETURN_WEEKS = 208
BOOTSTRAP_BUFFER_WEEKS = 52
BOOTSTRAP_HISTORY_WEEKS = (
    MIN_NORMALIZED_ES_RETURN_WEEKS + BOOTSTRAP_BUFFER_WEEKS
)
RECENT_OVERLAP_DAYS = 7


def load_config(path: str | Path) -> dict:
    import yaml

    with Path(path).open("r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def _as_daily_frame(downloaded: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Select the downloaded Close column and return the legacy CSV schema."""
    if downloaded is None or downloaded.empty:
        return pd.DataFrame(columns=["Date", "Close"])

    frame = downloaded.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        close_columns = [
            column
            for column in frame.columns
            if "Close" in column and (symbol in column or len(frame.columns) == 1)
        ]
        if not close_columns:
            close_columns = [column for column in frame.columns if "Close" in column]
        if not close_columns:
            raise ValueError(f"Downloaded data for {symbol} has no Close column")
        frame = frame[[close_columns[0]]]
        frame.columns = ["Close"]
    elif "Close" in frame.columns:
        frame = frame[["Close"]]
    else:
        raise ValueError(f"Downloaded data for {symbol} has no Close column")

    frame = frame.reset_index()
    if "Date" not in frame.columns:
        date_column = next(
            (column for column in ("Datetime", "index") if column in frame.columns),
            None,
        )
        if date_column is None:
            raise ValueError(f"Downloaded data for {symbol} has no date index")
        frame = frame.rename(columns={date_column: "Date"})
    return frame[["Date", "Close"]]


def merge_price_history(
    existing: pd.DataFrame | None, downloaded: pd.DataFrame
) -> pd.DataFrame:
    """Merge downloaded rows without truncating history; new overlaps win."""
    frames = []
    for candidate in (existing, downloaded):
        if candidate is None or candidate.empty:
            continue
        if "Date" not in candidate.columns or "Close" not in candidate.columns:
            raise ValueError("Price history must contain Date and Close columns")
        normalized = candidate[["Date", "Close"]].copy()
        normalized["Date"] = pd.to_datetime(normalized["Date"], errors="coerce")
        normalized["Close"] = pd.to_numeric(normalized["Close"], errors="coerce")
        normalized = normalized.dropna(subset=["Date"])
        frames.append(normalized)

    if not frames:
        return pd.DataFrame(columns=["Date", "Close"])

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.drop_duplicates(subset=["Date"], keep="last")
    return merged.sort_values("Date", kind="stable").reset_index(drop=True)


def choose_download_start(
    existing: pd.DataFrame | None, as_of: str | pd.Timestamp
) -> pd.Timestamp:
    """Backfill the required warm-up history, then update with a short overlap."""
    today = pd.Timestamp(as_of).normalize()
    bootstrap_start = today - pd.Timedelta(weeks=BOOTSTRAP_HISTORY_WEEKS)

    if existing is None or existing.empty or "Date" not in existing.columns:
        return bootstrap_start

    dates = pd.to_datetime(existing["Date"], errors="coerce").dropna()
    if dates.empty or dates.min().normalize() > bootstrap_start:
        return bootstrap_start

    return max(
        dates.max().normalize() - pd.Timedelta(days=RECENT_OVERLAP_DAYS),
        bootstrap_start,
    )


def fetch_and_save(
    symbol: str,
    output_dir: str | Path | None = None,
    downloader: Callable | None = None,
    as_of: str | pd.Timestamp | None = None,
) -> Path:
    """Download a backfill or recent delta and atomically merge it into history."""
    repository_root = Path(__file__).resolve().parents[1]
    destination = Path(output_dir) if output_dir is not None else repository_root / "data" / "processed"
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"{symbol}.csv"
    today = pd.Timestamp(as_of).normalize() if as_of is not None else pd.Timestamp.today().normalize()

    if path.exists():
        existing = pd.read_csv(path, parse_dates=["Date"])
    else:
        existing = pd.DataFrame(columns=["Date", "Close"])

    start = choose_download_start(existing, today)
    end = today + pd.Timedelta(days=1)  # Yahoo Finance treats end as exclusive.
    if downloader is None:
        import yfinance as yf

        downloader = yf.download
    download = downloader(
        symbol,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        progress=False,
    )
    fresh = _as_daily_frame(download, symbol)
    merged = merge_price_history(existing, fresh)

    temporary_path = path.with_name(f".{path.name}.tmp")
    merged.to_csv(temporary_path, index=False)
    temporary_path.replace(path)
    return path


def main() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    config = load_config(repository_root / "config" / "tickers.yaml")
    output_dir = repository_root / "data" / "processed"

    for ticker in config["tickers"]:
        fetch_and_save(ticker["symbol"], output_dir=output_dir)


if __name__ == "__main__":
    main()
