"""Low-voltage network study: solver, energy balance, and agreement with the MATLAB model."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gridsetu.lvnetwork import bfs, dt_thermal, load_params, network, run_case

ROOT = Path(__file__).resolve().parents[1]
MLIN, MLRES = ROOT / "outputs" / "matlab", ROOT / "matlab" / "results"


def test_bfs_matches_hand_calculation():
    """One load through one impedance: exact |V2| from the quadratic in |V2|^2."""
    v1, z, s = 1.0, complex(0.02, 0.04), complex(0.8, 0.3)
    b = 2 * (s.real * z.real + s.imag * z.imag) - v1 ** 2
    c = abs(z) ** 2 * abs(s) ** 2
    exact = np.sqrt((-b + np.sqrt(b * b - 4 * c)) / 2)
    net = {"parent": np.array([-1, 0]), "z": np.array([0j, z]), "v_src": v1}
    v, i_br, _ = bfs(net, np.array([0j, s]), tol=1e-12)
    assert abs(abs(v[1]) - exact) < 1e-9


def test_thermal_model_settles_to_steady_state():
    p = load_params()
    tr, th = p["transformer"], p["transformer"]["thermal"]
    n = 96 * 3
    _, hot, age = dt_thermal(np.full(n, 1.0), np.full(n, 30.0), np.ones(n, bool), p)
    assert abs(hot[-1] - (30 + tr["top_oil_rise_k"] + th["hotspot_gradient_k"])) < 0.05
    assert np.isclose(age[-1], 2 ** ((hot[-1] - 98) / 6), rtol=1e-3)


@pytest.fixture(scope="module")
def case():
    p = load_params()
    loads = pd.read_csv(MLIN / "f07_loads_stress_gridsetu.csv", index_col=0, parse_dates=True)
    feeder = pd.read_csv(MLIN / "f07_feeder_stress_gridsetu.csv", index_col=0, parse_dates=True)
    return p, feeder, run_case(loads, feeder, p, [0])


def test_power_into_transformer_is_import_plus_losses(case):
    _, feeder, df = case
    on = df["energized"] == 1
    lhs = df.loc[on, "p_dt_kw"]
    rhs = feeder.loc[on, "import_kw"] + df.loc[on, ["line_loss_kw", "dt_cu_loss_kw", "dt_nl_loss_kw"]].sum(axis=1)
    assert np.allclose(lhs, rhs, atol=1e-6)


def test_voltage_falls_along_every_circuit(case):
    p, _, df = case
    nbc = p["topology"]["buses_per_circuit"]
    on = df["energized"] == 1
    loaded = df.loc[on & (df["load_kw"] > 100)]
    for c in range(p["topology"]["circuits"]):
        cols = [f"v_bus_{c * nbc + k + 1:02d}" for k in range(nbc)]
        assert (np.diff(loaded[cols].to_numpy(), axis=1) <= 1e-12).all()


@pytest.mark.skipif(not (MLRES / "summary.json").exists(), reason="MATLAB results not present")
def test_matches_matlab_results():
    """The Python twin and matlab/run_f07.m agree on every case and every step."""
    p = load_params()
    ml = json.loads((MLRES / "summary.json").read_text(encoding="utf-8"))
    for week in ("stress", "representative"):
        for name, sc in p["scenarios"].items():
            loads = pd.read_csv(MLIN / f"f07_loads_{week}_{sc['variant']}.csv", index_col=0, parse_dates=True)
            feeder = pd.read_csv(MLIN / f"f07_feeder_{week}_{sc['variant']}.csv", index_col=0, parse_dates=True)
            py = run_case(loads, feeder, p, sc["storage_buses"])
            m = pd.read_csv(MLRES / f"f07_{week}_{name}_steps.csv", index_col=0)
            for col in ("v_min_pu", "line_loss_kw", "K", "theta_hotspot_c"):
                assert np.allclose(py[col].to_numpy(), m[col].to_numpy(), atol=1e-6, equal_nan=True), (week, name, col)
            assert ml[f"{week}_{name}"]["technical_loss_kwh"] == pytest.approx(
                (py["line_loss_kw"] + py["dt_cu_loss_kw"] + py["dt_nl_loss_kw"]).sum() * 0.25, abs=0.01)
