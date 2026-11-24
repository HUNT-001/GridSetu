"""Real household data file integrity and the synthetic statistics."""
import json
from pathlib import Path

import numpy as np

from gridsetu.householdcheck import EMARC, synthetic_stats


def test_emarc_summary_checks():
    d = json.loads(Path(EMARC).read_text(encoding="utf-8"))
    assert d["source"]["licence"] == "CC0 1.0" and d["source"]["doi"] == "10.7910/DVN/YJ5SP1"
    assert d["checks"]["complete_days"] == 61918 and d["checks"]["mainline_rows"] == 6138085
    g = d["groups"]["all|aug_oct"]
    assert len(g["profile"]) == 96
    # the mean daily energy must equal the integral of the mean profile
    assert abs(sum(g["profile"]) * 0.25 - g["daily_kwh_mean"]) < 0.01
    assert d["groups"]["urban|all_year"]["home_days"] + d["groups"]["nonurban|all_year"]["home_days"] == 61918


def test_synthetic_stats_on_a_known_case():
    hh = np.full((10, 96 * 2), 0.5)              # 10 homes, 2 days, flat 0.5 kW
    s = synthetic_stats(hh)
    assert s["daily_kwh_mean"] == 12.0 and s["evening_mean_kw"] == 0.5
    assert abs(s["evening_above_200w_share"] - 0.6) < 1e-9
    assert s["coincidence"] == 1.0 and s["profile_peak_over_mean"] == 1.0
