"""
ARIMAX (SARIMAX) model for existing-customer forecasting.

Training:
  y      = existing_count (monthly time series per product line)
  exog   = new_count for the same month — captures the correlation between
            acquisition volume and the size of the existing base.

Forecasting:
  future exog = user-supplied new customer counts for each future month.
"""

import warnings
import logging

import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

# SARIMAX order — (p,d,q)(P,D,Q,m)
_ORDER         = (1, 1, 1)
_SEASONAL_ORDER = (1, 0, 1, 12)


def forecast_arimax(
    history: pd.DataFrame,
    future_new: pd.Series,
) -> pd.DataFrame:
    """
    Fit SARIMAX and return a forecast DataFrame.

    Parameters
    ----------
    history : DataFrame with columns [month, existing_count, new_count].
              month must be a datetime64 column sorted ascending.
    future_new : Series indexed by future month Timestamps,
                 values = planned new customer counts.

    Returns
    -------
    DataFrame with columns:
        month, existing_forecast, lower_ci, upper_ci
    """
    ts = (
        history.set_index("month")["existing_count"]
        .asfreq("MS")
        .astype(float)
    )
    exog_train = (
        history.set_index("month")["new_count"]
        .asfreq("MS")
        .astype(float)
        .values.reshape(-1, 1)
    )
    exog_future = future_new.values.reshape(-1, 1).astype(float)

    logger.info("Fitting SARIMAX on %d observations.", len(ts))
    model = SARIMAX(
        ts,
        exog=exog_train,
        order=_ORDER,
        seasonal_order=_SEASONAL_ORDER,
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    result = model.fit(disp=False, maxiter=200)

    n = len(future_new)
    fc = result.get_forecast(steps=n, exog=exog_future)
    mean = fc.predicted_mean
    ci   = fc.conf_int(alpha=0.20)  # 80 % confidence interval

    return pd.DataFrame({
        "month":             future_new.index,
        "existing_forecast": np.maximum(0, mean.values).round().astype(int),
        "lower_ci":          np.maximum(0, ci.iloc[:, 0].values).round().astype(int),
        "upper_ci":          np.maximum(0, ci.iloc[:, 1].values).round().astype(int),
    })
