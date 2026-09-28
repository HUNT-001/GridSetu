"""GridSetu pilot feeder: day-ahead planning LP, uncertainty-sized reserve, and the edge
controller that runs every 15 minutes with the fairness ledger, comms fail-safe and
Tier-1 islanding. The same step loop runs the BASELINE (no battery, no coordination:
the DISCOM trips the whole feeder) so both scenarios share physics and random draws."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pyomo.environ as pyo

from .comms import build_slices
from .config import Scenario
from .fairness import FairnessLedger
from .profiles import FeederLoads
from .reserve import ReliabilityReserve, size_reserve

SOLVER = "appsi_highs"
FEEDER_ID = "TN-CBE-PERI-11KV-F07"


@dataclass
class FeederSignals:
    """Everything the feeder receives from the city layer (one scenario)."""
    price_da: np.ndarray        # R3 day-ahead MCP, INR/kWh (capped)
    shed_frac_da: np.ndarray    # R3 domestic shed fraction expected by the DA market
    shed_frac_rt: np.ndarray    # R3 domestic shed fraction actually required in RT
    rotation_trip: np.ndarray   # bool: pilot's rotation group is tripped this step
    sps_trip: np.ndarray        # bool: SPS block containing the pilot operates this step


@dataclass
class FeederResult:
    mode: str
    ts: pd.DataFrame
    metrics: dict
    fairness: dict = field(default_factory=dict)
    reserves: list = field(default_factory=list)
    comms: list = field(default_factory=list)
    sizing: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- planning
def plan_day(sc: Scenario, steps: np.ndarray, net_q50: np.ndarray, pv_q50: np.ndarray,
             price: np.ndarray, shed_da: np.ndarray, soc0: float,
             floor: dict[int, float], soc_floor_kwh: float | None = None) -> dict:
    """Least-cost battery schedule for one day on the q50 forecast.

    floor: {local step index: minimum SOC in kWh} (uncertainty buffer at window start)."""
    f = sc.feeder
    b = f["battery"]
    dt = sc.dt_h
    E, P = b["energy_kwh"], b["power_kw"]
    target = f["capacity_kw"] * f["import_target_margin"]
    T = range(len(steps))
    m = pyo.ConcreteModel()
    m.T = pyo.Set(initialize=list(T))
    nn = pyo.NonNegativeReals
    m.imp = pyo.Var(m.T, domain=nn)
    m.exp = pyo.Var(m.T, domain=nn, bounds=(0, f["export_limit_kw"]))
    m.ch = pyo.Var(m.T, domain=nn, bounds=(0, P))
    m.dis = pyo.Var(m.T, domain=nn, bounds=(0, P))
    lo = b["soc_min"] * E if soc_floor_kwh is None else soc_floor_kwh
    m.soc = pyo.Var(m.T, bounds=(min(lo, soc0), b["soc_max"] * E))
    m.spill = pyo.Var(m.T, domain=nn)
    m.over = pyo.Var(m.T, domain=nn)
    m.capslack = pyo.Var(m.T, domain=nn)
    m.floorslack = pyo.Var(m.T, domain=nn)
    m.peak = pyo.Var(domain=nn)

    def bal(mm, t):
        return mm.imp[t] - mm.exp[t] == net_q50[t] - (pv_q50[t] - mm.spill[t]) + mm.ch[t] - mm.dis[t]
    m.bal = pyo.Constraint(m.T, rule=bal)
    m.spill_lim = pyo.Constraint(m.T, rule=lambda mm, t: mm.spill[t] <= pv_q50[t])

    def soc_rule(mm, t):
        prev = soc0 if t == 0 else mm.soc[t - 1]
        return mm.soc[t] == prev + (b["eta_charge"] * mm.ch[t] - mm.dis[t] / b["eta_discharge"]) * dt
    m.socdyn = pyo.Constraint(m.T, rule=soc_rule)
    m.rating = pyo.Constraint(m.T, rule=lambda mm, t: mm.imp[t] <= target + mm.over[t])
    m.peakdef = pyo.Constraint(m.T, rule=lambda mm, t: mm.peak >= mm.imp[t])

    # expected DISCOM curtailment requests (DA scarcity) become import caps
    def cap_rule(mm, t):
        if shed_da[t] <= 1e-4:
            return pyo.Constraint.Skip
        base_imp = max(net_q50[t] - pv_q50[t], 0.0)
        return mm.imp[t] <= base_imp * (1 - shed_da[t]) + mm.capslack[t]
    m.cap = pyo.Constraint(m.T, rule=cap_rule)

    def floor_rule(mm, t):
        if t not in floor:
            return pyo.Constraint.Skip
        return mm.soc[t] + mm.floorslack[t] >= floor[t]
    m.floor = pyo.Constraint(m.T, rule=floor_rule)
    m.term = pyo.Constraint(expr=m.soc[len(steps) - 1] >= min(soc0, 0.5 * E))

    deg = b["degradation_cost_inr_kwh"]
    m.obj = pyo.Objective(expr=sum(
        price[t] * m.imp[t] * dt - 0.5 * price[t] * m.exp[t] * dt
        + deg * (m.ch[t] + m.dis[t]) * dt
        + 200 * m.over[t] * dt + 150 * m.capslack[t] * dt + 80 * m.floorslack[t]
        + 5 * m.spill[t] * dt for t in T) + f["peak_charge_inr_kw_day"] * m.peak,
        sense=pyo.minimize)
    res = pyo.SolverFactory(SOLVER).solve(m)
    if str(res.solver.termination_condition) != "optimal":
        raise RuntimeError(f"feeder plan not optimal: {res.solver.termination_condition}")
    g = lambda v: np.array([pyo.value(v[t]) for t in T])
    return {"battery_kw": g(m.dis) - g(m.ch), "soc": g(m.soc), "import": g(m.imp)}


# --------------------------------------------------------------------------- helpers
def rotation_schedule(shed_frac: np.ndarray, n_groups: int, group: int) -> np.ndarray:
    """Rotational load-shedding: each step trip round(s * n) groups, advancing a pointer so
    every group takes its turn. Returns whether `group` is tripped at each step."""
    tripped = np.zeros(len(shed_frac), bool)
    ptr = 0
    for t, s in enumerate(shed_frac):
        k = int(round(min(max(s, 0), 1) * n_groups))
        if k == 0:
            continue
        groups = [(ptr + j) % n_groups for j in range(k)]
        tripped[t] = group in groups
        ptr = (ptr + k) % n_groups
    return tripped


# --------------------------------------------------------------------------- simulation
def simulate_feeder(sc: Scenario, fl: FeederLoads, fc: dict, sig: FeederSignals,
                    mode: str, trip_draws: np.ndarray, comm_cfg: dict | None = None) -> FeederResult:
    assert mode in ("baseline", "gridsetu")
    f = sc.feeder
    b = f["battery"]
    dt = sc.dt_h
    n = sc.n_steps
    spd = sc.steps_per_day
    gs = mode == "gridsetu"
    E, P = b["energy_kwh"], b["power_kw"]
    cap_kw = f["capacity_kw"]
    target = cap_kw * f["import_target_margin"]
    trip_cfg = f["overload_trip"]
    rng = sc.rng(9001)
    slices = build_slices(comm_cfg or sc.raw["comm_slices"], sc.rng(424242))
    ledger = FairnessLedger(fl.hh_load.shape[0], f["refusal_prob_tier3"], sc.rng(777))
    window = sc.time_mask(*f["evening_window"])
    evening_period = sc.time_mask("17:00", "23:00")
    usable = E * (b["soc_max"] - b["soc_min"])
    t1_all = fl.tier1
    # Tier-1 islanding reserve: hard floor for every use except grid-forming the island
    island_kwh = f.get("tier1_island_hours", 0.0) * float(t1_all.max()) if gs else 0.0
    floor_kwh = b["soc_min"] * E + island_kwh
    b_res = dict(b, soc_min=floor_kwh / E)   # what planning and published reserves may use
    t2_all = (fl.ent_tier2 * fl.ent_optin[:, None])
    sizing_log, reserves = [], []

    n_hh = fl.hh_load.shape[0]
    hh_status = np.zeros((n, n_hh), np.uint8)   # 0 supplied, 1 Tier-3 curtailed, 2 dark
    rec = {k: np.zeros(n) for k in (
        "gross", "net", "import", "battery_kw", "soc", "unserved", "curtail_t3", "curtail_t2",
        "tier1_unserved", "solar_avail", "solar_used", "spill", "limit", "cap_request",
        "rebound", "t3_avail")}
    state = np.empty(n, dtype=object)
    relief_req = np.zeros(n)   # kW of relief the DISCOM asked of this feeder

    soc = b["soc_init"] * E if gs else 0.0
    local_trip = 0
    queue = 0.0     # shiftable energy waiting to be served (kWh)
    plan = np.zeros(n)
    for d in range(sc.n_days):
        steps = np.arange(d * spd, (d + 1) * spd)
        if gs:
            ev = steps[evening_period[steps]]
            sz = size_reserve(d, ev, window[ev], fc["net_load"], fc["community_pv"], target, dt,
                              usable - island_kwh, f["reserve"], sig.shed_frac_da, rng)
            sizing_log.append(sz.__dict__)
            floor_local = {int(sz.window_start_step - steps[0]):
                           floor_kwh + (sz.buffer_kwh + sz.expected_cap_kwh) / b["eta_discharge"]}
            p = plan_day(sc, steps, fc["net_load"].q50[steps], fc["community_pv"].q50[steps],
                         sig.price_da[steps], sig.shed_frac_da[steps], soc, floor_local, floor_kwh)
            plan[steps] = p["battery_kw"]
            ws_local = int(steps[window[steps]][0] - steps[0])
            reserves.append(_reserve_object("T-24h", sc, fl, fc, steps, window, p["soc"][ws_local],
                                            int(steps[window[steps]][0]) - spd, 0.0, 1.0, P, E, b_res, rng))

        for t in steps:
            hh3 = fl.hh_tier3[:, t]
            t1 = t1_all[t]
            rebound_kw = 0.0
            gross = fl.hh_load[:, t].sum() + fl.ent_load[:, t].sum() + t1
            roof, cpv = fl.rooftop_pv[t], fl.community_pv[t]
            rec["solar_avail"][t] = roof + cpv
            rec["t3_avail"][t] = hh3.sum()

            # ---------------- upstream events and comms
            upstream_trip = False
            cap_req = np.inf
            st = "normal"
            if sig.sps_trip[t]:
                if gs and slices["urllc_protection"].send():
                    cap_req, st = 0.0, "sps_relief"
                else:
                    upstream_trip, st = True, "sps_trip"
            elif sig.shed_frac_rt[t] > 1e-4:
                base_imp = max(gross - roof - cpv, 0.0)
                request = base_imp * sig.shed_frac_rt[t]
                if gs and slices["control_2g4g"].send():
                    # can GridSetu deliver the requested relief? if not, the DISCOM
                    # treats the feeder like any other and applies the rotation trip
                    p_dis = min(P, max(soc - floor_kwh, 0) * b["eta_discharge"] / dt)
                    flex = p_dis + hh3.sum() * (1 - f["refusal_prob_tier3"]) + t2_all[:, t].sum()
                    if flex >= 0.95 * request or not sig.rotation_trip[t]:
                        cap_req, st = base_imp - request, "cap"
                        relief_req[t] = request
                    else:
                        upstream_trip, st = True, "cap_shortfall_trip"
                elif sig.rotation_trip[t]:
                    upstream_trip, st = True, "rotation_trip"
                if not gs:
                    relief_req[t] = request
            if local_trip > 0:
                st = "local_trip"
            energized = not upstream_trip and local_trip == 0

            if energized:
                limit = min(target if gs else np.inf, cap_req)
                net = gross - roof - cpv
                pb = plan[t] if gs else 0.0
                if gs:
                    p_dis = min(P, max(soc - floor_kwh, 0) * b["eta_discharge"] / dt)
                    p_ch = min(P, max(b["soc_max"] * E - soc, 0) / (b["eta_charge"] * dt))
                    imp = net - pb
                    if imp > limit:
                        pb = pb + (imp - limit)
                    if net - pb < -f["export_limit_kw"]:
                        pb = pb - (-(net - pb) - f["export_limit_kw"])
                    pb = float(np.clip(pb, -p_ch, p_dis))
                imp = net - pb
                spill = 0.0
                if imp < -f["export_limit_kw"]:
                    spill = min(cpv, -f["export_limit_kw"] - imp)
                    imp += spill
                c3 = c2 = 0.0
                excess = imp - limit
                if gs and excess > 1e-6:
                    c3, cmask = ledger.step(excess, hh3, dt)
                    hh_status[t, cmask] = 1
                    excess -= c3
                    if excess > 1e-6:
                        c2 = min(excess, t2_all[:, t].sum())
                        excess -= c2
                    imp -= c3 + c2
                else:
                    ledger.step(0.0, hh3, dt)
                # serve the rebound queue only with headroom and no active request
                if gs and queue > 1e-6 and c3 + c2 == 0 and not np.isfinite(cap_req):
                    rebound_kw = min(queue / dt, max(0.0, target - imp))
                    imp += rebound_kw
                    queue -= rebound_kw * dt
                queue += (c3 * f["shiftable_share_tier3"] + c2) * dt
                # protection: probabilistic trip on overload (same draws in both scenarios)
                ratio = imp / cap_kw
                p_trip = trip_cfg["max_prob_per_step"] * np.clip(
                    (ratio - 1) / trip_cfg["full_prob_at_overload"], 0, 1)
                if trip_draws[t] < p_trip:
                    local_trip = trip_cfg["restore_steps"]
                    st = "overload_event"
                soc -= (pb / b["eta_discharge"] if pb > 0 else pb * b["eta_charge"]) * dt
                rec["import"][t] = imp
                rec["battery_kw"][t] = pb
                rec["unserved"][t] = c3 + c2
                rec["curtail_t3"][t] = c3
                rec["curtail_t2"][t] = c2
                rec["spill"][t] = spill
                rec["solar_used"][t] = roof + cpv - spill
                rec["limit"][t] = limit if np.isfinite(limit) else np.nan
                rec["net"][t] = net
            else:
                ledger.step(0.0, hh3, dt)
                hh_status[t, :] = 2
                if local_trip > 0:
                    local_trip -= 1
                t1_served = 0.0
                pb = 0.0
                used_pv = 0.0
                if gs:  # intentional island: battery grid-forms the Tier-1 segment
                    p_dis = min(P, max(soc - b["soc_min"] * E, 0) * b["eta_discharge"] / dt)
                    p_ch = min(P, max(b["soc_max"] * E - soc, 0) / (b["eta_charge"] * dt))
                    pv_load = min(cpv, t1)
                    need = t1 - pv_load
                    if need <= p_dis:
                        charge = min(cpv - pv_load, p_ch)
                        pb = need if need > 0 else -charge
                        t1_served = t1
                        used_pv = pv_load + charge
                        soc -= (pb / b["eta_discharge"] if pb > 0 else pb * b["eta_charge"]) * dt
                        st = st + "+island"
                rec["battery_kw"][t] = pb
                rec["unserved"][t] = gross - t1_served
                rec["tier1_unserved"][t] = t1 - t1_served
                rec["solar_used"][t] = used_pv
                rec["spill"][t] = roof + cpv - used_pv
                rec["net"][t] = gross - roof - cpv
                rec["import"][t] = 0.0
                rec["limit"][t] = 0.0
            rec["gross"][t] = gross + rebound_kw
            rec["rebound"][t] = rebound_kw
            rec["soc"][t] = soc
            rec["cap_request"][t] = cap_req if np.isfinite(cap_req) else np.nan
            state[t] = st

        if gs:  # T-1h / T-15min / delivered / post-event for this day's window
            reserves.extend(_window_updates(sc, fl, fc, steps, window, rec, P, E, b_res, rng))

    if gs:  # AMI interval reads (verification/settlement) and dashboard pushes
        slices["mmtc_ami"].bulk(fl.hh_load.shape[0] * n)
        slices["embb_dashboard"].bulk(n)
    ts = pd.DataFrame(rec, index=sc.index)
    ts["state"] = state
    ts["relief_requested"] = relief_req
    ts["tier1"] = t1_all
    metrics = feeder_metrics(sc, fl, ts, window, E, b, queue)
    return FeederResult(mode, ts, metrics, ledger.summary() if gs else {}, reserves,
                        [s.stats() for s in slices.values()] if gs else [], sizing_log,
                        {"household_hours": ledger.hours.copy(), "hh_status": hh_status,
                         "household_events": ledger.events.copy()})


def _deliverability(sc, fc, wsteps, soc_now, flex_kwh, bias, scale, b, E, rng, n=800):
    """P(the evening shortfall above the import target <= energy GridSetu can deliver)."""
    target = sc.feeder["capacity_kw"] * sc.feeder["import_target_margin"]
    q50n = fc["net_load"].q50[wsteps] + bias
    sig = fc["net_load"].spread[wsteps] / 2.563 * scale
    pv = fc["community_pv"].q50[wsteps]
    z = 0.8 * rng.normal(size=(n, 1)) + 0.6 * rng.normal(size=(n, len(wsteps)))
    need = np.maximum(q50n + sig * z - pv - target, 0).sum(axis=1) * sc.dt_h
    avail = max(0.0, (soc_now - b["soc_min"] * E) * b["eta_discharge"]) + flex_kwh
    return float(np.mean(need <= avail))


def _reserve_object(stage, sc, fl, fc, steps, window, soc_ws, issued_step, bias, scale,
                    P, E, b, rng, delivered=None):
    wsteps = steps[window[steps]]
    ws, we = wsteps[0], wsteps[-1]
    dur = len(wsteps) * sc.dt_h
    e_bat = max(0.0, (soc_ws - b["soc_min"] * E) * b["eta_discharge"])
    bat_kw = min(P, e_bat / dur)
    t3 = float(fl.hh_tier3[:, wsteps].sum(axis=0).mean() * (1 - sc.feeder["refusal_prob_tier3"]))
    t2 = float((fl.ent_tier2[:, wsteps] * fl.ent_optin[:, None]).sum(axis=0).mean())
    conf = _deliverability(sc, fc, wsteps, soc_ws, (t3 + t2) * dur, bias, scale, b, E, rng)
    return ReliabilityReserve(
        feeder_id=FEEDER_ID, stage=stage, issued_at=str(sc.index[max(issued_step, 0)]),
        window_start=str(sc.index[ws]), window_end=str(sc.index[we] + pd.Timedelta(minutes=15)),
        reserve_kw=round(bat_kw + t3 + t2, 1), energy_kwh=round(e_bat + (t3 + t2) * dur, 1),
        duration_h=dur, confidence_pct=round(100 * conf, 1),
        cost_inr_kwh=round(b["degradation_cost_inr_kwh"] + 2.0, 2),
        battery_kw=round(bat_kw, 1), tier3_kw=round(t3, 1), tier2_kw=round(t2, 1),
        delivered_kw=delivered).to_dict()


def _window_updates(sc, fl, fc, steps, window, rec, P, E, b, rng) -> list:
    wsteps = steps[window[steps]]
    ws = wsteps[0]
    out = []
    for stage, lead, scale in (("T-1h", 4, 0.6), ("T-15min", 1, 0.4)):
        soc_now = rec["soc"][ws - lead]
        bias = rec["net"][ws - lead] - fc["net_load"].q50[ws - lead]   # persistence nowcast
        out.append(_reserve_object(stage, sc, fl, fc, steps, window, soc_now, ws - lead,
                                   bias, scale, P, E, b, rng))
    delivered = float(np.mean(np.maximum(rec["battery_kw"][wsteps], 0)
                              + rec["curtail_t3"][wsteps] + rec["curtail_t2"][wsteps]))
    rt = dict(out[-1])
    rt.update(stage="real-time", issued_at=str(sc.index[ws]), delivered_kw=round(delivered, 1))
    post = dict(rt)
    post.update(stage="post-event", issued_at=str(sc.index[wsteps[-1]] + pd.Timedelta(minutes=15)))
    return out + [rt, post]


def feeder_metrics(sc: Scenario, fl: FeederLoads, ts: pd.DataFrame, window: np.ndarray,
                   E: float, b: dict, queue_left: float) -> dict:
    dt = sc.dt_h
    days = sc.n_days
    served_imp = ts["import"]
    discharge = ts["battery_kw"].clip(lower=0).sum() * dt
    usable = E * (b["soc_max"] - b["soc_min"])
    t1_out_steps = (ts["tier1_unserved"] > 1e-3)
    unserved_total = ts["unserved"].sum() * dt - ts["rebound"].sum() * dt + queue_left
    return {
        "evening_window_unserved_kwh": float(ts["unserved"][window].sum() * dt),
        "total_unserved_kwh": float(max(unserved_total, 0.0)),
        "gross_unserved_kwh": float(ts["unserved"].sum() * dt),
        "critical_outage_hours": float(t1_out_steps.sum() * dt),
        "critical_unserved_kwh": float(ts["tier1_unserved"].sum() * dt),
        "feeder_outage_hours": float(ts["state"].astype(str).str.contains("trip").sum() * dt),
        "solar_utilisation_pct": float(100 * ts["solar_used"].sum() / max(ts["solar_avail"].sum(), 1e-9)),
        "feeder_peak_import_kw": float(served_imp.max()),
        "battery_cycles": float(discharge / usable) if usable else 0.0,
        "battery_discharge_kwh": float(discharge),
        "tier3_curtailed_kwh": float(ts["curtail_t3"].sum() * dt),
        "tier2_curtailed_kwh": float(ts["curtail_t2"].sum() * dt),
        "overload_trips": int((ts["state"] == "overload_event").sum()),
        "days": days,
    }
