"""
Forecast engine — orchestrates data preparation, model fitting, and result assembly.

Output columns (one row per future month):
    month                  | Timestamp
    new_classic            | new customers routed to Classic
    new_super              | new customers routed to Super
    existing_classic       | forecasted existing Classic customers
    existing_super         | forecasted existing Super customers
    total_classic          | new_classic + existing_classic
    total_super            | new_super  + existing_super
    lower_ci_classic       | 80 % lower bound for existing Classic
    upper_ci_classic       | 80 % upper bound for existing Classic
    lower_ci_super         | 80 % lower bound for existing Super
    upper_ci_super         | 80 % upper bound for existing Super
"""

import logging

import pandas as pd

from models.arimax_model import forecast_arimax
from models.prophet_model import forecast_prophet

logger = logging.getLogger(__name__)


def _prepare_product_history(hist_df: pd.DataFrame, product: str) -> pd.DataFrame:
    """Return a tidy [month, existing_count, new_count] frame for one product line."""
    prod = hist_df[hist_df["product_line"] == product].copy()

    existing = (
        prod[prod["customer_type"] == "existing"]
        .groupby("month")["customer_count"].sum()
        .rename("existing_count")
    )
    new = (
        prod[prod["customer_type"] == "new"]
        .groupby("month")["customer_count"].sum()
        .rename("new_count")
    )

    merged = (
        pd.concat([existing, new], axis=1)
        .fillna(0)
        .reset_index()
        .sort_values("month")
    )
    merged["month"] = pd.to_datetime(merged["month"])
    return merged


def run_forecast(
    hist_df: pd.DataFrame,
    new_customer_plan: pd.DataFrame,
    classic_pct: float,
    super_pct: float,
    model_name: str,
    n_months: int,
) -> pd.DataFrame:
    """
    Parameters
    ----------
    hist_df           : historical data (month, customer_type, product_line, customer_count)
    new_customer_plan : DataFrame with columns [month (str YYYY-MM), new_customers (int)]
    classic_pct       : fraction of new customers going to Classic (0–1)
    super_pct         : fraction going to Super (0–1)
    model_name        : 'ARIMAX' or 'Prophet'
    n_months          : number of months to forecast
    """
    # ── Build future new-customer series ───────────────────────────────────────
    plan = new_customer_plan.copy()
    plan["month"] = pd.to_datetime(plan["month"].astype(str) + "-01")
    plan = plan.set_index("month")["new_customers"]

    future_new_classic = (plan * classic_pct).round().astype(int)
    future_new_super   = (plan * super_pct).round().astype(int)

    # ── Fit model for each product line ────────────────────────────────────────
    model_fn = forecast_arimax if model_name == "ARIMAX" else forecast_prophet

    for product, future_new in [("classic", future_new_classic), ("super", future_new_super)]:
        history = _prepare_product_history(hist_df, product)
        logger.info("Running %s for product_line=%s", model_name, product)

        fc = model_fn(history=history, future_new=future_new)

        if product == "classic":
            fc_classic = fc
        else:
            fc_super = fc

    # ── Assemble result ─────────────────────────────────────────────────────────
    result = pd.DataFrame({"month": fc_classic["month"]})

    result["new_classic"]      = future_new_classic.values
    result["new_super"]        = future_new_super.values
    result["existing_classic"] = fc_classic["existing_forecast"].values
    result["existing_super"]   = fc_super["existing_forecast"].values
    result["total_classic"]    = result["new_classic"] + result["existing_classic"]
    result["total_super"]      = result["new_super"]   + result["existing_super"]
    result["lower_ci_classic"] = fc_classic["lower_ci"].values
    result["upper_ci_classic"] = fc_classic["upper_ci"].values
    result["lower_ci_super"]   = fc_super["lower_ci"].values
    result["upper_ci_super"]   = fc_super["upper_ci"].values

    return result
