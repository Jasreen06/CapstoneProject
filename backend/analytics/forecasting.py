"""
forecasting.py
==============
Congestion forecasting for DockWise AI v2.
Wraps ARIMA, Prophet, XGBoost models from the v1 codebase.
"""

from __future__ import annotations
import logging
import warnings
from typing import Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

from analytics.congestion import compute_congestion_scores, get_congestion_level


def forecast_congestion(
    port_name: str,
    df: pd.DataFrame,
    model: str = "Prophet",
    horizon_days: int = 7,
) -> list[dict[str, Any]]:
    """
    Forecast congestion for a port.

    Args:
        port_name: Name of the port (for logging).
        df: DataFrame with columns [date, portcalls].
        model: "Prophet", "XGBoost", or "ARIMA".
        horizon_days: Number of days to forecast.

    Returns:
        List of {date, predicted_portcalls, congestion_score, congestion_level}.
    """
    if df.empty or len(df) < 30:
        logger.warning(f"Insufficient data for {port_name} forecast (need ≥30 days)")
        return []

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    try:
        if model == "Prophet":
            return _forecast_prophet(df, horizon_days)
        elif model == "XGBoost":
            return _forecast_xgboost(df, horizon_days)
        elif model == "ARIMA":
            return _forecast_arima(df, horizon_days)
        else:
            raise ValueError(f"Unknown model: {model}")
    except Exception as e:
        logger.error(f"Forecasting error ({model}) for {port_name}: {e}")
        # Fall back to simple moving average
        return _forecast_fallback(df, horizon_days)


def _make_output(forecast_df: pd.DataFrame, history_df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert forecast DataFrame to output format with congestion scores."""
    # Combine history + forecast to compute rolling z-score correctly
    hist = history_df[["date", "portcalls"]].copy()
    hist["is_forecast"] = False

    fcast = pd.DataFrame({
        "date": forecast_df["ds"],
        "portcalls": np.maximum(forecast_df["yhat"].values, 0),
        "is_forecast": True,
    })

    combined = pd.concat([hist, fcast], ignore_index=True).sort_values("date")
    combined = compute_congestion_scores(combined)

    results = []
    for _, row in combined[combined["is_forecast"]].iterrows():
        results.append({
            "date": str(row["date"])[:10],
            "predicted_portcalls": round(float(row["portcalls"]), 1),
            "congestion_score": round(float(row["congestion_score"]), 1),
            "congestion_level": row["congestion_level"],
        })
    return results


def _forecast_prophet(df: pd.DataFrame, horizon: int) -> list[dict[str, Any]]:
    from prophet import Prophet

    pdf = df.rename(columns={"date": "ds", "portcalls": "y"})
    pdf = pdf.dropna(subset=["ds", "y"])

    mode = "multiplicative" if pdf["y"].min() > 0 else "additive"
    if mode == "multiplicative":
        pdf["y"] = pdf["y"].replace(0, 1e-6)

    m = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        seasonality_mode=mode,
        changepoint_prior_scale=0.05,
        uncertainty_samples=100,
    )
    m.fit(pdf)
    future = m.make_future_dataframe(periods=horizon, freq="D")
    fcst = m.predict(future).tail(horizon)

    return _make_output(
        pd.DataFrame({"ds": fcst["ds"].values, "yhat": np.maximum(fcst["yhat"].values, 0)}),
        df,
    )


def _forecast_xgboost(df: pd.DataFrame, horizon: int) -> list[dict[str, Any]]:
    import xgboost as xgb

    lags = [1, 2, 3, 7, 14, 21]
    max_lag = max(lags)

    values = df["portcalls"].values.astype(float)
    dates = pd.DatetimeIndex(df["date"].values)

    if len(values) < max_lag + 10:
        return _forecast_fallback(df, horizon)

    def make_features(arr, dates_arr):
        n = len(arr)
        rows = []
        for i in range(max_lag, n):
            lag_feats = [arr[i - lag] for lag in lags]
            roll7 = arr[max(0, i - 7):i].mean()
            roll14 = arr[max(0, i - 14):i].mean()
            roll7_std = arr[max(0, i - 7):i].std() or 0.0
            dt = pd.Timestamp(dates_arr[i])
            cal = [dt.dayofweek, dt.month, int(dt.dayofweek >= 5)]
            rows.append(lag_feats + [roll7, roll14, roll7_std] + cal)
        return np.array(rows, dtype=float)

    X = make_features(values, dates)
    y = values[max_lag:]

    model = xgb.XGBRegressor(
        n_estimators=100, learning_rate=0.05, max_depth=4, verbosity=0, random_state=42
    )
    model.fit(X, y)

    buf = list(values)
    last_date = dates[-1]
    preds = []
    future_dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=horizon, freq="D")

    for fd in future_dates:
        arr = np.array(buf, dtype=float)
        lag_feats = [arr[-lag] if len(arr) >= lag else 0.0 for lag in lags]
        roll7 = arr[-7:].mean()
        roll14 = arr[-14:].mean()
        roll7_std = arr[-7:].std() or 0.0
        cal = [fd.dayofweek, fd.month, int(fd.dayofweek >= 5)]
        X_pred = np.array([lag_feats + [roll7, roll14, roll7_std] + cal])
        p = max(float(model.predict(X_pred)[0]), 0)
        preds.append(p)
        buf.append(p)

    return _make_output(
        pd.DataFrame({"ds": future_dates, "yhat": preds}),
        df,
    )


def _forecast_arima(df: pd.DataFrame, horizon: int) -> list[dict[str, Any]]:
    from statsmodels.tsa.arima.model import ARIMA

    s = df.set_index("date")["portcalls"].resample("D").sum().astype(float)
    model = ARIMA(s, order=(2, 1, 2)).fit()
    fcst = model.get_forecast(horizon)
    future = pd.date_range(s.index[-1] + pd.Timedelta(days=1), periods=horizon, freq="D")

    return _make_output(
        pd.DataFrame({"ds": future, "yhat": np.maximum(fcst.predicted_mean.values, 0)}),
        df,
    )


def _forecast_fallback(df: pd.DataFrame, horizon: int) -> list[dict[str, Any]]:
    """Simple 14-day moving average fallback."""
    last_avg = df["portcalls"].tail(14).mean()
    last_date = pd.to_datetime(df["date"].iloc[-1])
    future = pd.date_range(last_date + pd.Timedelta(days=1), periods=horizon, freq="D")
    preds = [last_avg] * horizon
    return _make_output(
        pd.DataFrame({"ds": future, "yhat": preds}),
        df,
    )
