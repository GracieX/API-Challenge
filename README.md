# API-Challenge

## Yahoo Finance → BigQuery Pipeline

Fetches historical OHLCV stock data from Yahoo Finance and loads it into a Google BigQuery table, with automatic dataset/table creation, date-partitioning, and clustering for efficient queries.

---

## Project Structure

```
API-Challenge/
├── pipeline.py          # Entrypoint — orchestrates the full ETL
├── yahoo_fetcher.py     # Downloads data from Yahoo Finance (yfinance)
├── bigquery_loader.py   # Creates BQ resources and loads data
├── config.py            # Reads settings from .env / environment variables
├── requirements.txt     # Python dependencies
├── .env.example         # Template for your .env file
└── WeatherPy.ipynb      # (original) OpenWeatherMap analysis notebook
```

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | |
| Google Cloud project | With BigQuery API enabled |
| Service account key | Roles: `BigQuery Data Editor` + `BigQuery Job User` |

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Edit `.env` and fill in at minimum:

```env
GCP_PROJECT_ID=your-gcp-project-id
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

Optional overrides (defaults shown):

```env
BQ_DATASET_ID=stock_data
BQ_TABLE_ID=yahoo_prices
STOCK_TICKERS=AAPL,MSFT,GOOGL,AMZN,TSLA
START_DATE=2024-01-01
END_DATE=2025-01-01
DATA_INTERVAL=1d
```

### 3. Enable BigQuery API

```bash
gcloud services enable bigquery.googleapis.com --project YOUR_PROJECT_ID
```

---

## Running the Pipeline

### Basic run (uses `.env` settings)

```bash
python pipeline.py
```

### Override tickers

```bash
python pipeline.py --tickers AAPL NVDA META
```

### Custom date range

```bash
python pipeline.py --start 2023-01-01 --end 2024-12-31
```

### Weekly data

```bash
python pipeline.py --interval 1wk
```

### Replace all existing data (truncate)

```bash
python pipeline.py --mode truncate
```

### All options together

```bash
python pipeline.py \
  --tickers AAPL MSFT GOOGL \
  --start 2024-01-01 \
  --end 2025-01-01 \
  --interval 1d \
  --mode append
```

---

## BigQuery Table Schema

| Column | Type | Description |
|---|---|---|
| `symbol` | STRING | Ticker symbol (e.g. `AAPL`) |
| `date` | DATE | Trading date (partition key) |
| `open` | FLOAT64 | Opening price |
| `high` | FLOAT64 | Daily high |
| `low` | FLOAT64 | Daily low |
| `close` | FLOAT64 | Closing price |
| `adj_close` | FLOAT64 | Adjusted closing price |
| `volume` | INT64 | Shares traded |
| `dividends` | FLOAT64 | Dividend amount (0 on non-dividend days) |
| `stock_splits` | FLOAT64 | Split ratio (0 on non-split days) |
| `ingested_at` | TIMESTAMP | UTC timestamp of ingestion run |

The table is **partitioned by `date`** and **clustered by `symbol`** for cost-efficient queries.

---

## Querying in BigQuery

```sql
-- Latest closing prices
SELECT symbol, date, close, volume
FROM `your-project.stock_data.yahoo_prices`
WHERE date = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
ORDER BY symbol;

-- AAPL price history for a year
SELECT date, open, high, low, close, volume
FROM `your-project.stock_data.yahoo_prices`
WHERE symbol = 'AAPL'
  AND date BETWEEN '2024-01-01' AND '2025-01-01'
ORDER BY date;

-- Average daily volume per ticker
SELECT symbol, AVG(volume) AS avg_volume
FROM `your-project.stock_data.yahoo_prices`
GROUP BY symbol
ORDER BY avg_volume DESC;
```
