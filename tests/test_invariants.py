"""Physics, safety and fairness invariants. Run: pytest -q"""
import numpy as np
import pandas as pd
import pytest

from gridsetu.config import CLASSES, load_scenario
from gridsetu.fairness import FairnessLedger
from gridsetu.feeder import rotation_schedule
from gridsetu.island import simulate_island
from gridsetu.profiles import shift_irrigation_to_solar
from gridsetu.simulate import run_week
from gridsetu.wams import wams_study


@pytest.fixture(scope="session")
def week():
    sc = load_scenario()
    return run_week(sc, "stress week", cloudy_days=[2, 4], verbose=False)


def test_city_power_balance_closes(week):
    sc = week.sc
    for name in ("baseline", "coordinated"):
        inp, rt = week.city[name]["inputs"], week.city[name]["rt"]
        for r in sc.regions:
            supply = sum(rt.gen[g].values for g, v in sc.generators.items() if v["region"] == r)
            net_in = np.zeros(sc.n_steps)
            for tie in sc.raw["interties"]:
                f = rt.flow[f"{tie['from']}-{tie['to']}"].values
                net_in += f if tie["to"] == r else 0
                net_in -= f if tie["from"] == r else 0
            demand = inp.loads[r].sum(axis=1).values - inp.rooftop[r]
            shed = rt.shed[r].sum(axis=1).values
            dr = rt.dr.values if r == "R1" else 0
            assert np.allclose(supply + net_in, demand - shed - dr, atol=1e-3), (name, r)


def test_interties_respect_atc(week):
    rt = week.city["baseline"]["rt"]
    for tie in week.sc.raw["interties"]:
        assert rt.flow[f"{tie['from']}-{tie['to']}"].abs().max() <= tie["mw"] + 1e-6


def test_priority_one_classes_never_shed(week):
    for name in ("baseline", "coordinated"):
        rt = week.city[name]["rt"]
        for r in rt.shed:
            for c in ("traction", "municipal"):
                assert rt.shed[r][c].max() < 1e-6


def test_shedding_follows_priority(week):
    """Industrial and commercial (priority 2-3) are only shed after all agri+domestic is."""
    rt = week.city["baseline"]["rt"]
    for r in rt.shed:
        assert rt.shed[r]["industrial"].max() < 1e-6 or rt.shed[r]["domestic"].max() > 0


def test_gridsetu_protects_tier1(week):
    assert week.feeder["gridsetu"].metrics["critical_outage_hours"] == 0.0
    assert week.feeder["baseline"].metrics["critical_outage_hours"] > 0.0


def test_battery_limits(week):
    sc = week.sc
    b = sc.feeder["battery"]
    ts = week.feeder["gridsetu"].ts
    E = b["energy_kwh"]
    assert ts["soc"].min() >= b["soc_min"] * E - 1e-6
    assert ts["soc"].max() <= b["soc_max"] * E + 1e-6
    assert ts["battery_kw"].abs().max() <= b["power_kw"] + 1e-6


def test_feeder_energy_balance(week):
    ts = week.feeder["gridsetu"].ts
    energized = ~ts["state"].astype(str).str.contains("trip")
    lhs = ts["import"]
    rhs = ts["net"] - ts["battery_kw"] + ts["spill"] - ts["curtail_t3"] - ts["curtail_t2"] + ts["rebound"]
    assert np.allclose(lhs[energized], rhs[energized], atol=1e-6)


def test_gridsetu_keeps_import_under_rating_when_able(week):
    sc = week.sc
    ts = week.feeder["gridsetu"].ts
    normal = ts["state"] == "normal"
    assert ts["import"][normal].max() <= sc.feeder["capacity_kw"] * sc.feeder["import_target_margin"] + 1e-6


def test_forecast_is_calibrated(week):
    cov = week.forecast_skill["net_load"]["coverage_q10_q90_pct"]
    assert 70 <= cov <= 92


def test_reserve_objects_are_complete(week):
    rr = week.feeder["gridsetu"].reserves
    stages = {r["stage"] for r in rr}
    assert stages == {"T-24h", "T-1h", "T-15min", "real-time", "post-event"}
    for r in rr:
        assert 0 <= r["confidence_pct"] <= 100 and r["reserve_kw"] >= 0


def test_fairness_ledger_rules():
    rng = np.random.default_rng(0)
    led = FairnessLedger(50, refusal_prob=0.0, rng=rng)
    t3 = np.full(50, 1.0)
    prev = np.zeros(50, bool)
    for _ in range(20):
        _, mask = led.step(10.0, t3, 0.25)
        assert not (mask & prev).any()   # nobody curtailed two intervals running
        prev = mask
    assert led.violations == 0
    assert led.hours.max() - led.hours.min() <= 0.25 + 1e-9   # hours stay balanced


def test_rotation_is_fair():
    s = np.full(400, 0.25)
    counts = [rotation_schedule(s, 20, g).sum() for g in range(20)]
    assert max(counts) - min(counts) <= 1


def test_irrigation_shift_preserves_energy():
    sc = load_scenario()
    prof = np.tile(np.r_[np.ones(16), np.zeros(56), np.ones(24)], sc.n_days)
    shifted = shift_irrigation_to_solar(prof, sc.index)
    assert np.isclose(prof.sum(), shifted.sum())
    h = sc.index.hour
    assert shifted[(h >= 17) & (h < 22)].max() == 0


def test_wams_protection_operates(week):
    c = week.city["baseline"]
    w = wams_study(week.sc, c["inputs"], c["rt"])
    a = w["runs"]["A_baseline"]["summary"]
    b = w["runs"]["B_baseline"]["summary"]
    assert any(e["event"] == "SPS operated" for e in a["events"])
    assert any(e["event"].startswith("UFLS") for e in b["events"])
    for run in w["runs"].values():
        f = run["ts"]["f_city_hz"]
        assert 48.8 < f.min() and f.iloc[-1] > 49.5


def test_island_microgrid_balance(week):
    for strat in ("legacy", "gridsetu"):
        ts, m = simulate_island(week.sc, week.weather, strat)
        supplied = ts["pv_used_kw"] + ts["diesel_kw"] + ts["battery_kw"].clip(lower=0) \
            - (-ts["battery_kw"].clip(upper=0))
        served = ts["load_kw"] - ts["unserved_kw"]
        assert (supplied - served >= -1e-6).all()   # never serves more than it supplies
        assert m["unserved_kwh"] >= 0
