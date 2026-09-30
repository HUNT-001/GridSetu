"""Day-ahead unit commitment with PyPSA (Phase 2 study).

The Phase 1 market is a linear dispatch in which every thermal unit is always on at or
above its minimum load. Real day-ahead scheduling also decides *which* units run: a unit
can be kept off overnight, but starting it costs money and it must then stay on for its
minimum up time. This module solves that mixed-integer problem per day with PyPSA and
HiGHS on the same three-area network, then fixes the commitment and re-solves the linear
dispatch to get clearing prices. It is reported next to the linear market as a study; the
feeder results still use the Phase 1 market so earlier numbers stay comparable.

Units: PyPSA costs are INR/MWh and INR; our config stores INR/kWh."""
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import CLASSES, Scenario

logging.getLogger("pypsa").setLevel(logging.ERROR)
logging.getLogger("linopy").setLevel(logging.ERROR)

COMMITTABLE = ("thermal", "gas")


@dataclass
class UCResult:
    status: pd.DataFrame        # 1/0 per committable unit
    gen: pd.DataFrame           # MW per unit
    price: pd.DataFrame         # INR/kWh per region (fixed-commitment LP duals)
    shed: pd.Series             # MW total shed
    startups: dict              # unit -> count
    cost_inr: dict              # {"energy", "startup", "shed", "total"}


def _day_network(sc: Scenario, inp, steps: np.ndarray, known_outage: dict, commit: dict | None,
                 prev_on: dict | None = None):
    import pypsa
    dt = sc.dt_h
    n = pypsa.Network()
    snaps = pd.RangeIndex(len(steps))
    n.set_snapshots(snaps)
    n.snapshot_weightings.loc[:, :] = dt
    ucp = sc.raw.get("unit_commitment", {})
    for r in sc.regions:
        n.add("Bus", r)
        load = sum(inp.loads_fc[r][c].values[steps] for c in CLASSES) - inp.rooftop_fc[r][steps]
        n.add("Load", f"load_{r}", bus=r, p_set=pd.Series(load, index=snaps))
        # shedding in priority segments (as in the LP market)
        for c in CLASSES:
            peak = float(inp.loads_fc[r][c].values[steps].max())
            if peak <= 0:
                continue
            n.add("Generator", f"shed_{r}_{c}", bus=r, p_nom=peak * 1.05,
                  marginal_cost=1000 * sc.classes[c]["shed_cost_inr_kwh"])
    for i, t in enumerate(sc.raw["interties"]):
        n.add("Link", f"{t['from']}-{t['to']}", bus0=t["from"], bus1=t["to"], p_nom=t["mw"], p_min_pu=-1.0,
              efficiency=1.0)
    for g, v in sc.generators.items():
        out = known_outage[g][steps]
        avail = (~out).astype(float)
        kind = v["kind"]
        if kind in ("solar", "wind"):
            n.add("Generator", g, bus=v["region"], p_nom=v["pmax_mw"],
                  p_max_pu=pd.Series(inp.renew_fc[g][steps] / v["pmax_mw"], index=snaps), marginal_cost=-10.0)
            continue
        if kind == "import":
            n.add("Generator", g, bus=v["region"], p_nom=v["pmax_mw"],
                  marginal_cost=pd.Series(1000 * inp.exch_price[steps], index=snaps))
            continue
        kw = dict(bus=v["region"], p_nom=v["pmax_mw"], marginal_cost=1000 * v["mc_inr_kwh"])
        steps_per_h = int(round(1 / dt))
        if kind == "hydro":
            kw["e_sum_max"] = v["daily_energy_mwh"]
            kw["p_max_pu"] = pd.Series(avail, index=snaps)
        elif kind in COMMITTABLE:
            u = ucp.get(g, {})
            pmin = float(u.get("pmin_mw", v.get("pmin_mw", 0.0)))
            if commit is None:
                up = int(u.get("min_up_h", 1) * steps_per_h)
                down = int(u.get("min_down_h", 1) * steps_per_h)
                was_on = bool((prev_on or {}).get(g, 1.0) > 0.5) and not out[0]
                # carry yesterday's state across midnight; min up/down times already served
                kw.update(committable=True, p_min_pu=pmin / v["pmax_mw"], min_up_time=up, min_down_time=down,
                          up_time_before=up if was_on else 0, down_time_before=0 if was_on else down,
                          start_up_cost=float(u.get("start_cost_inr", 0)),
                          shut_down_cost=float(u.get("shut_cost_inr", 0)),
                          p_max_pu=pd.Series(avail, index=snaps))
                # ramp limits are left out of the commitment problem: PyPSA's day-boundary
                # initial conditions make them infeasible for a unit already running at dawn
            else:
                on = commit[g] * avail
                kw.update(p_min_pu=pd.Series(on * pmin / v["pmax_mw"], index=snaps),
                          p_max_pu=pd.Series(on, index=snaps))
        n.add("Generator", g, **kw)
    return n


def _solve(n):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        status, cond = n.optimize(solver_name="highs", solver_options={"mip_rel_gap": 0.005, "time_limit": 60,
                                                                        "output_flag": False})
    if status != "ok":
        raise RuntimeError(f"PyPSA solve failed: {status} {cond}")


def run_uc(sc: Scenario, inp) -> UCResult:
    """Day-by-day commitment on the day-ahead forecast, with outages known as the DA market knew them."""
    spd = sc.steps_per_day
    dt = sc.dt_h
    status_parts, gen_parts, price_parts, shed_parts = [], [], [], []
    starts = {g: 0 for g, v in sc.generators.items() if v["kind"] in COMMITTABLE}
    cost = {"energy": 0.0, "startup": 0.0, "shed": 0.0}
    prev_on = {g: 1.0 for g in starts}
    for d in range(sc.n_days):
        steps = np.arange(d * spd, (d + 1) * spd)
        known = {}
        for g, mask in inp.outage.items():   # outages beginning today are unforeseen (as in market.py)
            k = mask.copy()
            if mask[steps].any() and np.argmax(mask) >= steps[0]:
                k[np.argmax(mask):] = False
            known[g] = k
        n = _day_network(sc, inp, steps, known, None, prev_on)
        _solve(n)
        st = n.generators_t.status[list(starts)].round().clip(0, 1)
        commit = {g: st[g].values for g in starts}
        for g in starts:
            s = np.r_[prev_on[g], st[g].values]
            starts[g] += int(((s[1:] - s[:-1]) > 0.5).sum())
            prev_on[g] = s[-1]
            cost["startup"] += float(sc.raw["unit_commitment"].get(g, {}).get("start_cost_inr", 0)) * \
                int(((s[1:] - s[:-1]) > 0.5).sum())
        # fix commitment, re-solve as LP for prices
        n2 = _day_network(sc, inp, steps, known, commit)
        _solve(n2)
        p = n2.generators_t.p
        shed_cols = [c for c in p.columns if c.startswith("shed_")]
        units = [g for g in sc.generators]
        mc = n2.get_switchable_as_dense("Generator", "marginal_cost")
        cost["energy"] += float((p[units] * mc[units]).sum().sum() * dt)
        cost["shed"] += float((p[shed_cols] * mc[shed_cols]).sum().sum() * dt)
        status_parts.append(st.set_axis(steps))
        gen_parts.append(p[units].set_axis(steps))
        price_parts.append((n2.buses_t.marginal_price[list(sc.regions)] / 1000).set_axis(steps))
        shed_parts.append(p[shed_cols].sum(axis=1).set_axis(steps))
    cost["total"] = cost["energy"] + cost["startup"] + cost["shed"]
    idx = sc.index
    return UCResult(status=pd.concat(status_parts).set_axis(idx), gen=pd.concat(gen_parts).set_axis(idx),
                    price=pd.concat(price_parts).set_axis(idx), shed=pd.concat(shed_parts).set_axis(idx),
                    startups=starts, cost_inr=cost)


def lp_cost(sc: Scenario, inp, da) -> dict:
    """Cost of the Phase 1 linear day-ahead schedule on the same terms, for comparison."""
    dt = sc.dt_h
    energy = 0.0
    for g, v in sc.generators.items():
        x = da.gen[g].values
        if v["kind"] == "import":
            energy += float((x * inp.exch_price).sum() * dt * 1000)
        elif v["kind"] in ("solar", "wind"):
            energy += float(-10.0 * x.sum() * dt)
        else:
            energy += float(1000 * v["mc_inr_kwh"] * x.sum() * dt)
    shed = 0.0
    for r in da.shed:
        for c in CLASSES:
            shed += float(1000 * sc.classes[c]["shed_cost_inr_kwh"] * da.shed[r][c].sum() * dt)
    return {"energy": energy, "startup": 0.0, "shed": shed, "total": energy + shed}
