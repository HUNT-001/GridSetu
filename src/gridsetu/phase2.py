"""Phase 2 city studies written to outputs/, so their README figures have a committed source.

    python -m gridsetu phase2                # writes outputs/phase2/phase2.json

Until now the 20-feeder fleet and the unit-commitment results lived only in the API's run cache.
This runs the same studies on the same seed as the reference run (seed 42, the first seed of
``python -m gridsetu run``) and keeps the summaries, without the per-step series.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .simulate import stress_and_representative

SEED = 42


def _fleet(week) -> dict:
    from .fleet import run_fleet
    r = run_fleet(week)
    n = len(r["feeders"])
    overloaded = sum(1 for f in r["feeders"] if f["peak_kw"] / f["rating_kw"] > 1.0)   # as fleet.py ranks them
    return {"n_feeders": n, "homes": int(sum(f["households"] for f in r["feeders"])),
            "feeders_overloaded_at_peak": overloaded, "curve": r["curve"], "feeders": r["feeders"], "note": r["note"]}


def _uc(week) -> dict:
    from .uc import lp_cost, run_uc
    c = week.city["baseline"]
    u = run_uc(week.sc, c["inputs"])
    lp = lp_cost(week.sc, c["inputs"], c["da"])
    dt = week.sc.dt_h
    gas = [g for g, v in week.sc.generators.items() if v["kind"] == "gas"]
    return {"startups": {g: int(v) for g, v in u.startups.items()},
            "hours_on_uc": {g: float(u.status[g].sum() * dt) for g in u.status},
            "hours_on_lp": {g: float((c["da"].gen[g] > 0.1).sum() * dt) for g in gas},   # > 0.1 MW, as the UC card
            "shed_uc_mwh": float(u.shed.sum() * dt),
            "shed_lp_mwh": float(sum(c["da"].shed[r].sum().sum() for r in c["da"].shed) * dt),
            "cost_uc_inr": {k: float(v) for k, v in u.cost_inr.items()},
            "cost_lp_inr": {k: float(v) for k, v in lp.items()},
            "note": "Day-ahead schedules on the forecast. Ramp limits are left out of the commitment problem."}


def run_studies(out_dir: str | Path = "outputs/phase2", config_path=None, verbose: bool = True) -> dict:
    t0 = time.time()
    log = print if verbose else (lambda *a, **k: None)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    res = stress_and_representative(config_path, {"simulation": {"seed": SEED}}, verbose=False)
    doc = {"about": {"label": "SIMULATION: synthetic data, not field measurement", "seed": SEED,
                     "runtime_s": None},
           "fleet": {}, "uc": {}}
    for wk in ("stress", "representative"):
        log(f"Fleet, {wk} week: 20 feeders under baseline and GridSetu ...")
        doc["fleet"][wk] = _fleet(res[wk])
    log("Unit commitment, stress week (PyPSA MILP) ...")
    doc["uc"]["stress"] = _uc(res["stress"])
    doc["about"]["runtime_s"] = round(time.time() - t0, 1)
    (out / "phase2.json").write_text(json.dumps(doc, indent=2, default=float), encoding="utf-8")
    return doc
