"""Real-data validation: does the synthetic scenario hold up against real weather and prices?

    python -m gridsetu real-data            # writes outputs/real_data/

Four checks, all on the real data in ``data/real/`` (see docs/DATA_CARD.md):

1. Prices: the scenario's exchange price curve against IEX DAM prices for 14-20 Sep 2025.
2. Weather: the synthetic weather against NASA POWER for Coimbatore on the same 63 days
   (the simulated week plus its eight history weeks).
3. Forecast backtest: the feeder forecaster trained and tested on real weather, three
   consecutive test weeks, against the same procedure on synthetic weather.
4. The stress week re-run on real weather, and on real weather plus real IEX prices.

Household and enterprise load stays synthetic in every case; only weather and prices are
real. The headline results in README/numbers.json stay on the synthetic scenario.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config import load_scenario
from .forecast import FeederForecaster
from .market import exchange_price_curve
from .plots import AMBER, GREY, INK, MUTED, NAVY, TEAL, TEAL_LIGHT, _save, _sim_tag, _style
from .profiles import feeder_loads, history_weeks
from .realdata import load_iex, load_nasa, nasa_weather, weather_for
from .simulate import run_week
from .weather import make_weather

LABEL = "REAL weather (NASA POWER) and prices (IEX); household load is synthetic"
TAG = "Real data: NASA POWER (Coimbatore), IEX day-ahead market · household load synthetic"
STRESS_CLOUDY = [2, 4]               # as in simulate.stress_and_representative
VARIANTS = ("baseline", "gridsetu", "gridsetu_coordinated")
CAP_INR_KWH = 10.0


# ---------------------------------------------------------------- 1. prices
def price_stats(p: np.ndarray, index: pd.DatetimeIndex, cap: float = CAP_INR_KWH) -> dict:
    p = np.asarray(p, float)
    h = index.hour.values + index.minute.values / 60
    peak = (h >= 17) & (h < 23)          # IEX "peak" = hour blocks 18-23 = 17:00-23:00
    solar = (h >= 10) & (h < 16)
    at_cap = p >= cap - 1e-6
    days = pd.Series(at_cap, index=index).groupby(index.date).any()
    return {
        "mean_inr_kwh": round(float(p.mean()), 3),
        "peak_17_23_mean_inr_kwh": round(float(p[peak].mean()), 3),
        "solar_10_16_mean_inr_kwh": round(float(p[solar].mean()), 3),
        "max_inr_kwh": round(float(p.max()), 3),
        "min_inr_kwh": round(float(p.min()), 3),
        "blocks_at_cap": int(at_cap.sum()),
        "blocks_at_cap_pct": round(float(100 * at_cap.mean()), 1),
        "peak_blocks_at_cap_pct": round(float(100 * at_cap[peak].mean()), 1),
        "days_reaching_cap": int(days.sum()),
        "n_days": int(len(days)),
    }


def price_check(config_path=None) -> dict:
    sc = load_scenario(config_path)
    iex = load_scenario(config_path, {"exchange_price": {"source": "iex"}})
    return {"iex_2025_09_14_20": price_stats(exchange_price_curve(iex), sc.index),
            "scenario_curve": price_stats(exchange_price_curve(sc), sc.index)}


# ---------------------------------------------------------------- 2. weather
def _weeks(config_path=None):
    """The simulated week and its history weeks, as the simulator builds them."""
    sc = load_scenario(config_path)
    simc = sc.raw["simulation"]
    lat, lon = simc["latitude_deg"], simc["longitude_deg"]
    out = []
    for w in range(simc["history_weeks"], -1, -1):          # oldest first
        idx = sc.index - pd.Timedelta(days=7 * w)
        if w == 0:
            syn = make_weather(idx, lat, lon, sc.rng_seed, forced_cloudy_days=STRESS_CLOUDY)
            real = nasa_weather(idx, lat, lon, sc.rng_seed)
        else:
            syn = make_weather(idx, lat, lon, sc.rng_seed + 7919 * w)
            real = nasa_weather(idx, lat, lon, sc.rng_seed + 7919 * w)
        out.append((syn, real))
    return out, sc.dt_h


def weather_stats(frames: list[pd.DataFrame], dt_h: float) -> dict:
    w = pd.concat(frames)
    day = w.index.date
    ins = w["ghi"].groupby(day).sum() * dt_h / 1000                 # kWh/m2/day
    clear = w["ghi_clear"].groupby(day).sum() * dt_h / 1000
    dcsi = ins / clear
    t = w["temp_c"].groupby(day)
    return {
        "n_days": int(len(ins)),
        "insolation_kwh_m2_day_mean": round(float(ins.mean()), 2),
        "insolation_kwh_m2_day_p10": round(float(ins.quantile(0.1)), 2),
        "insolation_kwh_m2_day_p90": round(float(ins.quantile(0.9)), 2),
        "daily_clear_sky_index_mean": round(float(dcsi.mean()), 2),
        "overcast_days_pct": round(float(100 * (dcsi < 0.5).mean()), 1),
        "temp_mean_c": round(float(w["temp_c"].mean()), 1),
        "temp_daily_max_mean_c": round(float(t.max().mean()), 1),
        "temp_daily_min_mean_c": round(float(t.min().mean()), 1),
        "daily_insolation": [round(float(x), 3) for x in ins.values],
        "dates": [str(d) for d in ins.index],
    }


def weather_check(config_path=None) -> dict:
    weeks, dt_h = _weeks(config_path)
    nasa = load_nasa()
    return {"synthetic": weather_stats([s for s, _ in weeks], dt_h),
            "nasa_power": weather_stats([r for _, r in weeks], dt_h),
            "nasa_clear_sky_vs_model_pct": round(float(100 * (nasa["ghi_clearsky_wm2"].sum() /
                                                             _model_clear_sky_hourly_sum() - 1)), 1)}


def _model_clear_sky_hourly_sum() -> float:
    """Our clear-sky model over exactly the hours of the NASA file (to compare with NASA's)."""
    from .realdata import NASA_LAT, NASA_LON
    from .weather import clear_sky_ghi, cos_zenith
    nasa = load_nasa()
    fine = pd.date_range(nasa.index[0], periods=len(nasa) * 60, freq="1min")
    return float(clear_sky_ghi(cos_zenith(fine, NASA_LAT, NASA_LON)).reshape(-1, 60).mean(1).sum())


# ---------------------------------------------------------------- 3. forecast backtest
def backtest(config_path=None, n_test: int = 3, history: int = 6) -> dict:
    """Train on ``history`` weeks, forecast the next week; repeat for ``n_test`` weeks."""
    base = pd.Timestamp(load_scenario(config_path).raw["simulation"]["start"])
    weeks, bands = [], {}
    for src in ("synthetic", "nasa_power"):
        for k in range(n_test - 1, -1, -1):
            start = base - pd.Timedelta(days=7 * k)
            sc = load_scenario(config_path, {"simulation": {"start": start.strftime("%Y-%m-%d %H:%M"),
                                                            "weather_source": src, "history_weeks": history}})
            wx = weather_for(sc, sc.index, sc.rng_seed)
            fl, hh = feeder_loads(sc, wx, seed=sc.rng_seed + 5)
            hist = history_weeks(sc, hh, history)
            fc = FeederForecaster(sc.steps_per_day, seed=sc.rng_seed).fit(hist).predict(fl, last_history=hist[0])
            row = {"weather": src, "test_week_start": str(start.date())}
            for name, actual in (("net_load", fl.net_load), ("community_pv", fl.community_pv)):
                s = fc[name].skill(actual)
                row[name] = {"coverage_q10_q90_pct": round(s["coverage_q10_q90_pct"], 1),
                             "mape_q50_pct": round(s["mape_q50_pct"], 1),
                             "mae_q50_kw": round(s["mae_q50"], 2)}
            weeks.append(row)
            if k == 0:
                bands[src] = {"index": sc.index, "actual": fl.net_load, "q10": fc["net_load"].q10,
                              "q50": fc["net_load"].q50, "q90": fc["net_load"].q90}
    summary = {}
    for src in ("synthetic", "nasa_power"):
        rs = [r for r in weeks if r["weather"] == src]
        summary[src] = {name: {m: round(float(np.mean([r[name][m] for r in rs])), 1)
                               for m in ("coverage_q10_q90_pct", "mape_q50_pct")}
                        for name in ("net_load", "community_pv")}
    return {"history_weeks": history, "test_weeks": n_test, "weeks": weeks, "mean": summary}, bands


# ---------------------------------------------------------------- 4. stress week on real data
def stress_week_runs(config_path=None, verbose: bool = False) -> dict:
    cases = {
        "synthetic": ({}, STRESS_CLOUDY),
        "real_weather": ({"simulation": {"weather_source": "nasa_power"}}, None),
        "real_weather_and_prices": ({"simulation": {"weather_source": "nasa_power"},
                                     "exchange_price": {"source": "iex"}}, None),
    }
    out = {}
    for name, (over, cloudy) in cases.items():
        w = run_week(load_scenario(config_path, over), name, cloudy_days=cloudy, verbose=verbose)
        fs = w.forecast_skill["net_load"]
        out[name] = {
            "feeders": {v: {k: round(float(x), 3) for k, x in w.feeder[v].metrics.items()
                            if isinstance(x, (int, float, np.floating, np.integer))} for v in VARIANTS},
            "forecast_net_load": {"coverage_q10_q90_pct": round(fs["coverage_q10_q90_pct"], 1),
                                  "mape_q50_pct": round(fs["mape_q50_pct"], 1)},
        }
    return out


# ---------------------------------------------------------------- charts
def _charts(out: Path, config_path, weather: dict, bands: dict, bt_mean: dict) -> list[Path]:
    _style()
    charts = out / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    paths = []
    sc = load_scenario(config_path)
    iex = load_scenario(config_path, {"exchange_price": {"source": "iex"}})
    real_p, syn_p = exchange_price_curve(iex), exchange_price_curve(sc)
    x = pd.DatetimeIndex([t - pd.DateOffset(years=1) for t in sc.index])

    # IEX prices vs the scenario curve
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.axhline(CAP_INR_KWH, color=AMBER, lw=1.2, ls="--")
    ax.text(x[0], CAP_INR_KWH + 0.15, "IEX price ceiling ₹10/kWh", color=MUTED, fontsize=9)
    ax.plot(x, syn_p, color=GREY, lw=1.6, label="Scenario price curve (assumption)")
    ax.plot(x, real_p, color=NAVY, lw=1.4, label="IEX day-ahead clearing price, 14–20 Sep 2025 (real)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %d %b"))
    ax.set_ylabel("₹ per kWh")
    ax.set_ylim(0, 11)
    st = price_stats(real_p, sc.index)
    ax.set_title(f"Real prices reached the ₹10 ceiling on {st['days_reaching_cap']} of {st['n_days']} days "
                 f"({st['peak_blocks_at_cap_pct']:.0f}% of 17:00–23:00 blocks); our curve peaks at "
                 f"₹{syn_p.max():.1f}")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, frameon=False)
    _sim_tag(fig, "Source: IEX DAM market snapshot, 15-minute blocks, all-India MCP")
    paths.append(_save(fig, charts / "iex_prices_vs_scenario.png"))

    # daily insolation, real vs synthetic
    s, r = weather["synthetic"], weather["nasa_power"]
    d = pd.DatetimeIndex([t - pd.DateOffset(years=1) for t in pd.to_datetime(r["dates"])])
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(d, s["daily_insolation"], color=GREY, lw=1.6, marker="o", ms=3, label="Synthetic weather (simulator)")
    ax.plot(d, r["daily_insolation"], color=TEAL, lw=1.8, marker="o", ms=3, label="NASA POWER, Coimbatore (real)")
    ax.axvspan(d[-7], d[-1] + pd.Timedelta(hours=23), color=TEAL_LIGHT, alpha=0.25, lw=0)
    ax.text(d[-7], 7.6, " simulated week", color=MUTED, fontsize=9, va="top")
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.SU))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.set_ylabel("Solar energy, kWh per m² per day")
    ax.set_ylim(0, 8)
    ax.set_title(f"Real monsoon sunshine: {r['insolation_kwh_m2_day_mean']:.1f} kWh/m²/day vs "
                 f"{s['insolation_kwh_m2_day_mean']:.1f} in our synthetic weather")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, frameon=False)
    _sim_tag(fig, "20 Jul to 20 Sep 2025: the simulated week and its eight training weeks (2026 maps to the same dates in 2025)")
    paths.append(_save(fig, charts / "weather_real_vs_synthetic.png"))

    # graph 10: forecast backtest band on real weather
    b = bands["nasa_power"]
    bx = pd.DatetimeIndex([t - pd.DateOffset(years=1) for t in b["index"]])
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.fill_between(bx, b["q10"], b["q90"], color=TEAL_LIGHT, alpha=0.6, lw=0, label="Forecast range (q10–q90)")
    ax.plot(bx, b["q50"], color=TEAL, lw=1.3, label="Forecast median")
    ax.plot(bx, b["actual"], color=INK, lw=1.0, label="Actual net load")
    cov = float(100 * np.mean((b["actual"] >= b["q10"]) & (b["actual"] <= b["q90"])))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %d %b"))
    ax.set_ylabel("Feeder net load, kW")
    m = bt_mean["nasa_power"]["net_load"]["coverage_q10_q90_pct"]
    ax.set_title(f"Day-ahead forecast on real weather: actual inside the 80% range {cov:.0f}% of the time "
                 f"(3-week mean {m:.0f}%)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, frameon=False)
    _sim_tag(fig, TAG)
    paths.append(_save(fig, charts / "forecast_backtest_real_weather.png"))
    return paths


def run_study(out_dir: str | Path = "outputs/real_data", config_path=None, verbose: bool = True) -> dict:
    log = print if verbose else (lambda *a, **k: None)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    log("prices: IEX vs scenario curve ...")
    prices = price_check(config_path)
    log("weather: NASA POWER vs synthetic, 63 days ...")
    weather = weather_check(config_path)
    log("forecast backtest: 3 test weeks x 2 weather sources ...")
    bt, bands = backtest(config_path)
    log("stress week on synthetic, real weather, real weather + IEX prices ...")
    runs = stress_week_runs(config_path)
    res = {"about": {"label": LABEL,
                     "real": ["GHI and air temperature: NASA POWER hourly, Coimbatore",
                              "exchange price: IEX DAM 15-minute MCP, 14-20 Sep 2025"],
                     "synthetic": ["household, enterprise and critical load", "wind", "city generation and outage"],
                     "date_mapping": "simulated 2026 dates = the same calendar dates in 2025",
                     "weather_forecast_on_real_data": "persistence (yesterday's real weather)"},
           "prices": prices, "weather": weather, "forecast_backtest": bt, "stress_week": runs}
    (out / "real_data.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    _charts(out, config_path, weather, bands, bt["mean"])
    return res
