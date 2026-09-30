"""Turns simulation results into compact, columnar JSON payloads for the dashboard.

Design rules (they are what makes the front end feel instant):
- One payload per (run, resource, week). Everything a page animates is in it, so
  playback never touches the network.
- Columnar arrays, floats rounded to what a chart can show, per-household states packed
  as base64 uint8. Payloads are serialised once with orjson and gzipped once; the server
  only ever streams pre-compressed bytes.
- Run IDs are content hashes, so every URL is immutable and cacheable forever."""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import time
from pathlib import Path
from typing import Callable

import numpy as np
import orjson
import pandas as pd

from ..config import CLASSES, DEFAULT_CONFIG, load_scenario
from ..island import simulate_island
from ..metrics import class_factors, feeder_factors, market_stats, plant_factors, system_factors
from ..network import run_power_flow
from ..runner import VARIANTS, _agg, monthly_composite
from ..simulate import stress_and_representative
from ..wams import wams_study
from ..citymap import build_map

ENGINE_VERSION = "1.1.0"
WEEKS = ("stress", "representative")
STATE_CODES = ["normal", "cap", "sps_relief", "rotation_trip", "sps_trip", "cap_shortfall_trip",
               "cap_shortfall_trip+island", "rotation_trip+island", "sps_trip+island",
               "local_trip", "local_trip+island", "overload_event"]


def run_id_for(overrides: dict | None, seeds: int, config_path=None) -> str:
    cfg = Path(config_path or DEFAULT_CONFIG).read_bytes()
    from ..citymap import OSM_FILE
    if OSM_FILE.exists():                 # real streets change the map, so they change the run id
        cfg += hashlib.sha1(OSM_FILE.read_bytes()).digest()
    blob = json.dumps({"o": overrides or {}, "s": seeds, "v": ENGINE_VERSION}, sort_keys=True).encode()
    return hashlib.sha1(cfg + blob).hexdigest()[:12]


def _r(x, nd=2):
    a = np.asarray(x, dtype=float)
    a = np.where(np.isfinite(a), np.round(a, nd), np.nan)
    return [None if np.isnan(v) else float(v) for v in a]


def _week_axis(w) -> dict:
    return {"t0": w.sc.index[0].isoformat(), "n": int(w.sc.n_steps), "dt_min": int(w.sc.dt_h * 60)}


def _events(w, scen: str) -> list:
    sc = w.sc
    ev = []
    for o in sc.raw.get("forced_outages", []):
        ev.append({"step": sc.step_of(o["start"]), "kind": "outage", "label": f"{o['unit']} forced outage"})
        end = sc.step_of(o["end"])
        if end < sc.n_steps:
            ev.append({"step": end, "kind": "restore", "label": f"{o['unit']} back in service"})
    rt = w.city[scen]["rt"]
    shed = sum(rt.shed[r].sum(axis=1).values for r in rt.shed)
    on = shed > 0.05
    starts = np.flatnonzero(on & ~np.r_[False, on[:-1]])
    for s in starts:
        ev.append({"step": int(s), "kind": "shedding", "label": f"Load shedding starts ({shed[s]:.0f} MW)"})
    da = w.city[scen]["da"]
    cap = sc.raw["exchange_price"]["price_cap"]
    sc_on = da.price.max(axis=1).values >= cap - 1e-6
    for s in np.flatnonzero(sc_on & ~np.r_[False, sc_on[:-1]]):
        ev.append({"step": int(s), "kind": "scarcity", "label": "Day-ahead price hits the ₹10 ceiling"})
    return sorted(ev, key=lambda e: e["step"])


def city_payload(w) -> dict:
    sc = w.sc
    out = {**_week_axis(w), "weather": {"csi": _r(w.weather["csi"], 3), "ghi": _r(w.weather["ghi"], 0),
                                        "temp": _r(w.weather["temp_c"], 1),
                                        "wind_cf": _r(w.weather["wind_cf"], 3),
                                        "cos_zenith": _r(w.weather["cos_zenith"], 3)},
           "tie_limit": {f"{t['from']}-{t['to']}": t["mw"] for t in sc.raw["interties"]},
           "scenarios": {}}
    cap = sc.raw["exchange_price"]["price_cap"]
    for scen in ("baseline", "coordinated"):
        c = w.city[scen]
        inp, da, rt = c["inputs"], c["da"], c["rt"]
        out["scenarios"][scen] = {
            "gen": {g: _r(rt.gen[g], 1) for g in rt.gen},
            "avail": {g: _r(inp.renew_avail[g], 1) for g in inp.renew_avail},
            "flow": {k: _r(rt.flow[k], 1) for k in rt.flow},
            "price_da": {r: _r(da.mcp(cap)[r], 2) for r in sc.regions},
            "price_rt": {r: _r(rt.mcp(cap)[r], 2) for r in sc.regions},
            "load": {r: {k: _r(inp.loads[r][k], 2) for k in CLASSES} for r in sc.regions},
            "shed": {r: {k: _r(rt.shed[r][k], 2) for k in CLASSES} for r in sc.regions},
            "rooftop": {r: _r(inp.rooftop[r], 2) for r in sc.regions},
            "dr": _r(rt.dr, 2),
            "exchange_price": _r(inp.exch_price, 2),
            "events": _events(w, scen),
        }
    return out


def feeder_payload(w) -> dict:
    sc = w.sc
    fl = w.feeder_loads
    variants = {}
    code = {s: i for i, s in enumerate(STATE_CODES)}
    for v in VARIANTS:
        res = w.feeder[v]
        ts = res.ts
        E = sc.feeder["battery"]["energy_kwh"]
        series = {k: _r(ts[k], 2) for k in ("import", "battery_kw", "gross", "net", "unserved",
                                             "curtail_t3", "curtail_t2", "tier1", "tier1_unserved",
                                             "solar_avail", "solar_used", "limit", "cap_request",
                                             "relief_requested")}
        series["soc_pct"] = _r(100 * ts["soc"] / E, 1)
        st = res.extra["hh_status"]
        variants[v] = {
            "series": series,
            "state": [code.get(str(s), 0) for s in ts["state"]],
            "metrics": res.metrics,
            "fairness": res.fairness,
            "reserves": res.reserves,
            "comms": res.comms,
            "hh_status_b64": base64.b64encode(st.tobytes()).decode(),   # [step][household] uint8
            "hh_lit_pct": _r(100 * (st == 0).mean(axis=1), 1),
        }
    fc = w.forecast
    return {**_week_axis(w), "state_codes": STATE_CODES, "n_households": int(fl.hh_load.shape[0]),
            "capacity_kw": sc.feeder["capacity_kw"],
            "target_kw": sc.feeder["capacity_kw"] * sc.feeder["import_target_margin"],
            "evening_window": sc.feeder["evening_window"],
            "critical": {k: _r(v, 1) for k, v in fl.critical.items()},
            "forecast": {"net": {q: _r(getattr(fc["net_load"], q), 1) for q in ("q10", "q50", "q90")},
                         "pv": {q: _r(getattr(fc["community_pv"], q), 1) for q in ("q10", "q50", "q90")}},
            "actual_net": _r(fl.net_load, 1),
            "variants": variants}


def households_payload(w) -> dict:
    sc = w.sc
    fl = w.feeder_loads
    dt = sc.dt_h
    n_hh = fl.hh_load.shape[0]
    spd = sc.steps_per_day
    gs, base = w.feeder["gridsetu"], w.feeder["baseline"]
    st_g, st_b = gs.extra["hh_status"], base.extra["hh_status"]
    daily = fl.hh_load.reshape(n_hh, sc.n_days, spd).sum(axis=2) * dt
    nodes = np.minimum((np.arange(n_hh) * 5) // n_hh, 4) + 1
    rows = {"id": [f"HH-{i + 1:03d}" for i in range(n_hh)],
            "node": nodes.tolist(),
            "peak_kw": _r(fl.hh_load.max(axis=1), 2),
            "energy_kwh": _r(fl.hh_load.sum(axis=1) * dt, 1),
            "tier3_kwh": _r(fl.hh_tier3.sum(axis=1) * dt, 1),
            "curtailed_h": _r((st_g == 1).sum(axis=0) * dt, 2),
            "events": gs.extra["household_events"].tolist(),
            "dark_h_gridsetu": _r((st_g == 2).sum(axis=0) * dt, 2),
            "dark_h_baseline": _r((st_b == 2).sum(axis=0) * dt, 2),
            "daily_kwh": [_r(d, 1) for d in daily]}
    t_idx, h_idx = np.nonzero(st_g == 1)
    order = np.lexsort((h_idx, t_idx))
    t_idx, h_idx = t_idx[order], h_idx[order]
    log = {"step": t_idx.tolist(), "hh": h_idx.tolist(),
           "kw": _r(fl.hh_tier3[h_idx, t_idx], 3)}
    ents = {"id": [f"ME-{i + 1:02d}" for i in range(fl.ent_load.shape[0])],
            "opt_in": fl.ent_optin.tolist(), "peak_kw": _r(fl.ent_load.max(axis=1), 2),
            "shiftable_kw": _r(fl.ent_tier2.max(axis=1), 2)}
    return {**_week_axis(w), "households": rows, "curtailment_log": log, "enterprises": ents,
            "fairness": gs.fairness}


def wams_payload(wams: dict) -> dict:
    if not wams:
        return {"timestamp": None, "fleet_ffr_mw": 0, "runs": {}}
    runs = {}
    for k, v in wams["runs"].items():
        ts = v["ts"].iloc[::2]   # 25 frames/s is plenty for the screen
        runs[k] = {"summary": v["summary"], "t": _r(ts.t_s, 2), "f_city": _r(ts.f_city_hz, 4),
                   "f_nat": _r(ts.f_national_hz, 4), "tie": _r(ts.tie_import_mw, 1),
                   "shed": _r(ts.shed_mw, 1), "ffr": _r(ts.ffr_mw, 2), "gov": _r(ts.governor_mw, 1)}
    return {"timestamp": wams["timestamp"], "fleet_ffr_mw": wams["fleet_ffr_mw"], "runs": runs}


def island_payload(w) -> dict:
    out = {**_week_axis(w), "strategies": {}}
    for s in ("legacy", "gridsetu"):
        ts, m = simulate_island(w.sc, w.weather, s)
        out["strategies"][s] = {"metrics": m, **{k: _r(ts[k], 1) for k in ts.columns}}
    return out


def network_payload(pf_base: pd.DataFrame, pf_gs: pd.DataFrame, every: int) -> dict:
    return {"every": every, "baseline": {k: _r(pf_base[k], 3) for k in pf_base.columns},
            "gridsetu_feeder_v": _r(pf_gs["feeder_min_v_pu"], 4)}


def _pack(obj) -> bytes:
    return gzip.compress(orjson.dumps(obj, option=orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_NON_STR_KEYS,
                                      default=_default), compresslevel=6)


def _default(o):
    if isinstance(o, (np.floating,)):
        return float(o) if np.isfinite(o) else None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return o.isoformat()
    raise TypeError(type(o))


def _clean(o):
    """Replace NaN/inf with None recursively (orjson would emit them as null anyway for
    numpy, but plain floats need this)."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o


def compute_run(overrides: dict | None, label: str, seeds: int, progress: Callable[[str, float], None],
                pf_every: int = 2, config_path=None, studies: bool | None = None) -> dict[str, bytes]:
    """Run the study and return {resource_key: gzipped JSON bytes}.

    studies: also run the Phase 2 fleet and unit-commitment studies (default: only for
    multi-seed reference runs, to keep one-seed lab runs quick)."""
    t0 = time.time()
    if studies is None:
        studies = seeds > 1
    stages = 6 + seeds + (2 if studies else 0)
    k = [0]

    def step(msg):
        k[0] += 1
        progress(msg, min(0.98, k[0] / stages))

    per_seed, primary = [], None
    for i in range(seeds):
        ov = dict(overrides or {})
        ov["simulation"] = {**ov.get("simulation", {}), "seed": 42 + 100 * i}
        step(f"Simulating seed {i + 1} of {seeds}: weather, loads, forecasts, markets, feeder")
        res = stress_and_representative(config_path, ov, verbose=False,
                                        log=lambda m: progress(m, min(0.98, k[0] / stages)))
        per_seed.append({v: monthly_composite(res["stress"].feeder[v].metrics,
                                              res["representative"].feeder[v].metrics) for v in VARIANTS})
        if primary is None:
            primary = res
    stress, rep = primary["stress"], primary["representative"]
    sc = stress.sc
    c = stress.city["baseline"]

    step("AC power flow over the stress week")
    pf_b = run_power_flow(sc, c["inputs"], c["rt"], stress.feeder["baseline"], every=pf_every)
    pf_g = run_power_flow(sc, c["inputs"], c["rt"], stress.feeder["gridsetu"], every=pf_every)
    step("Frequency event study (PMU rate)")
    wams = wams_study(sc, c["inputs"], c["rt"])
    step("Isolated microgrid and planning factors")
    island = {wk: island_payload(w) for wk, w in (("stress", stress), ("representative", rep))}
    cf = class_factors(sc, c["inputs"].loads)
    pl = plant_factors(sc, c["rt"])

    extra = {}
    if studies:
        step("City-wide fleet: 20 feeders under baseline and GridSetu")
        for wk, w in (("stress", stress), ("representative", rep)):
            extra[f"fleet:{wk}"] = fleet_payload(w)
        extra["map"] = build_map(extra["fleet:stress"]["feeders"])
        step("Unit commitment with PyPSA (day-ahead MILP)")
        for wk, w in (("stress", stress), ("representative", rep)):
            extra[f"uc:{wk}"] = uc_payload(w)

    step("Packing payloads")
    weeks_meta = {}
    for wk, w in (("stress", stress), ("representative", rep)):
        weeks_meta[wk] = {**_week_axis(w), "label": w.label.capitalize(),
                          "outages": w.sc.raw.get("forced_outages", [])}
    cfg = sc.raw
    meta = {
        "studies": sorted({k.split(":")[0] for k in extra}),
        "engine": ENGINE_VERSION, "label": label, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "seeds": seeds, "overrides": overrides or {}, "weeks": weeks_meta, "state_codes": STATE_CODES,
        "config": {"regions": {r: {"name": v["name"], "peak_mw": v["peak_mw"],
                                   "rooftop_solar_mwp": v.get("rooftop_solar_mwp", 0)}
                               for r, v in cfg["regions"].items()},
                   "generators": cfg["generators"], "interties": cfg["interties"],
                   "classes": cfg["load_classes"], "feeder": cfg["pilot_feeder"],
                   "coordination": cfg["coordination"], "comm_slices": cfg["comm_slices"],
                   "island": cfg["island_microgrid"], "price_cap": cfg["exchange_price"]["price_cap"]},
    }
    summary = {
        "monthly": {v: _agg([s[v] for s in per_seed]) for v in VARIANTS},
        "weekly": {wk: {v: w.feeder[v].metrics for v in VARIANTS}
                   for wk, w in (("stress", stress), ("representative", rep))},
        "city": {wk: {s: market_stats(w.sc, w.city[s]["da"], w.city[s]["rt"], w.city[s]["inputs"])
                      for s in ("baseline", "coordinated")}
                 for wk, w in (("stress", stress), ("representative", rep))},
        "system_factors": system_factors(sc, c["inputs"].loads, c["rt"]),
        "feeder_factors": feeder_factors(sc, stress.feeder_loads),
        "forecast_skill": stress.forecast_skill,
        "fairness": stress.feeder["gridsetu"].fairness,
        "comms": stress.feeder["gridsetu"].comms,
        "wams": {k: v["summary"] for k, v in wams.get("runs", {}).items()},
        "island": {wk: {s: island[wk]["strategies"][s]["metrics"] for s in ("legacy", "gridsetu")}
                   for wk in island},
        "power_flow": {"max_line_loading_pct": float(pf_b["max_tie_loading_pct"].max()),
                       "samples_over_100pct": int((pf_b["max_tie_loading_pct"] > 100).sum()),
                       "mean_losses_mw": float(pf_b["losses_mw"].mean())},
        "class_factors": cf.to_dict(orient="records"),
        "plant_factors": pl.to_dict(orient="records"),
        "runtime_s": round(time.time() - t0, 1),
    }
    payloads = {"meta": meta, "summary": summary, "wams": wams_payload(wams),
                "network:stress": network_payload(pf_b, pf_g, pf_every)}
    for wk, w in (("stress", stress), ("representative", rep)):
        payloads[f"city:{wk}"] = city_payload(w)
        payloads[f"feeder:{wk}"] = feeder_payload(w)
        payloads[f"households:{wk}"] = households_payload(w)
        payloads[f"island:{wk}"] = island[wk]
    payloads.update(extra)
    return {k: _pack(_clean(v)) for k, v in payloads.items()}


def fleet_payload(w) -> dict:
    from ..fleet import run_fleet
    r = run_fleet(w)
    code = {st: i for i, st in enumerate(STATE_CODES)}
    groups = [row["group"] for row in r["feeders"]]
    states, imports = {}, {}
    for m in ("baseline", "gridsetu"):
        st = np.array([[code.get(x, 0) for x in r["series"][(g, m)]["state"]] for g in groups], dtype=np.uint8)
        imp = np.array([np.nan_to_num(r["series"][(g, m)]["import"]) for g in groups]).round().astype(np.int16)
        states[m] = base64.b64encode(st.tobytes()).decode()       # [feeder][step]
        imports[m] = base64.b64encode(imp.tobytes()).decode()     # int16 little-endian kW
    return {**_week_axis(w), "state_codes": STATE_CODES, "feeders": r["feeders"], "curve": r["curve"],
            "states_b64": states, "import_b64": imports, "note": r["note"]}


def uc_payload(w) -> dict:
    from ..uc import lp_cost, run_uc
    c = w.city["baseline"]
    u = run_uc(w.sc, c["inputs"])
    cap = w.sc.raw["exchange_price"]["price_cap"]
    lp = lp_cost(w.sc, c["inputs"], c["da"])
    lp_shed = float(sum(c["da"].shed[r].sum().sum() for r in c["da"].shed) * w.sc.dt_h)
    return {**_week_axis(w), "status": {g: u.status[g].astype(int).tolist() for g in u.status},
            "gen_uc": {g: _r(u.gen[g], 1) for g in u.gen}, "gen_lp": {g: _r(c["da"].gen[g], 1) for g in u.status},
            "price_uc": {r: _r(u.price[r].clip(upper=cap), 2) for r in u.price},
            "price_lp": {r: _r(c["da"].mcp(cap)[r], 2) for r in u.price},
            "startups": u.startups, "cost_uc_inr": u.cost_inr, "cost_lp_inr": lp,
            "shed_uc_mwh": float(u.shed.sum() * w.sc.dt_h), "shed_lp_mwh": lp_shed,
            "hours_on": {g: float(u.status[g].sum() * w.sc.dt_h) for g in u.status},
            "note": "Day-ahead schedules on the forecast. Ramp limits are left out of the commitment problem."}


def load_scenario_defaults(config_path=None) -> dict:
    """Editable knobs for the scenario lab, with their current values."""
    sc = load_scenario(config_path)
    f = sc.feeder
    return {
        "battery_kwh": f["battery"]["energy_kwh"], "battery_kw": f["battery"]["power_kw"],
        "capacity_kw": f["capacity_kw"], "tier1_island_hours": f["tier1_island_hours"],
        "control_loss": sc.raw["comm_slices"]["control_2g4g"]["loss"],
        "forced_outage": bool(sc.raw.get("forced_outages")),
        "irrigation_shift": sc.raw["coordination"]["irrigation_shift_to_solar_hours"],
        "industrial_dr_mw": sc.raw["coordination"]["industrial_dr_mw"],
    }


def knobs_to_overrides(knobs: dict, config_path=None) -> dict:
    d = load_scenario_defaults(config_path)
    o: dict = {}
    fb = {}
    if knobs.get("battery_kwh", d["battery_kwh"]) != d["battery_kwh"]:
        fb["energy_kwh"] = float(knobs["battery_kwh"])
    if knobs.get("battery_kw", d["battery_kw"]) != d["battery_kw"]:
        fb["power_kw"] = float(knobs["battery_kw"])
    pf = {}
    if fb:
        pf["battery"] = fb
    for key in ("capacity_kw", "tier1_island_hours"):
        if key in knobs and knobs[key] != d[key]:
            pf[key] = float(knobs[key])
    if pf:
        o["pilot_feeder"] = pf
    if "control_loss" in knobs and knobs["control_loss"] != d["control_loss"]:
        o["comm_slices"] = {"control_2g4g": {"loss": float(knobs["control_loss"])}}
    if "forced_outage" in knobs and not knobs["forced_outage"]:
        o["forced_outages"] = []
    co = {}
    if "irrigation_shift" in knobs and knobs["irrigation_shift"] != d["irrigation_shift"]:
        co["irrigation_shift_to_solar_hours"] = bool(knobs["irrigation_shift"])
    if "industrial_dr_mw" in knobs and knobs["industrial_dr_mw"] != d["industrial_dr_mw"]:
        co["industrial_dr_mw"] = float(knobs["industrial_dr_mw"])
    if co:
        o["coordination"] = co
    return o
