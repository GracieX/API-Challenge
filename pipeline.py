"""
Yahoo Finance → BigQuery pipeline
----------------------------------
Usage:
    python pipeline.py                          # use settings from .env
    python pipeline.py --tickers AAPL MSFT NVDA
    python pipeline.py --start 2023-01-01 --end 2024-01-01
    python pipeline.py --mode truncate          # replace instead of append
"""

import argparse
import logging
import sys

from config import Config
from yahoo_fetcher import fetch_all
from bigquery_loader import get_client, ensure_dataset, ensure_table, load_dataframe

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Yahoo Finance → BigQuery pipeline")
    parser.add_argument(
        "--tickers", nargs="+", metavar="TICKER",
        help="Override STOCK_TICKERS from .env (e.g. --tickers AAPL MSFT)",
    )
    parser.add_argument(
        "--start", metavar="YYYY-MM-DD",
        help="Override START_DATE from .env",
    )
    parser.add_argument(
        "--end", metavar="YYYY-MM-DD",
        help="Override END_DATE from .env",
    )
    parser.add_argument(
        "--interval", choices=["1d", "1wk", "1mo"],
        help="Override DATA_INTERVAL from .env",
    )
    parser.add_argument(
        "--mode", choices=["append", "truncate"], default="append",
        help="Write mode: append (default) or truncate",
    )
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    cfg = Config()

    tickers  = [t.upper() for t in args.tickers]  if args.tickers  else cfg.TICKERS
    start    = args.start    or cfg.START_DATE
    end      = args.end      or cfg.END_DATE
    interval = args.interval or cfg.DATA_INTERVAL
    write_disposition = (
        "WRITE_TRUNCATE" if args.mode == "truncate" else "WRITE_APPEND"
    )

    logger.info("=== Yahoo Finance → BigQuery pipeline ===")
    logger.info("  Tickers  : %s", ", ".join(tickers))
    logger.info("  Date range: %s → %s", start, end)
    logger.info("  Interval : %s", interval)
    logger.info("  Destination: %s.%s.%s", cfg.GCP_PROJECT_ID, cfg.BQ_DATASET_ID, cfg.BQ_TABLE_ID)
    logger.info("  Write mode: %s", write_disposition)

    # 1. Fetch data from Yahoo Finance
    df = fetch_all(tickers, start=start, end=end, interval=interval)
    if df.empty:
        logger.error("No data fetched. Aborting.")
        return 1

    logger.info("Fetched %d total rows across %d tickers.", len(df), df["symbol"].nunique())

    # 2. Set up BigQuery resources
    client = get_client(cfg.GCP_PROJECT_ID)
    ensure_dataset(client, cfg.BQ_DATASET_ID)
    ensure_table(client, cfg.BQ_DATASET_ID, cfg.BQ_TABLE_ID)

    # 3. Load into BigQuery
    rows_loaded = load_dataframe(
        client, df,
        dataset_id=cfg.BQ_DATASET_ID,
        table_id=cfg.BQ_TABLE_ID,
        write_disposition=write_disposition,
    )

    logger.info("=== Pipeline complete. %d rows loaded. ===", rows_loaded)
    return 0


if __name__ == "__main__":
    sys.exit(run(parse_args()))
