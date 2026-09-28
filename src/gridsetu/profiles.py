"""Load profiles for the six consumer classes (city scale, MW) and the household-level
pilot feeder (kW). Shapes are typical Indian monsoon-season daily curves; all are
ENGINEERING ASSUMPTIONS, not DISCOM telemetry."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import CLASSES, Scenario
from .weather import make_weather, pv_power

# Hourly shapes normalised to a peak of 1.0 (index = hour of day).
HOURLY_SHAPES = {
    "domestic":   [.45, .40, .37, .36, .38, .50, .66, .70, .62, .52, .48, .47,
                   .50, .52, .50, .48, .52, .65, .88, 1.0, .98, .90, .75, .58],
    "commercial": [.25, .22, .20, .20, .20, .22, .28, .38, .50, .70, .85, .92,
                   .95, .93, .95, .95, .95, .97, 1.0, 1.0, .92, .75, .50, .35],
    "industrial": [.80, .80, .78, .78, .78, .80, .85, .90, .95, .98, 1.0, 1.0,
                   .95, .97, 1.0, 1.0, .98, .95, .92, .90, .88, .86, .84, .82],
    "municipal":  [.55, .55, .55, .55, .70, 1.0, 1.0, .90, .50, .30, .30, .30,
                   .30, .30, .30, .30, .40, .80, .95, .80, .60, .55, .55, .55],
    # legacy Tamil Nadu style agri schedule: night block + evening block of 3-phase supply
    "irrigation": [.95, .95, .95, .95, .20, .20, .10, .10, .10, .10, .10, .10,
                   .10, .10, .10, .90, .90, .90, .90, .90, .20, .20, .95, .95],
    "traction":   [.30, .25, .25, .25, .35, .55, .75, .90, .95, .85, .60, .55,
                   .55, .55, .55, .60, .75, .90, 1.0, .95, .80, .60, .45, .35],
}
WEEKDAY_FACTOR = {  # Mon..Sun
    "domestic":   [1, 1, 1, 1, 1, 1.02, 1.04],
    "commercial": [1, 1, 1, 1, 1, 0.95, 0.72],
    "industrial": [1, 1, 1, 1, 1, 0.92, 0.75],
    "municipal":  [1] * 7,
    "irrigation": [1] * 7,
    "traction":   [1, 1, 1, 1, 1, 0.85, 0.75],
}
SOLAR_WINDOW = (8.0, 17.0)  # hours used when irrigation is shifted to solar hours


def hourly_to_steps(hourly: list[float], index: pd.DatetimeIndex) -> np.ndarray:
    hours = index.hour.values + index.minute.values / 60
    xp = np.arange(25)
    fp = list(hourly) + [hourly[0]]
    return np.interp(hours, xp, fp)


def _ar1(rng, n, phi, sigma):
    x = np.zeros(n)
    e = rng.normal(0, sigma, n)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    return x


def shift_irrigation_to_solar(profile: np.ndarray, index: pd.DatetimeIndex) -> np.ndarray:
    """Energy-preserving reschedule of each day's pumping into solar hours (cap 1.0 p.u.
    of the day's own peak), with any remainder moved to the night block, never the evening."""
    out = np.zeros_like(profile)
    hours = index.hour.values + index.minute.values / 60
    day = (index - index[0]).days
    for d in np.unique(day):
        m = day == d
        p = profile[m]
        h = hours[m]
        energy = p.sum()
        peak = p.max() if p.max() > 0 else 1.0
        solar = (h >= SOLAR_WINDOW[0]) & (h < SOLAR_WINDOW[1])
        night = (h >= 22) | (h < 5)
        new = np.zeros_like(p)
        fill = min(energy, peak * solar.sum())
        new[solar] = fill / solar.sum()
        rest = energy - fill
        if rest > 0:
            new[night] += rest / night.sum()
        out[m] = new
    return out


def city_class_loads(sc: Scenario, weather: pd.DataFrame, shifted_irrigation: bool = False,
                     seed_salt: int = 0) -> dict[str, pd.DataFrame]:
    """Per-region DataFrame of class loads in MW (columns = classes)."""
    idx = sc.index
    n = len(idx)
    temp = weather["temp_c"].values
    dow = idx.dayofweek.values
    out = {}
    for r_i, (rid, reg) in enumerate(sc.regions.items()):
        rng = np.random.default_rng(sc.rng_seed + 1000 * (r_i + 1) + seed_salt)
        cols = {}
        for c in CLASSES:
            peak = float(reg["peak_mw"].get(c, 0))
            if peak <= 0:
                cols[c] = np.zeros(n)
                continue
            shape = hourly_to_steps(HOURLY_SHAPES[c], idx)
            wk = np.array(WEEKDAY_FACTOR[c])[dow]
            day_mult = 1 + rng.normal(0, 0.02, sc.n_days).repeat(sc.steps_per_day)[:n]
            noise = 1 + _ar1(rng, n, 0.85, 0.012)
            ts = sc.classes[c]["temp_sensitivity"]
            temp_mult = 1 + ts * (temp - 27.0)
            prof = shape * wk * day_mult * noise * temp_mult
            if c == "traction":  # train pulses on top of the base
                pulses = rng.poisson(0.35, n) * rng.uniform(0.05, 0.15, n)
                prof = prof + pulses * (shape > 0.4)
            if c == "irrigation" and shifted_irrigation:
                prof = shift_irrigation_to_solar(prof, idx)
            cols[c] = np.clip(prof, 0, None) * peak
        out[rid] = pd.DataFrame(cols, index=idx)
    return out


def region_rooftop_pv(sc: Scenario, weather: pd.DataFrame, forecast: bool = False) -> dict:
    ghi = weather["ghi_fc" if forecast else "ghi"].values
    t = weather["temp_fc" if forecast else "temp_c"].values
    return {rid: pv_power(ghi, t, float(reg.get("rooftop_solar_mwp", 0)))
            for rid, reg in sc.regions.items()}


# ------------------------------------------------------------------ pilot feeder
@dataclass
class FeederLoads:
    index: pd.DatetimeIndex
    hh_load: np.ndarray          # (n_hh, T) kW, total household load
    hh_tier3: np.ndarray         # (n_hh, T) kW, flexible portion (subset of hh_load)
    ent_load: np.ndarray         # (n_ent, T) kW
    ent_tier2: np.ndarray        # (n_ent, T) kW, shiftable motor load (subset)
    ent_optin: np.ndarray        # (n_ent,) bool
    critical: dict               # name -> (T,) kW   Tier 1
    rooftop_pv: np.ndarray       # (T,) kW behind the meter
    community_pv: np.ndarray     # (T,) kW at the battery site
    weather: pd.DataFrame

    @property
    def tier1(self) -> np.ndarray:
        return np.sum(list(self.critical.values()), axis=0)

    @property
    def tier2(self) -> np.ndarray:
        return (self.ent_tier2 * self.ent_optin[:, None]).sum(axis=0)

    @property
    def tier3(self) -> np.ndarray:
        return self.hh_tier3.sum(axis=0)

    @property
    def gross_load(self) -> np.ndarray:
        return self.hh_load.sum(axis=0) + self.ent_load.sum(axis=0) + self.tier1

    @property
    def net_load(self) -> np.ndarray:
        """Load seen at the feeder head after behind-the-meter rooftop PV (can be < 0)."""
        return self.gross_load - self.rooftop_pv


def _critical_profiles(idx: pd.DatetimeIndex, kw: dict) -> dict:
    h = idx.hour.values + idx.minute.values / 60
    weekday = idx.dayofweek.values < 5
    health = np.where((h >= 8) & (h < 18), 1.0, 0.6) * kw["health_subcentre"]
    school = np.where(weekday & (h >= 8.5) & (h < 16), 1.0, 0.15) * kw["school"]
    pump = np.where(((h >= 5) & (h < 8)) | ((h >= 17) & (h < 19)), 1.0, 0.0) * kw["water_pumping"]
    lights = np.where((h >= 18) | (h < 6), 1.0, 0.0) * kw["street_lighting_core"]
    return {"health_subcentre": health, "school": school,
            "water_pumping": pump, "street_lighting_core": lights}


def feeder_loads(sc: Scenario, weather: pd.DataFrame, seed: int, hh_scale: float | None = None,
                 index: pd.DatetimeIndex | None = None) -> tuple[FeederLoads, float]:
    """Household-level pilot feeder. Returns loads and the household scale factor used
    (calibrated so the gross feeder peak equals target_peak_kw when hh_scale is None)."""
    f = sc.feeder
    idx = index if index is not None else sc.index
    n = len(idx)
    rng = np.random.default_rng(seed)
    n_hh, n_ent = int(f["households"]), int(f["micro_enterprises"])
    hours = idx.hour.values + idx.minute.values / 60
    temp = weather["temp_c"].values

    # households: shared shape, individual time shift, size and noise
    base = np.array(HOURLY_SHAPES["domestic"])
    size = rng.lognormal(0, 0.35, n_hh)
    shift_h = rng.normal(0, 0.5, n_hh)
    hh = np.empty((n_hh, n))
    for i in range(n_hh):
        hh[i] = np.interp((hours - shift_h[i]) % 24, np.arange(25), list(base) + [base[0]])
    hh *= size[:, None]
    hh *= 1 + 0.02 * (temp[None, :] - 27)
    hh *= np.clip(1 + rng.normal(0, 0.12, (n_hh, n)), 0.3, None)
    evening = (hours >= 17) & (hours < 23)
    t3_frac = f["tier3_share_of_household"] * np.where(evening, 1.4, 0.8)

    # micro-enterprises: 09-19 working day, lunch dip, closed Sunday
    ent_shape = np.where((hours >= 9) & (hours < 19), 1.0, 0.08)
    ent_shape = ent_shape * np.where((hours >= 13) & (hours < 14), 0.6, 1.0)
    ent_shape = ent_shape * np.where(idx.dayofweek.values == 6, 0.2, 1.0)
    ent_size = rng.uniform(0.8, 2.4, n_ent)
    ent = ent_size[:, None] * ent_shape[None, :] * np.clip(1 + rng.normal(0, 0.15, (n_ent, n)), 0, None)
    ent_optin = rng.random(n_ent) < f["opt_in_share_tier2"]

    critical = _critical_profiles(idx, f["critical_loads_kw"])
    tier1 = np.sum(list(critical.values()), axis=0)

    if hh_scale is None:
        # calibrate household scale so the coincident gross peak hits the target
        other = ent.sum(axis=0) + tier1
        hh_sum = hh.sum(axis=0)
        lo, hi = 0.01, 5.0
        for _ in range(60):
            mid = (lo + hi) / 2
            if (mid * hh_sum + other).max() > f["target_peak_kw"]:
                hi = mid
            else:
                lo = mid
        hh_scale = (lo + hi) / 2
    hh *= hh_scale
    hh_t3 = hh * t3_frac[None, :]

    rooftop = pv_power(weather["ghi"].values, temp, f["rooftop_solar_kwp"])
    community = pv_power(weather["ghi"].values, temp, f["community_solar_kwp"])
    return FeederLoads(idx, hh, hh_t3, ent, ent * 0.5, ent_optin, critical,
                       rooftop, community, weather), hh_scale


def history_weeks(sc: Scenario, hh_scale: float, n_weeks: int):
    """Synthetic past weeks (different weather/load seeds) used to train forecasters."""
    lat = sc.raw["simulation"]["latitude_deg"]
    lon = sc.raw["simulation"]["longitude_deg"]
    weeks = []
    for w in range(1, n_weeks + 1):
        idx = sc.index - pd.Timedelta(days=7 * w)
        wx = make_weather(idx, lat, lon, seed=sc.rng_seed + 7919 * w)
        fl, _ = feeder_loads(sc, wx, seed=sc.rng_seed + 104729 * w, hh_scale=hh_scale, index=idx)
        weeks.append(fl)
    return weeks
