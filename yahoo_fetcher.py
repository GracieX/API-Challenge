"""Fetches OHLCV + metadata from Yahoo Finance via yfinance."""

import logging
from datetime import datetime

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_ticker_history(
    ticker: str,
    start: str,
    end: str,
    interval: str = "1d",
) -> pd.DataFrame:
    """
    Download OHLCV history for a single ticker and return a normalised DataFrame.

    Columns returned:
        symbol, date, open, high, low, close, adj_close,
        volume, dividends, stock_splits, ingested_at
    """
    logger.info("Fetching %s  [%s → %s]  interval=%s", ticker, start, end, interval)

    t = yf.Ticker(ticker)
    raw: pd.DataFrame = t.history(
        start=start,
        end=end,
        interval=interval,
        auto_adjust=False,
        actions=True,
    )

    if raw.empty:
        logger.warning("No data returned for %s", ticker)
        return pd.DataFrame()

    raw = raw.reset_index()

    # yfinance returns the index as "Date" (date-only for 1d) or "Datetime"
    date_col = "Datetime" if "Datetime" in raw.columns else "Date"
    raw = raw.rename(columns={date_col: "date"})

    # Normalise column names to snake_case
    raw.columns = [c.lower().replace(" ", "_") for c in raw.columns]

    rename_map = {
        "adj_close": "adj_close",
        "stock_splits": "stock_splits",
    }
    raw = raw.rename(columns=rename_map)

    keep = ["date", "open", "high", "low", "close", "adj_close",
            "volume", "dividends", "stock_splits"]
    existing = [c for c in keep if c in raw.columns]
    df = raw[existing].copy()

    # Fill optional columns with zero if yfinance didn't include them
    for col in ("dividends", "stock_splits"):
        if col not in df.columns:
            df[col] = 0.0

    df.insert(0, "symbol", ticker.upper())
    df["ingested_at"] = datetime.utcnow().isoformat()

    # Ensure date is a plain date string (no timezone)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    # Cast numeric columns
    float_cols = ["open", "high", "low", "close", "adj_close", "dividends", "stock_splits"]
    for col in float_cols:
        if col in df.columns:
            df[col] = df[col].astype(float).round(6)

    df["volume"] = df["volume"].astype("Int64")

    logger.info("  -> %d rows for %s", len(df), ticker)
    return df


def fetch_all(
    tickers: list[str],
    start: str,
    end: str,
    interval: str = "1d",
) -> pd.DataFrame:
    """Fetch and concatenate history for multiple tickers."""
    frames = []
    for ticker in tickers:
        try:
            df = fetch_ticker_history(ticker, start, end, interval)
            if not df.empty:
                frames.append(df)
        except Exception as exc:
            logger.error("Failed to fetch %s: %s", ticker, exc)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    logger.info("Total rows fetched: %d", len(combined))
    return combined
