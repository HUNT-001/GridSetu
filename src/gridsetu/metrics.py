"""Planning metrics: load factor, diversity factor, demand factor, plant capacity and
plant use factors, utilisation, reserve margin, market and renewable statistics.

Definitions used (standard power-system planning textbook forms):
  load factor        = average demand / maximum demand (over the period)
  diversity factor   = sum of individual maximum demands / maximum demand of the group
  demand factor      = maximum demand / connected load
  capacity factor    = energy generated / (rated capacity x period hours)
  plant use factor   = energy generated / (rated capacity x hours actually in operation)
  utilisation factor = maximum demand / installed capacity
  reserve margin     = (available capacity at peak - peak demand) / peak demand"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CLASSES, Scenario


def _lf(x: np.ndarray) -> float:
    return float(np.mean(x) / np.max(x)) if np.max(x) > 0 else 0.0


def class_factors(sc: Scenario, loads: dict) -> pd.DataFrame:
    """One row per (region, class) plus city-wide class totals."""
    dt = sc.dt_h
    rows = []
    for r, df in loads.items():
        for c in CLASSES:
            x = df[c].values
            if x.max() <= 0:
                continue
            md = float(x.max())
            connected = md / sc.classes[c]["demand_factor"]
            rows.append({"region": r, "class": c, "priority": sc.classes[c]["priority"],
                         "max_demand_mw": md, "avg_demand_mw": float(x.mean()),
                         "energy_mwh": float(x.sum() * dt), "load_factor": _lf(x),
                         "connected_load_mw": connected, "demand_factor": md / connected})
    for c in CLASSES:
        x = sum(loads[r][c].values for r in loads)
        if x.max() <= 0:
            continue
        indiv = sum(loads[r][c].max() for r in loads)
        connected = sum(loads[r][c].max() / sc.classes[c]["demand_factor"] for r in loads)
        rows.append({"region": "CITY", "class": c, "priority": sc.classes[c]["priority"],
                     "max_demand_mw": float(x.max()), "avg_demand_mw": float(x.mean()),
                     "energy_mwh": float(x.sum() * dt), "load_factor": _lf(x),
                     "connected_load_mw": connected, "demand_factor": float(x.max()) / connected,
                     "diversity_factor": float(indiv / x.max())})
    return pd.DataFrame(rows)


def system_factors(sc: Scenario, loads: dict, rt) -> dict:
    dt = sc.dt_h
    region_tot = {r: df.sum(axis=1).values for r, df in loads.items()}
    city = sum(region_tot.values())
    class_peaks_by_region = {r: sum(df[c].max() for c in CLASSES) for r, df in loads.items()}
    installed = sum(g["pmax_mw"] for g in sc.generators.values())
    t_peak = int(np.argmax(city))
    avail_at_peak = 0.0
    for gid, g in sc.generators.items():
        if g["kind"] in ("solar", "wind"):
            avail_at_peak += rt.gen[gid].values[t_peak] + rt.curtail[gid].values[t_peak]
        else:
            avail_at_peak += g["pmax_mw"]
    return {
        "city_peak_mw": float(city.max()),
        "city_peak_time": str(sc.index[t_peak]),
        "city_energy_mwh": float(city.sum() * dt),
        "city_load_factor": _lf(city),
        "diversity_factor_regions": float(sum(v.max() for v in region_tot.values()) / city.max()),
        "diversity_factor_classes_within_region": {r: float(class_peaks_by_region[r] / region_tot[r].max())
                                                   for r in loads},
        "installed_capacity_mw": float(installed),
        "utilisation_factor": float(city.max() / installed),
        "reserve_margin_at_peak_pct": float(100 * (avail_at_peak - city.max()) / city.max()),
        "region_load_factor": {r: _lf(v) for r, v in region_tot.items()},
    }


def plant_factors(sc: Scenario, rt) -> pd.DataFrame:
    dt = sc.dt_h
    hours = sc.n_steps * dt
    rows = []
    for gid, g in sc.generators.items():
        x = rt.gen[gid].values
        energy = float(x.sum() * dt)
        on_hours = float((x > 0.1).sum() * dt)
        cap = g["pmax_mw"]
        rows.append({"unit": gid, "kind": g["kind"], "region": g["region"], "capacity_mw": cap,
                     "energy_mwh": energy, "capacity_factor": energy / (cap * hours),
                     "plant_use_factor": energy / (cap * on_hours) if on_hours else 0.0,
                     "operating_hours": on_hours,
                     "curtailed_mwh": float(rt.curtail[gid].sum() * dt) if gid in rt.curtail else 0.0})
    return pd.DataFrame(rows)


def market_stats(sc: Scenario, da, rt, inp) -> dict:
    cap = sc.raw["exchange_price"]["price_cap"]
    dt = sc.dt_h
    mcp = da.mcp(cap)
    spread = mcp.max(axis=1) - mcp.min(axis=1)
    total_shed = sum(rt.shed[r].sum(axis=1) for r in rt.shed)
    shed_by_class = {c: float(sum(rt.shed[r][c].sum() for r in rt.shed) * dt) for c in CLASSES}
    demand = sum(inp.loads[r].sum(axis=1) for r in inp.loads)
    ren = [g for g, v in sc.generators.items() if v["kind"] in ("solar", "wind")]
    re_energy = float(rt.gen[ren].sum().sum() * dt) + float(sum(np.sum(v) for v in inp.rooftop.values()) * dt)
    return {
        "da_mcp_mean_inr_kwh": {r: float(mcp[r].mean()) for r in mcp},
        "da_mcp_max_inr_kwh": {r: float(mcp[r].max()) for r in mcp},
        "rt_price_mean_inr_kwh": {r: float(rt.mcp(cap)[r].mean()) for r in rt.price},
        "congestion_hours": float((spread > 0.05).sum() * dt),
        "scarcity_hours": float((da.price.max(axis=1) >= cap - 1e-6).sum() * dt),
        "energy_not_served_mwh": float(total_shed.sum() * dt),
        "energy_not_served_pct": float(100 * total_shed.sum() / demand.sum()),
        "ens_by_class_mwh": shed_by_class,
        "shedding_hours": float((total_shed > 0.01).sum() * dt),
        "industrial_dr_mwh": float(rt.dr.sum() * dt),
        "renewable_share_pct": float(100 * re_energy / float(demand.sum() * dt)),
        "renewable_curtailed_mwh": float(rt.curtail.sum().sum() * dt),
    }


def feeder_factors(sc: Scenario, fl) -> dict:
    """Diversity/load factors at feeder level from the household-level profiles."""
    gross = fl.gross_load
    indiv = fl.hh_load.max(axis=1).sum() + fl.ent_load.max(axis=1).sum() + \
        sum(v.max() for v in fl.critical.values())
    return {"feeder_peak_kw": float(gross.max()), "feeder_load_factor": _lf(gross),
            "household_diversity_factor": float(fl.hh_load.max(axis=1).sum() / fl.hh_load.sum(axis=0).max()),
            "feeder_diversity_factor": float(indiv / gross.max()),
            "tier1_peak_kw": float(fl.tier1.max()), "tier2_optin_peak_kw": float(fl.tier2.max()),
            "tier3_peak_kw": float(fl.tier3.max())}
