"""Creates the BigQuery dataset/table if needed and loads a DataFrame into it."""

import logging

import pandas as pd
from google.cloud import bigquery
from google.cloud.exceptions import Conflict

logger = logging.getLogger(__name__)

# Schema mirrors the columns produced by yahoo_fetcher.fetch_all()
TABLE_SCHEMA = [
    bigquery.SchemaField("symbol",       "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("date",         "DATE",      mode="REQUIRED"),
    bigquery.SchemaField("open",         "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("high",         "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("low",          "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("close",        "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("adj_close",    "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("volume",       "INT64",     mode="NULLABLE"),
    bigquery.SchemaField("dividends",    "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("stock_splits", "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("ingested_at",  "TIMESTAMP", mode="NULLABLE"),
]


def get_client(project_id: str) -> bigquery.Client:
    return bigquery.Client(project=project_id)


def ensure_dataset(client: bigquery.Client, dataset_id: str) -> None:
    """Create the dataset if it doesn't already exist."""
    ref = bigquery.DatasetReference(client.project, dataset_id)
    dataset = bigquery.Dataset(ref)
    dataset.location = "US"
    try:
        client.create_dataset(dataset)
        logger.info("Created dataset %s.%s", client.project, dataset_id)
    except Conflict:
        logger.info("Dataset %s.%s already exists", client.project, dataset_id)


def ensure_table(
    client: bigquery.Client,
    dataset_id: str,
    table_id: str,
    write_disposition: str = "WRITE_APPEND",
) -> bigquery.Table:
    """Create the table if it doesn't exist. Returns the Table object."""
    table_ref = f"{client.project}.{dataset_id}.{table_id}"
    table = bigquery.Table(table_ref, schema=TABLE_SCHEMA)

    # Partition by date so queries on date ranges are cheap
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="date",
    )
    # Cluster by symbol for fast per-ticker lookups
    table.clustering_fields = ["symbol"]

    try:
        table = client.create_table(table)
        logger.info("Created table %s", table_ref)
    except Conflict:
        logger.info("Table %s already exists", table_ref)
        table = client.get_table(table_ref)

    return table


def load_dataframe(
    client: bigquery.Client,
    df: pd.DataFrame,
    dataset_id: str,
    table_id: str,
    write_disposition: str = "WRITE_APPEND",
) -> int:
    """
    Load a DataFrame into BigQuery.

    write_disposition options:
        WRITE_APPEND   – append rows (default; safe for incremental loads)
        WRITE_TRUNCATE – replace all existing rows
        WRITE_EMPTY    – fail if table already has rows
    """
    if df.empty:
        logger.warning("DataFrame is empty — nothing to load.")
        return 0

    table_ref = f"{client.project}.{dataset_id}.{table_id}"

    job_config = bigquery.LoadJobConfig(
        schema=TABLE_SCHEMA,
        write_disposition=write_disposition,
        source_format=bigquery.SourceFormat.PARQUET,
    )

    # Convert date column to proper type for Parquet serialisation
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["ingested_at"] = pd.to_datetime(df["ingested_at"])
    # Int64 (nullable) → plain int64 for Parquet
    df["volume"] = df["volume"].astype("int64")

    job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()  # wait for completion

    loaded = job.output_rows
    logger.info("Loaded %d rows into %s", loaded, table_ref)
    return loaded
