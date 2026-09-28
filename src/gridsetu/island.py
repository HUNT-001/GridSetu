"""Isolated microgrid (no grid connection): solar + battery + diesel for a remote hamlet.

legacy   : solar serves load, the diesel set covers every deficit, surplus solar is lost.
gridsetu : solar -> load -> battery; the battery covers deficits down to its floor; the
           diesel starts only when the battery is at its floor and then runs at an
           efficient loading while recharging the battery (cycle-charging)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Scenario
from .profiles import HOURLY_SHAPES, hourly_to_steps
from .weather import pv_power


def island_profiles(sc: Scenario, wx: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    cfg = sc.raw["island_microgrid"]
    rng = sc.rng(555)
    dom = hourly_to_steps(HOURLY_SHAPES["domestic"], sc.index)
    muni = hourly_to_steps(HOURLY_SHAPES["municipal"], sc.index)
    load = (0.85 * dom + 0.15 * muni) * np.clip(1 + rng.normal(0, 0.06, sc.n_steps), 0.6, None)
    load = load / load.max() * cfg["peak_kw"]
    pv = pv_power(wx["ghi"].values, wx["temp_c"].values, cfg["solar_kwp"])
    return load, pv


def simulate_island(sc: Scenario, wx: pd.DataFrame, strategy: str) -> tuple[pd.DataFrame, dict]:
    cfg = sc.raw["island_microgrid"]
    dt = sc.dt_h
    load, pv = island_profiles(sc, wx)
    E, P = cfg["battery_kwh"], cfg["battery_kw"]
    Dmax, Dmin = cfg["diesel_kw"], cfg["diesel_min_load"] * cfg["diesel_kw"]
    soc_min, soc_max, eta = 0.2 * E, 0.95 * E, 0.95
    soc = 0.6 * E
    diesel_on = False
    rows = []
    for t in range(sc.n_steps):
        L, S = load[t], pv[t]
        pv_used = min(S, L)
        deficit = L - pv_used
        surplus = S - pv_used
        bat = diesel = unserved = 0.0
        if strategy == "legacy":
            if deficit > 0:
                diesel = min(max(deficit, Dmin), Dmax)
                unserved = max(deficit - Dmax, 0.0)
            curtailed = surplus
        else:
            ch_room = min(P, (soc_max - soc) / (eta * dt))
            charge = min(surplus, ch_room)
            curtailed = surplus - charge
            soc += charge * eta * dt
            dis_room = min(P, max(soc - soc_min, 0) * eta / dt)
            if diesel_on and soc >= 0.8 * E:
                diesel_on = False
            if deficit > dis_room + 1e-9:
                diesel_on = True
            if diesel_on and deficit > 0:
                d_serve = min(deficit, Dmax)
                rem = deficit - d_serve
                bat = min(rem, dis_room)
                soc -= bat / eta * dt
                unserved = rem - bat
                setpoint = max(0.8 * Dmax, d_serve)       # efficient loading
                ch = min(setpoint - d_serve, max(0.0, min(P, (soc_max - soc) / (eta * dt))))
                soc += ch * eta * dt
                bat -= ch
                diesel = max(d_serve + ch, Dmin)
            else:
                bat = min(deficit, dis_room)
                soc -= bat / eta * dt
                unserved = deficit - bat
            bat -= charge
        rows.append({"load_kw": L, "pv_kw": S, "pv_used_kw": S - curtailed, "diesel_kw": diesel,
                     "battery_kw": bat, "soc_kwh": soc if strategy != "legacy" else np.nan,
                     "unserved_kw": unserved})
    ts = pd.DataFrame(rows, index=sc.index)
    litres = ts["diesel_kw"].sum() * dt * cfg["diesel_l_per_kwh"]
    served = ts["load_kw"].sum() * dt - ts["unserved_kw"].sum() * dt
    return ts, {
        "strategy": strategy,
        "diesel_litres": float(litres),
        "diesel_cost_inr": float(litres * cfg["diesel_price_inr_l"]),
        "diesel_run_hours": float((ts["diesel_kw"] > 0).sum() * dt),
        "renewable_fraction_pct": float(100 * (1 - ts["diesel_kw"].sum() * dt / max(served, 1e-9))),
        "pv_curtailed_kwh": float((ts["pv_kw"] - ts["pv_used_kw"]).sum() * dt),
        "unserved_kwh": float(ts["unserved_kw"].sum() * dt),
        "co2_kg": float(litres * 2.68),
    }
