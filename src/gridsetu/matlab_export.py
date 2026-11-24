"""Export pilot feeder F07 as per-bus load profiles for the MATLAB low-voltage model.

The Python simulator treats the feeder as one point. The MATLAB model (``matlab/``) needs
the same loads placed on a radial low-voltage network to compute technical losses,
voltage and transformer ageing. This module places every household, micro-enterprise and
critical load on one of 21 buses (3 circuits x 7 buses) and writes, for each week and
variant (baseline, gridsetu):

* ``f07_buses.csv`` -- the bus map (circuit, position, what is connected)
* ``f07_loads_<week>_<variant>.csv`` -- net load per bus per 15-minute step (kW), wide format
* ``f07_feeder_<week>_<variant>.csv`` -- feeder-head import, battery, community PV and state

Allocation is exact: at every energized step the bus loads, minus community PV and the
battery at the transformer bus, add up to the feeder import Python reports (tested).
Assumptions (stated, not measured): homes are spread evenly over the 21 buses (home ``i`` to bus ``i * 21 // n + 1``); enterprises
round-robin across buses; the health sub-centre, school and water pump sit on named buses;
street lighting and rooftop PV are spread evenly over the 21 buses.

    python -m gridsetu export-matlab --out outputs/matlab
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

N_CIRCUITS, BUSES_PER_CIRCUIT, CIRCUIT_LENGTH_M = 3, 7, 600
CRITICAL_BUS = {"health_subcentre": 4, "school": 11, "water_pumping": 21}   # street lights: spread


def bus_map(n_hh: int, n_ent: int) -> pd.DataFrame:
    n_bus = N_CIRCUITS * BUSES_PER_CIRCUIT
    rows = []
    for b in range(1, n_bus + 1):
        c, k = divmod(b - 1, BUSES_PER_CIRCUIT)
        crit = [name for name, bus in CRITICAL_BUS.items() if bus == b]
        rows.append({"bus_id": b, "circuit": "ABC"[c], "index_on_circuit": k + 1,
                     "position_m": round((k + 1) * CIRCUIT_LENGTH_M / BUSES_PER_CIRCUIT, 1),
                     "n_homes": int(sum(1 for i in range(n_hh) if i * n_bus // n_hh + 1 == b)),
                     "n_enterprises": int(sum(1 for j in range(n_ent) if j % n_bus + 1 == b)),
                     "critical": ";".join(crit)})
    return pd.DataFrame(rows)


def bus_loads(fl, fr) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-bus net load (kW) and the feeder-head summary for one simulated variant."""
    ts = fr.ts
    n_hh, n_ent = fl.hh_load.shape[0], fl.ent_load.shape[0]
    n_bus = N_CIRCUITS * BUSES_PER_CIRCUIT
    T = len(ts)
    hh_bus = np.arange(n_hh) * (N_CIRCUITS * BUSES_PER_CIRCUIT) // n_hh
    ent_bus = np.arange(n_ent) % n_bus
    status = fr.extra.get("hh_status", np.zeros((T, n_hh), np.uint8))
    state = ts["state"].astype(str).to_numpy()
    energized = ~pd.Series(state).str.contains("trip").to_numpy()

    loads = np.zeros((T, n_bus))
    for t in range(T):
        if not energized[t]:
            continue
        # households: Tier-3 removed for homes the ledger paused this step
        hh = fl.hh_load[:, t] - fl.hh_tier3[:, t] * (status[t] == 1)
        ent = fl.ent_load[:, t].copy()
        c2 = ts["curtail_t2"].iat[t]
        if c2 > 0:   # consented Tier-2 shifting, shared by opted-in enterprises' motor load
            w = fl.ent_tier2[:, t] * fl.ent_optin
            ent -= c2 * w / w.sum() if w.sum() > 0 else 0
        # rescale households so the step matches Python's served energy exactly
        # (covers partial pauses, overrides and the rebound queue)
        crit = {k: v[t] for k, v in fl.critical.items()}
        served = ts["gross"].iat[t] - ts["unserved"].iat[t]      # recorded gross already includes rebound
        target_hh = served - ent.sum() - sum(crit.values())
        if hh.sum() > 0:
            hh *= target_hh / hh.sum()
        np.add.at(loads[t], hh_bus, hh)
        np.add.at(loads[t], ent_bus, ent)
        for name, kw in crit.items():
            if name in CRITICAL_BUS:
                loads[t, CRITICAL_BUS[name] - 1] += kw
            else:
                loads[t] += kw / n_bus
        loads[t] -= fl.rooftop_pv[t] / n_bus           # behind-the-meter PV, spread evenly

    idx = ts.index
    load_df = pd.DataFrame(loads.round(4), index=idx, columns=[f"bus_{b:02d}" for b in range(1, n_bus + 1)])
    load_df.index.name = "timestamp"
    cpv_used = np.where(energized, fl.community_pv - ts["spill"].to_numpy(), 0.0)
    feeder = pd.DataFrame({
        "import_kw": ts["import"].to_numpy().round(4),
        "battery_kw": np.where(energized, ts["battery_kw"].to_numpy(), 0.0).round(4),   # + = discharge
        "community_pv_kw": cpv_used.round(4),
        "energized": energized.astype(int),
        "tier1_islanded_kw": np.where(~energized & pd.Series(state).str.contains("island").to_numpy(),
                                      ts["tier1"].to_numpy(), 0.0).round(4),
        "ambient_c": fl.weather["temp_c"].to_numpy().round(2),
        "state": state,
    }, index=idx)
    feeder.index.name = "timestamp"
    return load_df, feeder


def export(out_dir: str | Path = "outputs/matlab", config_path=None, seed: int = 42, verbose: bool = True) -> Path:
    from .simulate import stress_and_representative
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    res = stress_and_representative(config_path, {"simulation": {"seed": seed}}, verbose=False)
    first = res["stress"].feeder_loads
    bus_map(first.hh_load.shape[0], first.ent_load.shape[0]).to_csv(out / "f07_buses.csv", index=False)
    for week in ("stress", "representative"):
        wk = res[week]
        for variant in ("baseline", "gridsetu"):
            loads, feeder = bus_loads(wk.feeder_loads, wk.feeder[variant])
            loads.to_csv(out / f"f07_loads_{week}_{variant}.csv")
            feeder.to_csv(out / f"f07_feeder_{week}_{variant}.csv")
            if verbose:
                print(f"{week}/{variant}: {len(loads)} steps, {loads.shape[1]} buses")
    return out
