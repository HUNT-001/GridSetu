"""City-scale market clearing and real-time dispatch.

Day-ahead (DA): 96 x 15-min blocks per day, IEX-style market splitting across the three
bid areas with available-transfer-capability limits on the interties. The regional
market clearing price (MCP) is the dual of each area's power-balance constraint.

Real-time (RT): the same network re-solved on actual loads and renewables, with thermal
units held near their DA schedule (they cannot re-commit), forced outages applied, and
fast resources (gas, hydro, import, demand response) re-dispatched. Whatever cannot be
served is shed in priority order through piece-wise value-of-lost-load segments, which
also spreads shedding evenly across areas instead of dumping it on one."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pyomo.environ as pyo

from .config import CLASSES, Scenario
from .profiles import city_class_loads, region_rooftop_pv
from .weather import pv_power

SOLVER = "appsi_highs"
N_SEGMENTS = 4
RT_THERMAL_BAND_MW = 5.0   # AGC regulation band around the DA schedule
DISPATCHABLE = ("thermal", "gas", "hydro", "import")


def exchange_price_curve(sc: Scenario) -> np.ndarray:
    ep = sc.raw["exchange_price"]
    hourly = [ep["offpeak"]] * 6 + [4.2, 5.0, 4.6] + [ep["solar_hours"]] * 7 + [5.2] \
        + [ep["evening_peak"]] * 5 + [6.5, ep["offpeak"] + 0.8]
    h = sc.index.hour.values
    return np.minimum(np.array(hourly)[h], ep["price_cap"])


def _ar1(rng, n, phi, sigma):
    x = np.zeros(n)
    e = rng.normal(0, sigma, n)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    return x


@dataclass
class CityInputs:
    loads: dict               # region -> DataFrame (MW by class), actual
    loads_fc: dict            # region -> DataFrame, day-ahead forecast
    rooftop: dict             # region -> array MW, actual
    rooftop_fc: dict
    renew_avail: dict         # gen -> array MW, actual availability (solar/wind)
    renew_fc: dict
    exch_price: np.ndarray
    outage: dict              # gen -> bool array (True = unit out)
    coordinated: bool


def build_city_inputs(sc: Scenario, wx: pd.DataFrame, coordinated: bool) -> CityInputs:
    coord = sc.raw["coordination"]
    shift = coordinated and coord["irrigation_shift_to_solar_hours"]
    loads = city_class_loads(sc, wx, shifted_irrigation=shift)
    n = sc.n_steps
    loads_fc = {}
    for i, (rid, df) in enumerate(loads.items()):
        rng = np.random.default_rng(sc.rng_seed + 50 + i)  # same error in both scenarios
        err = 1 + _ar1(rng, n, 0.97, 0.004) + rng.normal(0, 0.01, n)
        loads_fc[rid] = df.mul(err, axis=0)
    renew, renew_fc = {}, {}
    for gid, g in sc.generators.items():
        if g["kind"] == "solar":
            renew[gid] = pv_power(wx["ghi"].values, wx["temp_c"].values, g["pmax_mw"])
            renew_fc[gid] = pv_power(wx["ghi_fc"].values, wx["temp_fc"].values, g["pmax_mw"])
        elif g["kind"] == "wind":
            renew[gid] = g["pmax_mw"] * wx["wind_cf"].values
            renew_fc[gid] = g["pmax_mw"] * wx["wind_cf_fc"].values
    outage = {gid: np.zeros(n, bool) for gid in sc.generators}
    for o in sc.raw.get("forced_outages", []):
        s, e = sc.step_of(o["start"]), sc.step_of(o["end"])
        outage[o["unit"]][s:e + 1] = True
    return CityInputs(loads, loads_fc, region_rooftop_pv(sc, wx), region_rooftop_pv(sc, wx, True),
                      renew, renew_fc, exchange_price_curve(sc), outage, coordinated)


@dataclass
class DispatchResult:
    gen: pd.DataFrame                      # MW by generator (+ renewables after curtailment)
    curtail: pd.DataFrame                  # MW curtailed renewables
    flow: pd.DataFrame                     # MW on each intertie (+ = from->to)
    shed: dict                             # region -> DataFrame MW shed by class
    price: pd.DataFrame                    # INR/kWh raw shadow price by region
    dr: pd.Series                          # MW industrial demand response
    served_load: dict = field(default_factory=dict)

    def mcp(self, cap: float) -> pd.DataFrame:
        """Published market clearing price: the shadow price capped at the exchange ceiling."""
        return self.price.clip(upper=cap)


def _solve_day(sc: Scenario, inp: CityInputs, steps: np.ndarray, mode: str,
               thermal_sched: dict | None, known_outage: dict) -> dict:
    dt = sc.dt_h
    T = range(len(steps))
    R = list(sc.regions)
    gens = sc.generators
    disp = [g for g, v in gens.items() if v["kind"] in DISPATCHABLE]
    ren = [g for g, v in gens.items() if v["kind"] in ("solar", "wind")]
    ties = sc.raw["interties"]
    loads = inp.loads if mode == "RT" else inp.loads_fc
    roof = inp.rooftop if mode == "RT" else inp.rooftop_fc
    ravail = inp.renew_avail if mode == "RT" else inp.renew_fc
    coord = sc.raw["coordination"]
    use_dr = inp.coordinated and coord["industrial_dr_mw"] > 0

    m = pyo.ConcreteModel()
    m.T = pyo.Set(initialize=list(T))
    m.p = pyo.Var(disp, m.T, domain=pyo.NonNegativeReals)
    m.r = pyo.Var(ren, m.T, domain=pyo.NonNegativeReals)
    m.f = pyo.Var(range(len(ties)), m.T, domain=pyo.Reals)
    seg_keys = [(r, c, k) for r in R for c in CLASSES for k in range(N_SEGMENTS)]
    m.shed = pyo.Var(seg_keys, m.T, domain=pyo.NonNegativeReals)
    m.dr = pyo.Var(m.T, domain=pyo.NonNegativeReals)

    load_rc = {(r, c): loads[r][c].values[steps] for r in R for c in CLASSES}

    for t in T:
        s = steps[t]
        for g in disp:
            v = gens[g]
            out = known_outage[g][s]
            pmax = 0.0 if out else v["pmax_mw"]
            pmin = 0.0 if out else v.get("pmin_mw", 0)
            if thermal_sched is not None and v["kind"] == "thermal" and not out:
                sch = thermal_sched[g][t]
                pmin = max(pmin, sch - RT_THERMAL_BAND_MW)
                pmax = min(pmax, sch + RT_THERMAL_BAND_MW)
                if sch <= 0:  # unit was offline in DA (e.g. still on outage): stays off
                    pmin, pmax = 0.0, 0.0
            m.p[g, t].setlb(pmin)
            m.p[g, t].setub(pmax)
        for g in ren:
            m.r[g, t].setub(ravail[g][s])
        for i, tie in enumerate(ties):
            m.f[i, t].setlb(-tie["mw"])
            m.f[i, t].setub(tie["mw"])
        for (r, c, k) in seg_keys:
            m.shed[r, c, k, t].setub(load_rc[(r, c)][t] / N_SEGMENTS)
        m.dr[t].setub(coord["industrial_dr_mw"] if use_dr else 0.0)

    # ramps (thermal & gas)
    m.ramp = pyo.ConstraintList()
    for g in disp:
        rr = gens[g].get("ramp_mw_per_step")
        if rr is None or gens[g]["kind"] == "import":
            continue
        for t in list(T)[1:]:
            if known_outage[g][steps[t]] or known_outage[g][steps[t - 1]]:
                continue
            m.ramp.add(m.p[g, t] - m.p[g, t - 1] <= rr)
            m.ramp.add(m.p[g, t - 1] - m.p[g, t] <= rr)

    # hydro daily energy budget, DR daily energy budget (4 h at full contract)
    m.budget = pyo.ConstraintList()
    for g in disp:
        if gens[g]["kind"] == "hydro":
            m.budget.add(sum(m.p[g, t] for t in T) * dt <= gens[g]["daily_energy_mwh"])
    m.budget.add(sum(m.dr[t] for t in T) * dt <= 4 * coord["industrial_dr_mw"])
    # industrial DR can only reduce industrial load actually present in R1
    m.drlim = pyo.Constraint(m.T, rule=lambda mm, t: mm.dr[t] <= load_rc[("R1", "industrial")][t])

    def balance(mm, r, t):
        s = steps[t]
        supply = sum(mm.p[g, t] for g in disp if gens[g]["region"] == r)
        supply += sum(mm.r[g, t] for g in ren if gens[g]["region"] == r)
        net_in = 0
        for i, tie in enumerate(ties):
            if tie["to"] == r:
                net_in += mm.f[i, t]
            if tie["from"] == r:
                net_in -= mm.f[i, t]
        demand = sum(load_rc[(r, c)][t] for c in CLASSES) - roof[r][s]
        shed = sum(mm.shed[r, c, k, t] for c in CLASSES for k in range(N_SEGMENTS))
        dr = mm.dr[t] if r == "R1" else 0
        return supply + net_in == demand - shed - dr
    m.bal = pyo.Constraint(R, m.T, rule=balance)

    def cost(mm):
        tot = 0
        for t in T:
            s = steps[t]
            for g in disp:
                v = gens[g]
                mc = inp.exch_price[s] if v["kind"] == "import" else v["mc_inr_kwh"]
                tot += mc * mm.p[g, t]
            for g in ren:
                tot += -0.01 * mm.r[g, t]           # prefer using renewables
            for (r, c, k) in seg_keys:
                voll = sc.classes[c]["shed_cost_inr_kwh"] + 0.25 * k
                tot += voll * mm.shed[r, c, k, t]
            tot += coord["industrial_dr_price_inr_kwh"] * mm.dr[t]
        return tot * dt
    m.obj = pyo.Objective(rule=cost, sense=pyo.minimize)
    m.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)

    res = pyo.SolverFactory(SOLVER).solve(m)
    if str(res.solver.termination_condition) != "optimal":
        raise RuntimeError(f"{mode} dispatch not optimal: {res.solver.termination_condition}")

    out = {
        "gen": {g: np.array([pyo.value(m.p[g, t]) for t in T]) for g in disp},
        "ren": {g: np.array([pyo.value(m.r[g, t]) for t in T]) for g in ren},
        "curt": {g: ravail[g][steps] - np.array([pyo.value(m.r[g, t]) for t in T]) for g in ren},
        "flow": {f"{tie['from']}-{tie['to']}": np.array([pyo.value(m.f[i, t]) for t in T])
                 for i, tie in enumerate(ties)},
        "shed": {r: {c: np.array([sum(pyo.value(m.shed[r, c, k, t]) for k in range(N_SEGMENTS))
                                  for t in T]) for c in CLASSES} for r in R},
        "price": {r: np.array([m.dual[m.bal[r, t]] / dt for t in T]) for r in R},
        "dr": np.array([pyo.value(m.dr[t]) for t in T]),
    }
    return out


def _collect(sc: Scenario, parts: list[dict]) -> DispatchResult:
    idx = sc.index
    cat = lambda key: {k: np.concatenate([p[key][k] for p in parts]) for k in parts[0][key]}
    gen = pd.DataFrame({**cat("gen"), **cat("ren")}, index=idx)
    shed = {r: pd.DataFrame({c: np.concatenate([p["shed"][r][c] for p in parts]) for c in CLASSES},
                            index=idx) for r in sc.regions}
    return DispatchResult(gen=gen, curtail=pd.DataFrame(cat("curt"), index=idx),
                          flow=pd.DataFrame(cat("flow"), index=idx), shed=shed,
                          price=pd.DataFrame(cat("price"), index=idx),
                          dr=pd.Series(np.concatenate([p["dr"] for p in parts]), index=idx))


def run_city(sc: Scenario, inp: CityInputs) -> tuple[DispatchResult, DispatchResult]:
    """Day-by-day DA clearing followed by RT dispatch. The DA market of the day a forced
    outage starts does not know about it; later days do."""
    spd = sc.steps_per_day
    da_parts, rt_parts = [], []
    for d in range(sc.n_days):
        steps = np.arange(d * spd, (d + 1) * spd)
        known = {}
        for g, mask in inp.outage.items():
            k = mask.copy()
            # unforeseen on its first day: DA only knows outages that began before this day
            started_today = np.zeros_like(k)
            if mask[steps].any():
                first = np.argmax(mask)
                if first >= steps[0]:
                    started_today[first:] = True
            known[g] = k & ~started_today
        da = _solve_day(sc, inp, steps, "DA", None, known)
        sched = {g: da["gen"][g] for g in da["gen"] if sc.generators[g]["kind"] == "thermal"}
        rt = _solve_day(sc, inp, steps, "RT", sched, inp.outage)
        da_parts.append(da)
        rt_parts.append(rt)
    return _collect(sc, da_parts), _collect(sc, rt_parts)
