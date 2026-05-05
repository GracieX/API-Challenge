"""BigQuery client — fetches historical subscription data, with demo-mode fallback."""

import logging
import numpy as np
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)


def fetch_historical_data(sql: str, project_id: str) -> pd.DataFrame:
    from google.cloud import bigquery

    client = bigquery.Client(project=project_id)
    logger.info("Executing BQ query:\n%s", sql)
    df = client.query(sql).to_dataframe()
    df["month"] = pd.to_datetime(df["month"])
    df["customer_count"] = df["customer_count"].astype(int)
    df["customer_type"] = df["customer_type"].str.lower().str.strip()
    df["product_line"] = df["product_line"].str.lower().str.strip()
    return df


def get_demo_data() -> pd.DataFrame:
    """
    Generates 5 years of synthetic monthly subscription data matching the schema:
        month (date), customer_type (new|existing), product_line (classic|super), customer_count (int)
    """
    rng = np.random.default_rng(42)
    end = date.today().replace(day=1)
    start = end - relativedelta(years=5)

    months = []
    cur = start
    while cur <= end:
        months.append(cur)
        cur += relativedelta(months=1)

    rows = []
    # Realistic base counts with trend + seasonality + noise
    for i, m in enumerate(months):
        trend = i * 0.8
        season = 300 * np.sin(2 * np.pi * i / 12)

        for product, base_new, base_exist in [
            ("classic", 800, 12_000),
            ("super",   500,  7_500),
        ]:
            new_count = int(max(50, base_new + trend * 1.2 + season * 0.4 + rng.normal(0, 80)))
            exist_count = int(max(500, base_exist + trend * 4 + season * 0.8 + rng.normal(0, 200)))
            rows.append({"month": pd.Timestamp(m), "customer_type": "new",      "product_line": product, "customer_count": new_count})
            rows.append({"month": pd.Timestamp(m), "customer_type": "existing", "product_line": product, "customer_count": exist_count})

    return pd.DataFrame(rows)
