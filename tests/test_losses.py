"""Pilot 11 kV feeder line losses from the AC power flow (network.py, runner.feeder_losses)."""
import numpy as np
import pandas as pd
import pytest

from gridsetu.config import load_scenario
from gridsetu.network import run_power_flow
from gridsetu.runner import feeder_losses
from gridsetu.simulate import run_week


def test_feeder_losses_arithmetic():
    pf = pd.DataFrame({"feeder_line_loss_mw": [0.001, 0.002, 0.0], "feeder_head_mw": [0.2, 0.3, -0.05]})
    r = feeder_losses(pf, h_per_sample=0.5)
    assert r["loss_kwh"] == pytest.approx(1.5)                 # 3 kW x 0.5 h
    assert r["energy_in_kwh"] == pytest.approx(250.0)          # reverse flow is not counted as energy in
    assert r["loss_pct"] == pytest.approx(0.6)


@pytest.fixture(scope="module")
def pf_pair():
    w = run_week(load_scenario(), "stress week", cloudy_days=[2, 4], verbose=False)
    c = w.city["baseline"]
    return {v: run_power_flow(w.sc, c["inputs"], c["rt"], w.feeder[v], every=24) for v in ("baseline", "gridsetu")}


def test_feeder_line_losses_are_small_and_positive(pf_pair):
    for v, pf in pf_pair.items():
        loss = pf["feeder_line_loss_mw"].to_numpy()
        assert np.all(loss >= -1e-9), v
        # I^2R on 6 km of 11 kV line carrying a few hundred kW: well under 2% of the power
        energized = pf["feeder_head_mw"] > 0.05
        assert (loss[energized] < 0.02 * pf["feeder_head_mw"][energized]).all(), v
        # the pilot's own sections are a small part of the whole city's losses
        assert (loss <= pf["losses_mw"].to_numpy() + 1e-9).all(), v
