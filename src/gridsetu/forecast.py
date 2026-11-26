"""Probabilistic day-ahead forecasting for the pilot feeder with LightGBM quantile
regression (q10 / q50 / q90), trained on synthetic history weeks."""
from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd

QUANTILES = (0.1, 0.5, 0.9)


def _features(index: pd.DatetimeIndex, wx: pd.DataFrame, lag_day: np.ndarray | None) -> pd.DataFrame:
    h = index.hour.values + index.minute.values / 60
    X = pd.DataFrame({
        "h_sin": np.sin(2 * np.pi * h / 24),
        "h_cos": np.cos(2 * np.pi * h / 24),
        "hour": h,
        "dow": index.dayofweek.values,
        "weekend": (index.dayofweek.values >= 5).astype(int),
        "temp_fc": wx["temp_fc"].values,
        "ghi_fc": wx["ghi_fc"].values,
        "csi_fc": wx["csi_fc"].values,
        "ghi_clear": wx["ghi_clear"].values,
    })
    if lag_day is not None:
        X["lag_day"] = lag_day
    return X


def _lag_day(series: np.ndarray, steps_per_day: int) -> np.ndarray:
    out = np.full_like(series, np.nan, dtype=float)
    out[steps_per_day:] = series[:-steps_per_day]
    return out


@dataclass
class QuantileForecast:
    q10: np.ndarray
    q50: np.ndarray
    q90: np.ndarray

    @property
    def spread(self) -> np.ndarray:
        return self.q90 - self.q10

    def skill(self, actual: np.ndarray) -> dict:
        def pinball(q, pred):
            d = actual - pred
            return float(np.mean(np.maximum(q * d, (q - 1) * d)))
        denom = np.maximum(np.abs(actual), 1e-6)
        mask = np.abs(actual) > 0.05 * np.max(np.abs(actual))
        return {
            "mae_q50": float(np.mean(np.abs(actual - self.q50))),
            "mape_q50_pct": float(100 * np.mean(np.abs(actual - self.q50)[mask] / denom[mask])) if mask.any() else 0.0,
            "coverage_q10_q90_pct": float(100 * np.mean((actual >= self.q10) & (actual <= self.q90))),
            "pinball_mean": float(np.mean([pinball(q, p) for q, p in
                                           zip(QUANTILES, (self.q10, self.q50, self.q90))])),
        }


class FeederForecaster:
    """Two quantile models: feeder net load (after rooftop PV) and community PV."""

    def __init__(self, steps_per_day: int, seed: int = 0):
        self.spd = steps_per_day
        self.seed = seed
        self.models: dict[str, dict[float, lgb.LGBMRegressor]] = {}
        self.conformal: dict[str, float] = {}

    def _fit(self, name: str, X: pd.DataFrame, y: np.ndarray):
        self.models[name] = {}
        for q in QUANTILES:
            m = lgb.LGBMRegressor(objective="quantile", alpha=q, n_estimators=300,
                                  learning_rate=0.05, num_leaves=31, min_child_samples=20,
                                  subsample=0.8, subsample_freq=1, colsample_bytree=0.9,
                                  random_state=self.seed, verbose=-1)
            m.fit(X, y)
            self.models[name][q] = m

    def fit(self, history: list, n_folds: int = 4, adapt_rate: float = 0.5) -> "FeederForecaster":
        """Cross-conformal quantile regression with daily adaptation.

        1. The history weeks are split into ``n_folds`` folds. For each fold a model is fitted
           on the other weeks and scored on the held-out ones, so every history week gives
           out-of-sample conformity scores (how far the actual fell outside q10-q90).
        2. The final models are fitted on all weeks.
        3. ``predict`` widens q10-q90 by the score quantile for 80 % coverage, and after each
           day moves that quantile level by ``adapt_rate`` x (yesterday's miss rate - 20 %)
           (adaptive conformal inference, Gibbs & Candes 2021), using only data already seen.
        """
        self.adapt_rate = adapt_rate
        k = max(2, min(n_folds, len(history)))
        folds = [list(map(int, c)) for c in np.array_split(np.arange(len(history)), k)]
        self.scores = {"net_load": [], "community_pv": []}
        for idx in folds:
            train = [w for j, w in enumerate(history) if j not in idx]
            self._fit_models(train)
            for j in idx:
                fl = history[j]
                raw = self._predict_raw(fl)
                for name in self.scores:
                    y = fl.net_load if name == "net_load" else fl.community_pv
                    fc = raw[name]
                    self.scores[name].append(np.maximum(fc[0] - y, y - fc[2]))
        self.scores = {n: np.concatenate(v) for n, v in self.scores.items()}
        self._fit_models(history)
        self.conformal = {n: _conformal_q(v, 0.8) for n, v in self.scores.items()}
        return self

    def _fit_models(self, history: list):
        Xl, yl, Xs, ys = [], [], [], []
        for fl in history:
            net = fl.net_load
            Xl.append(_features(fl.index, fl.weather, _lag_day(net, self.spd)))
            yl.append(net)
            Xs.append(_features(fl.index, fl.weather, None))
            ys.append(fl.community_pv)
        self._fit("net_load", pd.concat(Xl, ignore_index=True), np.concatenate(yl))
        self._fit("community_pv", pd.concat(Xs, ignore_index=True), np.concatenate(ys))

    def _predict_raw(self, fl, last_history=None) -> dict[str, np.ndarray]:
        net = fl.net_load
        lag = _lag_day(net, self.spd)
        if last_history is not None:  # day 1 lag comes from the last history day
            lag[: self.spd] = last_history.net_load[-self.spd:]
        out = {}
        for name, X in (("net_load", _features(fl.index, fl.weather, lag)),
                        ("community_pv", _features(fl.index, fl.weather, None))):
            preds = np.vstack([self.models[name][q].predict(X) for q in QUANTILES])
            out[name] = np.sort(preds, axis=0)  # remove quantile crossing
        return out

    def predict(self, fl, last_history=None) -> dict[str, QuantileForecast]:
        raw = self._predict_raw(fl, last_history)
        out = {}
        spd = self.spd
        for name, preds in raw.items():
            preds = preds.copy()
            actual = fl.net_load if name == "net_load" else fl.community_pv
            scores = getattr(self, "scores", {}).get(name)
            level = 0.8
            n_days = int(np.ceil(preds.shape[1] / spd))
            for d in range(n_days):
                sl = slice(d * spd, min((d + 1) * spd, preds.shape[1]))
                q = _conformal_q(scores, level) if scores is not None else self.conformal.get(name, 0.0)
                preds[0, sl] -= q
                preds[2, sl] += q
                if scores is not None:      # adapt from the day just observed (data the operator has)
                    miss = 1 - np.mean((actual[sl] >= preds[0, sl]) & (actual[sl] <= preds[2, sl]))
                    level = float(np.clip(level + self.adapt_rate * (miss - 0.2), 0.5, 0.99))
            if name == "community_pv":
                preds = np.clip(preds, 0, None)
                night = fl.weather["ghi_clear"].values < 1
                preds[:, night] = 0
            out[name] = QuantileForecast(*preds)
        return out


def _conformal_q(scores: np.ndarray, level: float) -> float:
    """Finite-sample conformal quantile of the conformity scores."""
    n = len(scores)
    return float(max(0.0, np.quantile(scores, min(1.0, np.ceil((n + 1) * level) / n))))
