import os
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            "Copy .env.example to .env and fill in your values."
        )
    return value


class Config:
    GCP_PROJECT_ID: str = _require("GCP_PROJECT_ID")
    BQ_DATASET_ID: str = os.getenv("BQ_DATASET_ID", "stock_data")
    BQ_TABLE_ID: str = os.getenv("BQ_TABLE_ID", "yahoo_prices")

    _default_end = date.today().isoformat()
    _default_start = (date.today() - timedelta(days=365)).isoformat()

    TICKERS: list[str] = [
        t.strip().upper()
        for t in os.getenv("STOCK_TICKERS", "AAPL,MSFT,GOOGL,AMZN,TSLA").split(",")
        if t.strip()
    ]
    START_DATE: str = os.getenv("START_DATE", _default_start)
    END_DATE: str = os.getenv("END_DATE", _default_end)
    DATA_INTERVAL: str = os.getenv("DATA_INTERVAL", "1d")

    @property
    def bq_table_ref(self) -> str:
        return f"{self.GCP_PROJECT_ID}.{self.BQ_DATASET_ID}.{self.BQ_TABLE_ID}"
