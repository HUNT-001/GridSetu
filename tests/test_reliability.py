"""SAIDI, SAIFI, CAIDI and evening availability (reliability.py) and their place in the run."""
import numpy as np
import pytest

from gridsetu.config import load_scenario
from gridsetu.reliability import interruption_counts, reliability_indices
from gridsetu.runner import monthly_composite
from gridsetu.simulate import run_week


def _status(cols):
    """Build [step][household] from per-household strings: '.' supplied, 'x' dark, 'l' lifeline, 'c' curtailed."""
    code = {".": 0, "c": 1, "x": 2, "l": 3}
    return np.array([[code[ch] for ch in col] for col in cols], dtype=np.uint8).T


def test_interruptions_count_runs_of_dark_steps():
    st = _status(["..xx..x.", "xx......", "........", "xxxxxxxx"])
    assert interruption_counts(st).tolist() == [2, 1, 0, 1]


def test_lifeline_and_curtailment_are_not_interruptions():
    st = _status(["llll", "cccc", "lxl."])
    assert interruption_counts(st).tolist() == [0, 0, 1]


def test_indices_by_hand():
    # 2 homes, 8 steps of 0.25 h; evening = last 4 steps
    st = _status(["..xx..x.", "........"])
    ev = np.array([0, 0, 0, 0, 1, 1, 1, 1], bool)
    r = reliability_indices(st, 0.25, ev)
    assert r["saidi_h"] == pytest.approx(3 * 0.25 / 2)          # 3 dark steps over 2 homes
    assert r["saifi"] == pytest.approx(2 / 2)                   # 2 interruptions over 2 homes
    assert r["caidi_h"] == pytest.approx(0.375)
    assert r["evening_supply_availability_pct"] == pytest.approx(100 * (1 - 1 / 8))
    assert r["evening_dark_home_hours"] == pytest.approx(0.25)


def test_no_outage_gives_full_availability():
    r = reliability_indices(np.zeros((10, 5), np.uint8), 0.25, np.ones(10, bool))
    assert r["saidi_h"] == 0 and r["saifi"] == 0 and r["caidi_h"] == 0
    assert r["evening_supply_availability_pct"] == 100


def test_composite_month_adds_weeks_and_averages_availability():
    wk = {"saidi_h": 1.0, "saifi": 2.0, "customer_interruptions": 10, "evening_dark_home_hours": 5.0,
          "evening_supply_availability_pct": 90.0, "feeder_peak_import_kw": 1, "solar_utilisation_pct": 1}
    from gridsetu.runner import ADDITIVE
    base = {k: 0.0 for k in ADDITIVE}
    stress = {**base, **wk}
    rep = {**base, **wk, "saidi_h": 0.0, "saifi": 0.0, "evening_supply_availability_pct": 100.0}
    m = monthly_composite(stress, rep)
    assert m["saidi_h"] == pytest.approx(1.0) and m["saifi"] == pytest.approx(2.0)
    assert m["caidi_h"] == pytest.approx(0.5)
    assert m["evening_supply_availability_pct"] == pytest.approx((3 * 100 + 90) / 4)


@pytest.fixture(scope="module")
def week():
    return run_week(load_scenario(), "stress week", cloudy_days=[2, 4], verbose=False)


def test_feeder_metrics_carry_the_indices(week):
    n_hh = week.feeder_loads.hh_load.shape[0]
    for v in ("baseline", "gridsetu"):
        m = week.feeder[v].metrics
        assert m["customers"] == n_hh
        # SAIDI is the existing dark home-hours spread over the homes
        assert m["saidi_h"] == pytest.approx(m["dark_home_hours"] / n_hh)
        assert 0 <= m["evening_supply_availability_pct"] <= 100
        assert m["saifi"] >= 0


def test_gridsetu_does_not_worsen_saidi_on_the_stress_week(week):
    b, g = week.feeder["baseline"].metrics, week.feeder["gridsetu"].metrics
    assert g["saidi_h"] <= b["saidi_h"]
    assert g["evening_supply_availability_pct"] >= b["evening_supply_availability_pct"]
