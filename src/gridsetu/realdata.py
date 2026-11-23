"""Real data: NASA POWER weather for Coimbatore and IEX day-ahead prices.

Files (see docs/DATA_CARD.md for sources and checks):
  data/real/nasa_power_coimbatore_2025.csv   hourly GHI (all-sky, clear-sky) and 2 m temperature,
                                             20 Jul to 21 Sep 2025
  data/real/iex_dam_2025-09-14_20.csv        IEX DAM 15-minute market clearing price, 14-20 Sep 2025

The simulated week (14-20 Sep 2026) is mapped to the same calendar dates in 2025, so the
eight history weeks used to train the forecasters start on 20 Jul 2025, the first day of
the NASA file.

``nasa_weather`` returns the same columns as ``weather.make_weather`` so it can replace
it (``simulation.weather_source: nasa_power``). What is real and what is not:
  REAL       GHI and air temperature (NASA POWER, MERRA-2 / CERES SYN1deg)
  DERIVED    15-minute GHI: each NASA hourly mean is spread over its hour with the shape of
             the clear-sky curve, so every hour's energy is exactly NASA's
  REAL-BASED day-ahead weather forecast = persistence (yesterday's real weather). No
             forecast archive was used; a numerical weather forecast would do better, so this
             is a pessimistic test of the forecaster
  SYNTHETIC  wind capacity factor (not in the NASA file): the synthetic model, same seed
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .weather import clear_sky_ghi, cos_zenith, make_weather

ROOT = Path(__file__).resolve().parents[2]
NASA_FILE = ROOT / "data" / "real" / "nasa_power_coimbatore_2025.csv"
IEX_FILE = ROOT / "data" / "real" / "iex_dam_2025-09-14_20.csv"
NASA_LAT, NASA_LON = 11.02, 76.96
# NASA POWER "LST" is UTC + round(lon/15) h = UTC+5 here, so IST = LST + 30 min.
# Checked: Haurwitz clear-sky vs NASA clear-sky correlates best at +30 min (r = 0.997).
LST_TO_IST = pd.Timedelta(minutes=30)
YEAR_SHIFT = pd.DateOffset(years=1)


@lru_cache(maxsize=2)
def load_nasa(path: str | Path = NASA_FILE) -> pd.DataFrame:
    """Hourly NASA POWER rows indexed by the start of the hour in IST."""
    d = pd.read_csv(path, comment="#", parse_dates=["timestamp"])
    d.index = pd.DatetimeIndex(d.pop("timestamp")) + LST_TO_IST
    return d


@lru_cache(maxsize=2)
def load_iex(path: str | Path = IEX_FILE) -> pd.DataFrame:
    """15-minute IEX DAM rows indexed by block start (IST); price also in INR/kWh."""
    d = pd.read_csv(path, comment="#", parse_dates=["timestamp"])
    d.index = pd.DatetimeIndex(d.pop("timestamp"))
    d["mcp_inr_kwh"] = d["mcp_rs_per_mwh"] / 1000
    return d


def to_real_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Simulated 2026 timestamps -> the same calendar dates in 2025."""
    return pd.DatetimeIndex([t - YEAR_SHIFT for t in index])


def _hourly_to_steps(real_idx: pd.DatetimeIndex, step_min: int, lat: float, lon: float) -> pd.DataFrame:
    """Disaggregate NASA hourly GHI to the step grid, keeping each hour's energy."""
    nasa = load_nasa()
    # NASA hours run hh:30-hh+1:30 IST; steps of 15 or 30 min fall wholly inside one of them
    hours = (real_idx - LST_TO_IST).floor("h") + LST_TO_IST
    first, last = nasa.index[0], nasa.index[-1]
    if hours.min() < first - pd.Timedelta(hours=1) or hours.max() > last:
        raise ValueError(f"NASA file covers {first} .. {last} IST, not {real_idx[0]} .. {real_idx[-1]}")
    # the file starts at 00:30 IST: the half hour before it (night) takes the first hour's values
    hours = hours.where(hours >= first, first)
    # clear-sky shape at 1-minute resolution, averaged per step and per NASA hour
    fine = pd.date_range(min(hours.min(), real_idx.min()), hours.max() + pd.Timedelta(hours=1), freq="1min", inclusive="left")
    cs_fine = pd.Series(clear_sky_ghi(cos_zenith(fine, lat, lon)), index=fine)
    cs_step = cs_fine.resample(f"{step_min}min").mean().reindex(real_idx).values
    cs_hour = cs_fine.resample("1h", offset=LST_TO_IST).mean().reindex(hours).values
    allsky = nasa["ghi_allsky_wm2"].reindex(hours).values.astype(float)
    ratio = np.divide(allsky, cs_hour, out=np.zeros_like(allsky), where=cs_hour > 1.0)
    ghi = cs_step * ratio
    # temperature: linear between hour midpoints (NASA T2M is an hourly value)
    t_mid = nasa.index + pd.Timedelta(minutes=30)
    step_mid = real_idx + pd.Timedelta(minutes=step_min / 2)
    temp = np.interp(step_mid.asi8, t_mid.asi8, nasa["temp_c"].values)
    return pd.DataFrame({"ghi": ghi, "temp_c": temp, "ghi_clear": cs_step}, index=real_idx)


def nasa_weather(index: pd.DatetimeIndex, lat: float, lon: float, seed: int,
                 forced_cloudy_days=None) -> pd.DataFrame:
    """Real weather on the simulated index, in the schema of ``make_weather``.

    ``forced_cloudy_days`` is ignored: the real week has whatever sky it had.
    """
    step_min = int((index[1] - index[0]).total_seconds() // 60)
    spd = 1440 // step_min
    real_idx = to_real_dates(index)
    # one extra day before the window for the persistence forecast; for the first week of the
    # file there is no day before, so that week's first day is its own "yesterday"
    before = real_idx[0] - pd.Timedelta(days=1)
    if before < load_nasa().index[0].floor("D"):
        before = real_idx[0]
        ext = real_idx[:spd].append(real_idx)
    else:
        ext = pd.date_range(before, periods=len(index) + spd, freq=f"{step_min}min")
    w = _hourly_to_steps(ext, step_min, lat, lon)
    cz = cos_zenith(index, lat, lon)
    ghi_clear = clear_sky_ghi(cz)
    ghi = w["ghi"].values[spd:]
    csi = np.clip(np.divide(ghi, ghi_clear, out=np.zeros_like(ghi), where=ghi_clear > 20), 0, 1.1)

    # day-ahead forecast = persistence of yesterday's daily clear-sky index and temperature
    day_ghi = w["ghi"].values.reshape(-1, spd).sum(1)
    day_cs = w["ghi_clear"].values.reshape(-1, spd).sum(1)
    day_csi = np.clip(np.divide(day_ghi, day_cs, out=np.zeros_like(day_ghi), where=day_cs > 0), 0.05, 1.0)
    n_days = len(index) // spd
    csi_fc = np.repeat(day_csi[:n_days], spd)               # yesterday's value for each day
    temp_fc = w["temp_c"].values[:len(index)]               # same time yesterday
    regime = np.repeat(np.where(day_csi[1:n_days + 1] >= 0.75, 0, np.where(day_csi[1:n_days + 1] >= 0.5, 1, 2)), spd)

    syn = make_weather(index, lat, lon, seed)                # wind only (no wind in the NASA file)
    return pd.DataFrame({
        "cos_zenith": cz,
        "ghi_clear": ghi_clear,
        "csi": csi,
        "ghi": ghi,
        "temp_c": w["temp_c"].values[spd:],
        "wind_cf": syn["wind_cf"].values,
        "csi_fc": csi_fc,
        "ghi_fc": ghi_clear * csi_fc,
        "temp_fc": temp_fc,
        "wind_cf_fc": syn["wind_cf_fc"].values,
        "regime": regime,
    }, index=index)


def iex_price_curve(index: pd.DatetimeIndex) -> np.ndarray:
    """Real IEX DAM MCP (INR/kWh) on the simulated index (same calendar dates in 2025)."""
    iex = load_iex()
    real_idx = to_real_dates(index)
    missing = real_idx.difference(iex.index)
    if len(missing):
        raise ValueError(f"IEX file does not cover {missing[0]} .. {missing[-1]}")
    return iex["mcp_inr_kwh"].reindex(real_idx).values


def weather_for(sc, index: pd.DatetimeIndex, seed: int, forced_cloudy_days=None) -> pd.DataFrame:
    """The scenario's weather source: synthetic (default) or nasa_power."""
    simc = sc.raw["simulation"]
    src = simc.get("weather_source", "synthetic")
    fn = {"synthetic": make_weather, "nasa_power": nasa_weather}.get(src)
    if fn is None:
        raise ValueError(f"unknown simulation.weather_source {src!r}")
    return fn(index, simc["latitude_deg"], simc["longitude_deg"], seed, forced_cloudy_days=forced_cloudy_days)
