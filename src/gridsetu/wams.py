"""Wide-area monitoring and control (WAMS) study: sub-second frequency dynamics sampled
like PMUs (50 frames/s, IEEE C37.118 reporting rate for 50 Hz systems).

Two-area model: the city control area and the rest of the Indian grid (a large equivalent)
joined by the national tie. Each area has inertia, load damping and a first-order
governor with limited headroom; the tie follows the angle difference.

Case A, interconnected: G1B trips. The rest of the grid holds frequency, so the tie
  picks up the loss and overloads; the special protection scheme (SPS) sheds
  pre-designated feeder blocks to bring tie flow back under its thermal limit.
Case B, islanding: the tie itself trips while importing, the city is islanded with a
  deficit, and under-frequency load shedding (UFLS) stages operate.

GridSetu variant: feeders running GridSetu deliver fast frequency response (FFR) from
their batteries and Tier-3 loads within ~200 ms; SPS takes that relief instead of
tripping them, while UFLS (last-resort) still trips them and they island Tier-1."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import Scenario


@dataclass
class OperatingPoint:
    load_mw: float
    kinetic_mws: float          # stored kinetic energy of online synchronous units, after the event
    gov_headroom_mw: float
    gov_down_mw: float          # room to back units down towards their minimum
    gov_capacity_mw: float
    import_mw: float
    lost_mw: float              # generation (case A) or tie import (case B) lost at t=0
    fleet_ffr_mw: float         # GridSetu fast response available city-wide


def operating_point(sc: Scenario, inp, rt, step: int, case: str, fleet_ffr_mw: float,
                    tripped_unit: str = "G1B") -> OperatingPoint:
    gens = sc.generators
    before = step - 1 if step > 0 else step    # pre-contingency operating point
    served = sum(inp.loads[r].values[before].sum() - rt.shed[r].values[before].sum()
                 - inp.rooftop[r][before] for r in sc.regions)
    ke, head, down, cap = 0.0, 0.0, 0.0, 0.0
    for g, v in gens.items():
        if v["kind"] not in ("thermal", "gas", "hydro"):
            continue
        p = rt.gen[g].values[before]
        if p <= 0.1 or (case == "A" and g == tripped_unit):
            continue
        ke += v.get("inertia_h_s", 4.0) * v["pmax_mw"]
        head += max(v["pmax_mw"] - p, 0.0)
        down += max(p - v.get("pmin_mw", 0.0), 0.0)
        cap += v["pmax_mw"]
    imp = rt.gen["IMP"].values[before]
    lost = rt.gen[tripped_unit].values[before] if case == "A" else imp
    return OperatingPoint(served, ke, head, down, cap, imp, lost, fleet_ffr_mw)


def simulate_event(sc: Scenario, op: OperatingPoint, case: str, gridsetu: bool,
                   t_end: float = 60.0, h: float = 0.005) -> tuple[pd.DataFrame, dict]:
    fq = sc.raw["frequency"]
    f0 = fq["nominal_hz"]
    nat = fq["national_equivalent"]
    tie = fq["tie"]
    M1 = 2 * op.kinetic_mws / f0                       # MW*s/Hz
    D1 = fq["load_damping_pu"] * op.load_mw / f0       # MW/Hz
    K1 = op.gov_capacity_mw / (fq["governor_droop"] * f0)
    M2 = 2 * nat["inertia_h_s"] * nat["base_mw"] / f0
    D2 = 0.4 * nat["frc_mw_per_hz"]
    K2 = 0.6 * nat["frc_mw_per_hz"]
    T12 = tie["sync_coeff_mw_per_rad"]
    Dt = tie.get("damping_mw_per_hz", 0.0)
    tau_g, tau_ffr = fq["governor_tau_s"], fq["ffr_tau_s"]
    ffr_max = op.fleet_ffr_mw if gridsetu else 0.0
    connected = case == "A"

    df1 = df2 = pm1 = pm2 = p12 = ffr = 0.0
    shed = 0.0
    sps_timer, sps_done = 0.0, False
    stages = [dict(s, done=False, timer=0.0) for s in fq["ufls_stages"]]
    events, rows = [], []
    n = int(t_end / h)
    rec_every = int(round(0.02 / h))
    for k in range(n + 1):
        t = k * h
        deficit = op.lost_mw
        # tie flow is only defined while connected
        ptie = p12 + Dt * (df1 - df2) if connected else 0.0
        imp_flow = op.import_mw - ptie if connected else 0.0
        acc1 = (pm1 + ffr + shed - deficit - D1 * df1 - ptie) / M1
        acc2 = (pm2 - D2 * df2 + ptie) / M2 if connected else 0.0
        # FFR: triggered below 49.9 Hz (or on SPS signal), first-order 200 ms response
        trig = df1 < -0.1 or (connected and imp_flow > tie["thermal_limit_mw"])
        ffr += h * ((ffr_max if trig else 0.0) - ffr) / tau_ffr
        pm1 += h * (np.clip(-K1 * df1, -op.gov_down_mw, op.gov_headroom_mw) - pm1) / tau_g
        pm2 += h * (-K2 * df2 - pm2) / tau_g
        df1 += h * acc1          # semi-implicit Euler: update frequencies first,
        df2 += h * acc2          # then the tie angle, keeps the inter-area mode stable
        if connected:
            p12 += h * 2 * np.pi * T12 * (df1 - df2)
        # SPS on tie overload
        if connected and not sps_done:
            sps_timer = sps_timer + h if imp_flow > tie["thermal_limit_mw"] else 0.0
            if sps_timer >= tie["sps_arm_seconds"]:
                amount = max(imp_flow - tie["sps_target_mw"], 0.0)
                shed += amount
                sps_done = True
                events.append({"t_s": round(t, 3), "event": "SPS operated", "mw": round(amount, 1)})
        # UFLS stages (islanded case)
        if not connected:
            for i, st in enumerate(stages):
                if st["done"]:
                    continue
                st["timer"] = st["timer"] + h if f0 + df1 < st["hz"] else 0.0
                if st["timer"] >= 0.15:   # relay + breaker time
                    amt = st["share"] * op.load_mw
                    shed += amt
                    st["done"] = True
                    events.append({"t_s": round(t, 3), "event": f"UFLS stage {i + 1} ({st['hz']} Hz)",
                                   "mw": round(amt, 1)})
        if k % rec_every == 0:
            rows.append({"t_s": t, "f_city_hz": f0 + df1, "f_national_hz": f0 + df2,
                         "tie_import_mw": imp_flow, "governor_mw": pm1, "ffr_mw": ffr,
                         "shed_mw": shed, "rocof_hz_s": acc1})
    ts = pd.DataFrame(rows)
    rocof_500ms = ts["f_city_hz"].diff(25).div(0.5).min()
    stages_hit = [e for e in events if e["event"].startswith("UFLS")]
    pilot_stage = fq["pilot_feeder_ufls_stage"]
    pilot_tripped = (case == "A" and any(e["event"] == "SPS operated" for e in events)
                     and fq.get("pilot_in_sps_block", False)) or \
                    (case == "B" and len(stages_hit) >= pilot_stage)
    summary = {
        "case": case, "variant": "gridsetu" if gridsetu else "baseline",
        "lost_mw": round(op.lost_mw, 1), "system_load_mw": round(op.load_mw, 1),
        "inertia_h_equiv_s": round(op.kinetic_mws / max(op.load_mw, 1), 2),
        "nadir_hz": round(float(ts["f_city_hz"].min()), 3),
        "rocof_500ms_hz_s": round(float(rocof_500ms), 3),
        "settling_hz": round(float(ts["f_city_hz"].iloc[-1]), 3),
        "peak_tie_import_mw": round(float(ts["tie_import_mw"].max()), 1) if connected else None,
        "load_shed_mw": round(shed, 1), "ffr_peak_mw": round(float(ts["ffr_mw"].max()), 2),
        "events": events,
        # SPS asks GridSetu feeders for their committed relief instead of tripping them;
        # UFLS is a last-resort safety net and trips every wired feeder, GridSetu or not
        # (a GridSetu feeder then islands its Tier-1 loads on the battery).
        "pilot_feeder_tripped": bool(pilot_tripped and (case == "B" or not gridsetu)),
    }
    return ts, summary


def wams_study(sc: Scenario, inp, rt) -> dict:
    """Run both cases x both variants at the forced-outage instant."""
    o = sc.raw.get("forced_outages", [])
    if not o:
        return {}
    step = sc.step_of(o[0]["start"])
    coord = sc.raw["coordination"]
    fleet_feeders_mw = coord["gridsetu_feeder_share_r3"] * sc.regions["R3"]["peak_mw"]["domestic"]
    fleet_ffr = fleet_feeders_mw * (coord["gridsetu_battery_kw_per_feeder_peak_kw"]
                                    + sc.feeder["tier3_share_of_household"])
    out = {"step": step, "timestamp": str(sc.index[step]), "fleet_ffr_mw": round(fleet_ffr, 2),
           "runs": {}}
    for case in ("A", "B"):
        op = operating_point(sc, inp, rt, step, case, fleet_ffr)
        for gs in (False, True):
            ts, summ = simulate_event(sc, op, case, gs)
            out["runs"][f"{case}_{'gridsetu' if gs else 'baseline'}"] = {"ts": ts, "summary": summ}
    return out
