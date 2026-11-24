"""Lifeline mode and the second (DISCOM call) confidence."""
import numpy as np

from gridsetu.feeder import _lifeline, _lifeline_headroom_forecast


def test_lifeline_removes_what_is_needed_with_one_common_limit():
    rng = np.random.default_rng(0)
    load = rng.uniform(0.05, 1.5, 400)
    need = 120.0
    removed, dark = _lifeline(load, need, 0.2, 0.0, rng)          # nobody exceeds the cap
    assert not dark.any()
    assert removed >= need - 1e-6
    assert removed <= need + 1.0                                  # limit found by bisection, no overshoot
    # every home keeps at least min(own load, the floor)
    removed_small, _ = _lifeline(load, 1e9, 0.2, 0.0, rng)
    assert np.isclose(removed_small, np.maximum(load - 0.2, 0).sum())


def test_lifeline_meter_trips_only_hit_limited_homes():
    rng = np.random.default_rng(1)
    load = np.r_[np.full(100, 0.1), np.full(100, 1.0)]
    _, dark = _lifeline(load, 50.0, 0.2, 0.5, rng)
    assert not dark[:100].any()                                   # homes under the cap never trip
    assert dark[100:].any()


def test_headroom_forecast_uses_only_the_past():
    spd = 4
    hh = np.arange(3 * 2 * spd, dtype=float).reshape(3, 2 * spd)  # 3 homes, 2 days of 4 steps

    class FL:
        hh_load = hh

    class Hist:
        hh_load = np.full((3, 2 * spd), 5.0)

    h = _lifeline_headroom_forecast(FL, Hist, spd, 0.0)
    assert np.allclose(h[spd:], hh[:, :spd].sum(axis=0))          # day 2 = day 1 loads
    assert np.allclose(h[:spd], 15.0)                             # day 1 = last history day


def test_reserves_publish_call_capacity_and_confidence():
    from gridsetu.config import load_scenario
    from gridsetu.simulate import run_week
    sc = load_scenario(None, {"simulation": {"days": 2}})
    w = run_week(sc, "test", verbose=False)
    rs = w.feeder["gridsetu"].reserves
    assert rs and all(r["call_capacity_kw"] is not None and r["call_capacity_kw"] > 0 for r in rs)
    assert all(0 <= r["call_confidence_pct"] <= 100 for r in rs)
    assert all(r["call_capacity_kw"] >= r["tier2_kw"] for r in rs)  # lifeline adds to load flexibility
    m = w.feeder["gridsetu"].metrics
    assert m["critical_outage_hours"] == 0.0
    assert m["dark_home_hours"] <= w.feeder["baseline"].metrics["dark_home_hours"]
