"""Synthetic weather: solar geometry, clear-sky index, temperature and wind, plus a
day-ahead weather forecast with realistic error. Deterministic for a given seed."""
from __future__ import annotations

import numpy as np
import pandas as pd

IST_MERIDIAN = 82.5


def cos_zenith(index: pd.DatetimeIndex, lat_deg: float, lon_deg: float) -> np.ndarray:
    """Cosine of solar zenith at the midpoint of each step (clipped at 0)."""
    step_h = (index[1] - index[0]).total_seconds() / 3600 if len(index) > 1 else 0.25
    doy = index.dayofyear.values
    b = 2 * np.pi * (doy - 81) / 364
    eot_min = 9.87 * np.sin(2 * b) - 7.53 * np.cos(b) - 1.5 * np.sin(b)
    clock_h = index.hour.values + index.minute.values / 60 + step_h / 2
    solar_h = clock_h + (4 * (lon_deg - IST_MERIDIAN) + eot_min) / 60
    omega = np.radians(15 * (solar_h - 12))
    decl = np.radians(23.45 * np.sin(np.radians(360 / 365 * (284 + doy))))
    lat = np.radians(lat_deg)
    cz = np.sin(lat) * np.sin(decl) + np.cos(lat) * np.cos(decl) * np.cos(omega)
    return np.clip(cz, 0, None)


def clear_sky_ghi(cz: np.ndarray) -> np.ndarray:
    """Haurwitz clear-sky GHI model, W/m2."""
    out = np.zeros_like(cz)
    m = cz > 0.01
    out[m] = 1098 * cz[m] * np.exp(-0.057 / cz[m])
    return out


def _ar1(rng, n, phi, sigma):
    x = np.zeros(n)
    e = rng.normal(0, sigma, n)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    return x


def make_weather(index: pd.DatetimeIndex, lat: float, lon: float, seed: int,
                 forced_cloudy_days: list[int] | None = None) -> pd.DataFrame:
    """Actual and day-ahead-forecast weather on the given index.

    forced_cloudy_days: day numbers (0-based) forced to be overcast so the evaluation
    week always contains monsoon stress days.
    """
    rng = np.random.default_rng(seed)
    n = len(index)
    steps_per_day = int(round(24 / ((index[1] - index[0]).total_seconds() / 3600)))
    n_days = n // steps_per_day
    day_of_step = np.arange(n) // steps_per_day

    # daily sky regime: clear / partly cloudy / overcast (monsoon)
    regimes = rng.choice([0, 1, 2], size=n_days, p=[0.45, 0.35, 0.20])
    for d in forced_cloudy_days or []:
        if d < n_days:
            regimes[d] = 2
    day_mean = np.array([0.88, 0.66, 0.38])[regimes] + rng.normal(0, 0.03, n_days)
    day_vol = np.array([0.04, 0.12, 0.16])[regimes]

    transient = _ar1(rng, n, 0.80, 1.0)
    csi = day_mean[day_of_step] + transient * day_vol[day_of_step]
    csi = np.clip(csi, 0.05, 1.05)

    cz = cos_zenith(index, lat, lon)
    ghi = clear_sky_ghi(cz) * csi

    hour = index.hour.values + index.minute.values / 60
    diurnal = -np.cos(2 * np.pi * (hour - 2.0) / 24)          # min ~02:00-06:00, max ~14:00
    cloud_cool = np.array([0.0, 1.5, 3.5])[regimes][day_of_step]
    temp = 27.5 + 3.8 * diurnal - cloud_cool + _ar1(rng, n, 0.95, 0.15)

    # Tamil Nadu monsoon wind: strong, peaking afternoon/evening
    wind_diurnal = 0.10 * np.sin(2 * np.pi * (hour - 9) / 24)
    wind_cf = np.clip(0.40 + wind_diurnal + 0.6 * _ar1(rng, n, 0.97, 0.05), 0.0, 0.95)

    # ---- day-ahead forecast: knows the regime roughly, not the transients
    fc_day_err = rng.normal(0, 1, n_days) * np.array([0.04, 0.10, 0.14])[regimes]
    csi_fc = np.clip(day_mean[day_of_step] + fc_day_err[day_of_step], 0.05, 1.0)
    temp_fc = temp + _ar1(rng, n, 0.9, 0.25)
    wind_fc = np.clip(pd.Series(wind_cf).rolling(16, center=True, min_periods=1).mean().values
                      + _ar1(rng, n, 0.98, 0.012), 0, 0.95)

    return pd.DataFrame({
        "cos_zenith": cz,
        "ghi_clear": clear_sky_ghi(cz),
        "csi": csi,
        "ghi": ghi,
        "temp_c": temp,
        "wind_cf": wind_cf,
        "csi_fc": csi_fc,
        "ghi_fc": clear_sky_ghi(cz) * csi_fc,
        "temp_fc": temp_fc,
        "wind_cf_fc": wind_fc,
        "regime": regimes[day_of_step],
    }, index=index)


def pv_power(ghi: np.ndarray, temp_c: np.ndarray, kwp: float, pr: float = 0.80) -> np.ndarray:
    """PV AC output (same unit as kwp) with a simple -0.4 %/degC cell temperature derate."""
    cell = temp_c + 0.03 * ghi
    derate = 1 - 0.004 * (cell - 25)
    return np.clip(kwp * ghi / 1000 * pr * derate, 0, kwp)
