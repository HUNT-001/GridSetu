"""End-to-end orchestration: weather -> loads -> forecasts -> city market (DA + RT) ->
feeder signals -> pilot feeder (baseline vs GridSetu) for one week.

Attribution is kept clean: the headline pilot comparison runs BOTH feeder modes on the
same baseline city signals, so every difference is caused by GridSetu alone. City-level
coordination (solar-hour irrigation, industrial DR) is reported as a separate layer."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import Scenario, load_scenario
from .feeder import FeederSignals, rotation_schedule, simulate_feeder
from .forecast import FeederForecaster
from .market import build_city_inputs, run_city
from .profiles import feeder_loads, history_weeks
from .weather import make_weather


@dataclass
class WeekResult:
    label: str
    sc: Scenario
    weather: pd.DataFrame
    feeder_loads: object
    forecast: dict
    forecast_skill: dict
    city: dict           # scenario -> {"inputs", "da", "rt"}
    feeder: dict         # variant -> FeederResult
    signals: dict        # scenario -> FeederSignals


def feeder_signals(sc: Scenario, inp, da, rt) -> FeederSignals:
    reg = sc.regions["R3"]
    cap = sc.raw["exchange_price"]["price_cap"]
    dom_fc = inp.loads_fc["R3"]["domestic"].values
    dom = inp.loads["R3"]["domestic"].values
    s_da = np.divide(da.shed["R3"]["domestic"].values, dom_fc, out=np.zeros_like(dom_fc), where=dom_fc > 0)
    s_rt = np.divide(rt.shed["R3"]["domestic"].values, dom, out=np.zeros_like(dom), where=dom > 0)
    rot = rotation_schedule(s_rt, int(reg["domestic_feeder_groups"]), int(reg["pilot_feeder_group"]))
    sps = np.zeros(sc.n_steps, bool)
    fq = sc.raw["frequency"]
    if fq.get("pilot_in_sps_block", False):
        n_restore = max(1, int(round(fq["restoration_minutes"] / (sc.dt_h * 60))))
        for o in sc.raw.get("forced_outages", []):
            s0 = sc.step_of(o["start"])
            if s0 < sc.n_steps:
                sps[s0:s0 + n_restore] = True
    return FeederSignals(price_da=da.mcp(cap)["R3"].values, shed_frac_da=np.clip(s_da, 0, 1),
                         shed_frac_rt=np.clip(s_rt, 0, 1), rotation_trip=rot, sps_trip=sps)


def run_week(sc: Scenario, label: str, cloudy_days: list[int] | None = None,
             comm_cfg: dict | None = None, verbose: bool = True, log=None) -> WeekResult:
    simc = sc.raw["simulation"]
    if log is None:
        log = print if verbose else (lambda *a, **k: None)
    wx = make_weather(sc.index, simc["latitude_deg"], simc["longitude_deg"], sc.rng_seed,
                      forced_cloudy_days=cloudy_days)
    fl, hh_scale = feeder_loads(sc, wx, seed=sc.rng_seed + 5)
    log(f"[{label}] training quantile forecasters on {simc['history_weeks']} synthetic history weeks")
    hist = history_weeks(sc, hh_scale, simc["history_weeks"])
    model = FeederForecaster(sc.steps_per_day, seed=sc.rng_seed).fit(hist)
    fc = model.predict(fl, last_history=hist[0])
    skill = {"net_load": fc["net_load"].skill(fl.net_load),
             "community_pv": fc["community_pv"].skill(fl.community_pv),
             "conformal_widening_kw": model.conformal}

    city, signals = {}, {}
    for name, coordinated in (("baseline", False), ("coordinated", True)):
        log(f"[{label}] clearing day-ahead market and real-time dispatch: {name} city")
        inp = build_city_inputs(sc, wx, coordinated)
        da, rt = run_city(sc, inp)
        city[name] = {"inputs": inp, "da": da, "rt": rt}
        signals[name] = feeder_signals(sc, inp, da, rt)

    draws = sc.rng(31337).random(sc.n_steps)   # common random numbers for protection trips
    feeders = {}
    for variant, mode, city_name in (("baseline", "baseline", "baseline"),
                                     ("gridsetu", "gridsetu", "baseline"),
                                     ("gridsetu_coordinated", "gridsetu", "coordinated")):
        log(f"[{label}] simulating pilot feeder: {variant}")
        feeders[variant] = simulate_feeder(sc, fl, fc, signals[city_name], mode, draws, comm_cfg)
    return WeekResult(label, sc, wx, fl, fc, skill, city, feeders, signals)


def stress_and_representative(config_path=None, overrides: dict | None = None,
                              comm_cfg: dict | None = None, verbose: bool = True, log=None) -> dict:
    """Monthly composite = 3 representative weeks + 1 stress week (forced outage, two
    overcast monsoon days). The representative week has no forced outage."""
    stress = load_scenario(config_path, overrides)
    rep_over = {**(overrides or {}), "forced_outages": [],
                "simulation": {**(overrides or {}).get("simulation", {}),
                               "seed": stress.rng_seed + 1}}
    rep = load_scenario(config_path, rep_over)
    return {
        "stress": run_week(stress, "stress week", cloudy_days=[2, 4], comm_cfg=comm_cfg, verbose=verbose,
                           log=log),
        "representative": run_week(rep, "representative week", cloudy_days=None,
                                   comm_cfg=comm_cfg, verbose=verbose, log=log),
    }
