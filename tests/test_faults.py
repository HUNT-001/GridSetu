"""Fault study: hand checks and the committed result."""
import json
import math
from pathlib import Path

from gridsetu.faults import PARAMS, fault_currents, run_study

ROOT = Path(__file__).resolve().parents[1]


def _p():
    return json.loads(PARAMS.read_text(encoding="utf-8"))


def test_transformer_terminal_fault_matches_hand_calculation():
    p = _p()
    t = p["transformer"]
    i_rated = t["rating_kva"] * 1e3 / (math.sqrt(3) * p["v_nominal_ll_v"])
    hand = i_rated / (t["impedance_pct"] / 100)          # infinite source, c = 1, no K_T
    ik3 = fault_currents(p, 0)["ik3_max"]
    assert 0.85 * hand < ik3 < 1.1 * hand


def test_fault_current_falls_along_the_circuit_and_min_below_max():
    p = _p()
    prev = None
    for m in (0, 100, 300, 600):
        f = fault_currents(p, m)
        assert f["ik1_min"] < f["ik1_max"] <= f["ik3_max"] * 1.01
        if prev:
            assert f["ik3_max"] < prev["ik3_max"] and f["ik1_min"] < prev["ik1_min"]
        prev = f


def test_island_findings(tmp_path):
    r = run_study(tmp_path)
    isl = r["island_mode"]
    assert isl["fault_current_a"] < r["grid_mode"]["tail_ik1_min_a"]        # inverter-limited
    pump = isl["critical_legs"]["water_pumping"]
    assert not pump["island_fault_cleared_with_dol_start"]
    assert pump["island_fault_cleared_with_soft_start"]
    assert r["grid_mode"]["street_breaker"]["clears_every_street_fault_fast"]


def test_committed_result_is_reproducible(tmp_path):
    committed = json.loads((ROOT / "outputs" / "faults" / "faults.json").read_text(encoding="utf-8"))
    fresh = run_study(tmp_path)
    assert json.loads(json.dumps(fresh)) == committed
