"""Real data: files match their published checks, and the weather/price switches are safe."""
import numpy as np
import pandas as pd

from gridsetu.config import load_scenario
from gridsetu.market import exchange_price_curve
from gridsetu.realdata import load_iex, load_nasa, nasa_weather, weather_for
from gridsetu.weather import clear_sky_ghi, cos_zenith, make_weather

# IEX's own published daily average MCP (Rs/MWh), market snapshot summary table
IEX_DAILY_AVG = {"2025-09-14": 2549.69, "2025-09-15": 4212.69, "2025-09-16": 3925.75, "2025-09-17": 4095.84,
                 "2025-09-18": 4090.40, "2025-09-19": 4055.43, "2025-09-20": 4160.89}
IDX = pd.date_range("2026-09-14", periods=672, freq="15min")


def test_iex_file_matches_iex_daily_averages():
    d = load_iex()
    assert len(d) == 672 and d.index.is_unique
    daily = d["mcp_rs_per_mwh"].groupby(d.index.strftime("%Y-%m-%d")).mean()
    for day, avg in IEX_DAILY_AVG.items():
        assert abs(daily[day] - avg) < 0.006, day
    assert d["mcp_rs_per_mwh"].max() == 10000.0          # the exchange price ceiling


def test_nasa_file_complete_and_clock_offset():
    n = load_nasa()
    assert len(n) == 1536 and n.index.is_unique
    assert (n["ghi_allsky_wm2"] <= n["ghi_clearsky_wm2"] + 1).all()
    # NASA "LST" = UTC+5: IST = LST + 30 min gives the best fit to solar geometry
    def corr(off):
        fine = pd.date_range(n.index[0] - pd.Timedelta(minutes=30) + pd.Timedelta(minutes=off),
                             periods=len(n) * 60, freq="1min")
        cs = clear_sky_ghi(cos_zenith(fine, 11.02, 76.96)).reshape(-1, 60).mean(1)
        return np.corrcoef(cs, n["ghi_clearsky_wm2"].values)[0, 1]
    assert corr(30) > corr(0) and corr(30) > corr(60) and corr(30) > 0.99


def test_nasa_weather_keeps_hourly_energy_and_schema():
    w = nasa_weather(IDX, 11.0, 76.96, 42)
    syn = make_weather(IDX, 11.0, 76.96, 42)
    assert list(w.columns) == list(syn.columns) and not w.isna().any().any()
    n = load_nasa()
    n = n[(n.index >= "2025-09-14 00:30") & (n.index < "2025-09-21 00:30")]
    # the half hour 00:00-00:30 on 14 Sep is night, so the totals must agree exactly
    assert abs(w["ghi"].sum() * 0.25 - n["ghi_allsky_wm2"].sum()) < 1e-6 * n["ghi_allsky_wm2"].sum()
    # persistence forecast: day d uses day d-1's temperature
    assert np.allclose(w["temp_fc"].values[96:], w["temp_c"].values[:-96])


def test_default_sources_unchanged():
    sc = load_scenario()
    assert sc.raw["simulation"]["weather_source"] == "synthetic"
    a = weather_for(sc, sc.index, sc.rng_seed, forced_cloudy_days=[2, 4])
    b = make_weather(sc.index, 11.0, 76.96, sc.rng_seed, forced_cloudy_days=[2, 4])
    pd.testing.assert_frame_equal(a, b)
    iex = load_scenario(None, {"exchange_price": {"source": "iex"}})
    p = exchange_price_curve(iex)
    assert abs(p.mean() * 1000 - np.mean(list(IEX_DAILY_AVG.values()))) < 0.01
    assert not np.allclose(exchange_price_curve(sc), p)
