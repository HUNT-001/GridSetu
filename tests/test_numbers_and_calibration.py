"""The numbers registry and the reserve-calibration scoring."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from gridsetu.calibration import score, window_outcomes
from gridsetu.numbers import _pct_change, build_numbers, check_files

ROOT = Path(__file__).resolve().parents[1]


def _copy_results(tmp_path):
    (tmp_path / "results.json").write_text((ROOT / "outputs" / "results.json").read_text(encoding="utf-8"),
                                           encoding="utf-8")


def test_numbers_registry_matches_readme(tmp_path):
    _copy_results(tmp_path)
    doc = build_numbers(tmp_path)
    figs = doc["figures"]
    assert figs["pilot.gridsetu.critical_outage_h"]["value"] == 0.0
    assert all(f["source"] for f in figs.values())
    assert check_files(tmp_path, [str(ROOT / "README.md")]) == []


def test_checker_catches_a_drifted_figure(tmp_path):
    _copy_results(tmp_path)
    doc = build_numbers(tmp_path)
    target = doc["figures"]["pilot.baseline.evening_unserved_kwh"]["display"]
    page = tmp_path / "doc.md"
    page.write_text("Evening unserved energy fell from 9,999 kWh.", encoding="utf-8")
    assert any(target in p for p in check_files(tmp_path, [str(page)]))


def test_pct_change_uses_true_minus_sign():
    assert _pct_change(100, 20) == "−80%"
    assert _pct_change(100, 110) == "+10%"


def _fake_feeder(states, imports, limits, conf=99.0):
    idx = pd.date_range("2026-09-14 17:30", periods=len(states), freq="15min")
    ts = pd.DataFrame({"state": states, "import": imports, "limit": limits}, index=idx)
    res = {"stage": "T-15min", "window_start": str(idx[0]),
           "window_end": str(idx[-1] + pd.Timedelta(minutes=15)), "confidence_pct": conf, "reserve_kw": 100.0}
    return SimpleNamespace(ts=ts, reserves=[res])


def test_window_held_when_import_stays_under_limit():
    fr = _fake_feeder(["normal"] * 8, [280.0] * 8, [291.0] * 8)
    row = window_outcomes(fr, "stress", 42)[0]
    assert row["held"] and row["end_to_end"] and row["own_peak_held"]


def test_window_fails_on_residual_overload_or_shortfall_trip():
    over = _fake_feeder(["normal"] * 8, [280.0] * 7 + [300.0], [291.0] * 8)
    assert not window_outcomes(over, "stress", 42)[0]["held"]
    trip = _fake_feeder(["cap"] * 7 + ["cap_shortfall_trip"], [200.0] * 7 + [0.0], [210.0] * 7 + [0.0])
    assert not window_outcomes(trip, "stress", 42)[0]["held"]


def test_lost_protection_message_counts_only_end_to_end():
    fr = _fake_feeder(["normal"] * 7 + ["sps_trip+island"], [280.0] * 7 + [0.0], [291.0] * 7 + [0.0])
    row = window_outcomes(fr, "stress", 42)[0]
    assert row["held"] and not row["end_to_end"]


def test_sps_call_is_not_counted_against_own_peak():
    fr = _fake_feeder(["normal"] * 6 + ["sps_relief"] * 2, [250.0] * 6 + [150.0] * 2, [291.0] * 6 + [0.0] * 2)
    fr.ts["relief_requested"] = 0.0
    row = window_outcomes(fr, "stress", 42)[0]
    assert row["own_peak_held"] and not row["held"]


def test_brier_and_reliability_table():
    df = pd.DataFrame({"confidence_pct": [99.0] * 10 + [60.0] * 10,
                       "held": [True] * 9 + [False] + [True] * 6 + [False] * 4})
    s = score(df)
    assert s["n_forecasts"] == 20
    assert s["observed_when_stated_ge_99_pct"] == 90.0
    expected = np.mean([(0.99 - 1) ** 2] * 9 + [0.99 ** 2] + [(0.6 - 1) ** 2] * 6 + [0.6 ** 2] * 4)
    assert abs(s["brier"] - round(expected, 4)) < 1e-9
