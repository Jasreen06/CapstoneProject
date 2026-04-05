"""
forecasting.py
==============
Step 4: Three forecasting models — ARIMA, Prophet, XGBoost.
Each exposes a uniform fit/predict interface.

Usage:
    from forecasting import ARIMAModel, ProphetModel, XGBoostModel

    model = ProphetModel()
    model.fit(train_df)                    # train_df has columns: date, portcalls
    forecast = model.predict(horizon=7)    # returns DataFrame with ds, yhat, yhat_lower, yhat_upper
"""

from __future__ import annotations
import time
import warnings
import logging

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

FORECAST_HORIZON = 7   # days


# ──────────────────────────────────────────────
# Base class
# ──────────────────────────────────────────────

class BaseForecaster:
    name: str = "Base"

    def fit(self, daily: pd.DataFrame) -> "BaseForecaster":
        """
        Fit the model on a daily DataFrame.
        Must contain columns: date (datetime), portcalls (float).
        Returns self.
        """
        raise NotImplementedError

    def predict(self, horizon: int = FORECAST_HORIZON) -> pd.DataFrame:
        """
        Return a forecast DataFrame with columns:
            ds, yhat, yhat_lower, yhat_upper, model
        """
        raise NotImplementedError

    @property
    def fit_time(self) -> float:
        return getattr(self, "_fit_time", 0.0)

    def _prep(self, daily: pd.DataFrame) -> pd.DataFrame:
        """Shared preprocessing: sort, clip, fill zeros."""
        df = daily[["date", "portcalls"]].copy()
        df = df.sort_values("date").reset_index(drop=True)
        df["portcalls"] = pd.to_numeric(df["portcalls"], errors="coerce").fillna(0).clip(lower=0)
        return df

    def _future_dates(self, last_date: pd.Timestamp, horizon: int) -> pd.DatetimeIndex:
        return pd.date_range(last_date + pd.Timedelta(days=1), periods=horizon, freq="D")


# ──────────────────────────────────────────────
# ARIMA
# ──────────────────────────────────────────────

class ARIMAModel(BaseForecaster):
    name = "ARIMA"

    def __init__(self, max_p: int = 3, max_q: int = 3):
        self.max_p = max_p
        self.max_q = max_q
        self._model = None
        self._last_date = None

    def fit(self, daily: pd.DataFrame) -> "ARIMAModel":
        from statsmodels.tsa.arima.model import ARIMA
        from statsmodels.tsa.stattools import adfuller

        df = self._prep(daily)
        s  = df.set_index("date")["portcalls"].resample("D").sum().astype(float)

        # Determine differencing order
        try:
            d = 0 if adfuller(s.dropna())[1] < 0.05 else 1
        except Exception:
            d = 1

        # Grid search over (p, d, q)
        best_aic, best_order = np.inf, (1, d, 1)
        for p in range(self.max_p + 1):
            for q in range(self.max_q + 1):
                try:
                    m = ARIMA(s, order=(p, d, q)).fit()
                    if m.aic < best_aic:
                        best_aic, best_order = m.aic, (p, d, q)
                except Exception:
                    continue

        t0 = time.time()
        self._model = ARIMA(s, order=best_order).fit()
        self._fit_time = time.time() - t0
        self._last_date = s.index[-1]
        logger.info(f"ARIMA fitted order={best_order}  AIC={self._model.aic:.1f}  fit={self._fit_time:.2f}s")
        return self

    def predict(self, horizon: int = FORECAST_HORIZON) -> pd.DataFrame:
        if self._model is None:
            raise RuntimeError("Call fit() first.")
        fcst = self._model.get_forecast(horizon)
        ci   = fcst.conf_int(alpha=0.05)
        future = self._future_dates(self._last_date, horizon)
        return pd.DataFrame({
            "ds":         future,
            "yhat":       np.maximum(fcst.predicted_mean.values, 0),
            "yhat_lower": np.maximum(ci.iloc[:, 0].values, 0),
            "yhat_upper": np.maximum(ci.iloc[:, 1].values, 0),
            "model":      self.name,
        })


# ──────────────────────────────────────────────
# Prophet
# ──────────────────────────────────────────────

class ProphetModel(BaseForecaster):
    name = "Prophet"

    def __init__(self,
                 changepoint_prior_scale: float = 0.05,
                 seasonality_prior_scale: float = 10.0,
                 uncertainty_samples: int = 200):
        self.cps = changepoint_prior_scale
        self.sps = seasonality_prior_scale
        self.ucs = uncertainty_samples
        self._model = None
        self._last_date = None

    def fit(self, daily: pd.DataFrame) -> "ProphetModel":
        from prophet import Prophet

        df = self._prep(daily)
        pdf = df.rename(columns={"date": "ds", "portcalls": "y"})
        pdf = pdf.dropna(subset=["ds", "y"])

        # Use multiplicative mode if series is strictly positive
        mode = "multiplicative" if pdf["y"].min() > 0 else "additive"
        if mode == "multiplicative":
            pdf["y"] = pdf["y"].replace(0, 1e-6)

        t0 = time.time()
        m = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            seasonality_mode=mode,
            changepoint_prior_scale=self.cps,
            seasonality_prior_scale=self.sps,
            uncertainty_samples=self.ucs,
        )
        m.fit(pdf)
        self._fit_time = time.time() - t0
        self._model = m
        self._last_date = pd.Timestamp(pdf["ds"].iloc[-1])
        logger.info(f"Prophet fitted  mode={mode}  fit={self._fit_time:.2f}s")
        return self

    def predict(self, horizon: int = FORECAST_HORIZON) -> pd.DataFrame:
        if self._model is None:
            raise RuntimeError("Call fit() first.")
        future = self._model.make_future_dataframe(periods=horizon, freq="D")
        fcst   = self._model.predict(future).tail(horizon)
        return pd.DataFrame({
            "ds":         fcst["ds"].values,
            "yhat":       np.maximum(fcst["yhat"].values, 0),
            "yhat_lower": np.maximum(fcst["yhat_lower"].values, 0),
            "yhat_upper": np.maximum(fcst["yhat_upper"].values, 0),
            "model":      self.name,
        })


# ──────────────────────────────────────────────
# XGBoost
# ──────────────────────────────────────────────

class XGBoostModel(BaseForecaster):
    name = "XGBoost"

    # Chokepoints whose transit volume is a leading indicator for US port arrivals.
    # Lags (days) reflect realistic ocean transit times from each chokepoint.
    CHOKEPOINT_LAGS = [14, 21, 28]

    def __init__(self,
                 n_estimators: int = 200,
                 learning_rate: float = 0.05,
                 max_depth: int = 4,
                 lags: list[int] | None = None):
        self.n_estimators  = n_estimators
        self.learning_rate = learning_rate
        self.max_depth     = max_depth
        self.lags          = lags or [1, 2, 3, 7, 14, 21]
        self._model        = None
        self._history      = None
        self._resid_std    = 0.0
        self._last_date    = None
        self._chk_series: dict[str, np.ndarray] = {}  # name → aligned daily values

    # ── Chokepoint alignment helper ───────────────────────────
    def _align_chokepoints(
        self,
        dates: pd.DatetimeIndex,
        chokepoint_data: dict[str, pd.DataFrame],
    ) -> dict[str, np.ndarray]:
        """
        Align each chokepoint series to the port's date index.
        Missing dates are forward-filled then zero-filled.
        """
        aligned = {}
        for name, chk_df in chokepoint_data.items():
            s = (
                chk_df.set_index("date")["n_total"]
                .reindex(dates)
                .ffill()
                .fillna(0)
                .values.astype(float)
            )
            aligned[name] = s
        return aligned

    # ── Feature builder ──────────────────────────────────────
    def _make_features(
        self,
        values: np.ndarray,
        dates: pd.DatetimeIndex,
        chk_aligned: dict[str, np.ndarray] | None = None,
    ) -> np.ndarray:
        n = len(values)
        max_lag = max(self.lags)
        rows = []
        for i in range(max_lag, n):
            lag_feats = [values[i - lag] for lag in self.lags]
            roll7_mean  = values[max(0, i-7):i].mean()
            roll14_mean = values[max(0, i-14):i].mean()
            roll7_std   = values[max(0, i-7):i].std() or 0.0
            dt = pd.Timestamp(dates[i])
            cal_feats = [dt.dayofweek, dt.month, dt.year, int(dt.dayofweek >= 5)]

            # Lagged chokepoint transit volume features
            chk_feats = []
            if chk_aligned:
                for arr in chk_aligned.values():
                    for lag in self.CHOKEPOINT_LAGS:
                        idx = i - lag
                        chk_feats.append(float(arr[idx]) if idx >= 0 else 0.0)

            rows.append(lag_feats + [roll7_mean, roll14_mean, roll7_std] + cal_feats + chk_feats)
        return np.array(rows, dtype=float)

    def fit(
        self,
        daily: pd.DataFrame,
        chokepoint_data: dict[str, pd.DataFrame] | None = None,
    ) -> "XGBoostModel":
        import xgboost as xgb

        df = self._prep(daily)
        values = df["portcalls"].values.astype(float)
        dates  = pd.DatetimeIndex(df["date"].values)

        max_lag = max(self.lags)
        if len(values) < max_lag + 10:
            raise ValueError(f"Need ≥ {max_lag + 10} days; got {len(values)}.")

        chk_aligned = self._align_chokepoints(dates, chokepoint_data) if chokepoint_data else {}
        self._chk_series = chk_aligned

        X = self._make_features(values, dates, chk_aligned)
        y = values[max_lag:]

        t0 = time.time()
        self._model = xgb.XGBRegressor(
            n_estimators=self.n_estimators,
            learning_rate=self.learning_rate,
            max_depth=self.max_depth,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbosity=0,
        )
        self._model.fit(X, y)
        self._fit_time  = time.time() - t0
        self._resid_std = float(np.std(y - self._model.predict(X)))
        self._history   = list(values)
        self._dates     = dates
        self._last_date = dates[-1]
        n_chk_feats = len(chk_aligned) * len(self.CHOKEPOINT_LAGS)
        logger.info(
            f"XGBoost fitted  resid_std={self._resid_std:.3f}  "
            f"chk_features={n_chk_feats}  fit={self._fit_time:.2f}s"
        )
        return self

    def predict(self, horizon: int = FORECAST_HORIZON) -> pd.DataFrame:
        if self._model is None:
            raise RuntimeError("Call fit() first.")

        buf    = list(self._history)
        future = self._future_dates(self._last_date, horizon)
        preds  = []

        # For future dates, hold chokepoint values at their last known level
        chk_bufs = {name: list(arr) for name, arr in self._chk_series.items()}

        for fd in future:
            arr = np.array(buf, dtype=float)
            lag_feats   = [arr[-lag] if len(arr) >= lag else 0.0 for lag in self.lags]
            roll7_mean  = arr[-7:].mean()
            roll14_mean = arr[-14:].mean()
            roll7_std   = arr[-7:].std() or 0.0
            cal_feats   = [fd.dayofweek, fd.month, fd.year, int(fd.dayofweek >= 5)]

            chk_feats = []
            for name, cbuf in chk_bufs.items():
                carr = np.array(cbuf, dtype=float)
                for lag in self.CHOKEPOINT_LAGS:
                    chk_feats.append(float(carr[-lag]) if len(carr) >= lag else 0.0)
                # Extend chokepoint buffer with last known value
                cbuf.append(cbuf[-1] if cbuf else 0.0)

            X_pred = np.array([lag_feats + [roll7_mean, roll14_mean, roll7_std] + cal_feats + chk_feats])
            p = max(float(self._model.predict(X_pred)[0]), 0)
            preds.append(p)
            buf.append(p)

        preds = np.array(preds)
        return pd.DataFrame({
            "ds":         future,
            "yhat":       preds,
            "yhat_lower": np.maximum(preds - 1.96 * self._resid_std, 0),
            "yhat_upper": preds + 1.96 * self._resid_std,
            "model":      self.name,
        })


# ──────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────

def get_model(name: str) -> BaseForecaster:
    """Return a fresh model instance by name."""
    mapping = {
        "ARIMA":   ARIMAModel,
        "Prophet": ProphetModel,
        "XGBoost": XGBoostModel,
    }
    if name not in mapping:
        raise ValueError(f"Unknown model '{name}'. Choose from: {list(mapping)}")
    return mapping[name]()


ALL_MODELS = ["ARIMA", "Prophet", "XGBoost"]


if __name__ == "__main__":
    import sys, logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    from data_cleaning import load_and_clean, get_port_daily_series

    path = sys.argv[1] if len(sys.argv) > 1 else "portwatch_us_data.csv"
    df   = load_and_clean(path)
    port = "Los Angeles"
    daily = get_port_daily_series(df, port)

    for mname in ALL_MODELS:
        model = get_model(mname)
        try:
            model.fit(daily)
            fcst = model.predict(7)
            print(f"\n{mname} — next 7 days:")
            print(fcst[["ds","yhat","yhat_lower","yhat_upper"]].to_string(index=False))
        except Exception as e:
            print(f"{mname} error: {e}")
