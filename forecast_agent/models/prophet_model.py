"""
Prophet model for existing-customer forecasting.

new_count is added as an additional regressor so the model can learn how
acquisition volume relates to the size of the existing base.
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def forecast_prophet(
    history: pd.DataFrame,
    future_new: pd.Series,
) -> pd.DataFrame:
    """
    Fit a Prophet model and return a forecast DataFrame.

    Parameters
    ----------
    history : DataFrame with columns [month, existing_count, new_count].
    future_new : Series indexed by future month Timestamps,
                 values = planned new customer counts.

    Returns
    -------
    DataFrame with columns:
        month, existing_forecast, lower_ci, upper_ci
    """
    from prophet import Prophet  # imported lazily — heavy dependency

    train = pd.DataFrame({
        "ds": history["month"],
        "y":  history["existing_count"].astype(float),
        "new_count": history["new_count"].astype(float),
    })

    m = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        interval_width=0.80,
        changepoint_prior_scale=0.05,
    )
    m.add_regressor("new_count")

    logger.info("Fitting Prophet on %d observations.", len(train))
    m.fit(train)

    future = pd.DataFrame({
        "ds":        future_new.index,
        "new_count": future_new.values.astype(float),
    })

    forecast = m.predict(future)

    return pd.DataFrame({
        "month":             pd.to_datetime(forecast["ds"]),
        "existing_forecast": np.maximum(0, forecast["yhat"]).round().astype(int),
        "lower_ci":          np.maximum(0, forecast["yhat_lower"]).round().astype(int),
        "upper_ci":          np.maximum(0, forecast["yhat_upper"]).round().astype(int),
    })
