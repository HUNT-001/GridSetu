"""Full Phase 1 pipeline: multi-seed runs, monthly composite, power flow, WAMS, isolated
microgrid, planning factors, charts and machine-readable outputs."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import plots
from .island import simulate_island
from .metrics import class_factors, feeder_factors, market_stats, plant_factors, system_factors
from .network import run_power_flow
from .simulate import stress_and_representative
from .wams import wams_study

ADDITIVE = ["evening_window_unserved_kwh", "total_unserved_kwh", "gross_unserved_kwh",
            "critical_outage_hours", "critical_unserved_kwh", "feeder_outage_hours",
            "battery_cycles", "battery_discharge_kwh", "tier3_curtailed_kwh",
            "tier2_curtailed_kwh", "overload_trips"]
REP_WEEKS_PER_MONTH = 3
VARIANTS = ("baseline", "gridsetu", "gridsetu_coordinated")


def monthly_composite(stress: dict, rep: dict) -> dict:
    out = {k: REP_WEEKS_PER_MONTH * rep[k] + stress[k] for k in ADDITIVE}
    out["feeder_peak_import_kw"] = max(rep["feeder_peak_import_kw"], stress["feeder_peak_import_kw"])
    out["solar_utilisation_pct"] = (REP_WEEKS_PER_MONTH * rep["solar_utilisation_pct"]
                                    + stress["solar_utilisation_pct"]) / (REP_WEEKS_PER_MONTH + 1)
    return out


def _agg(values: list[dict]) -> dict:
    keys = values[0].keys()
    return {k: {"mean": float(np.mean([v[k] for v in values])),
                "min": float(np.min([v[k] for v in values])),
                "max": float(np.max([v[k] for v in values]))} for k in keys}


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o


def run_all(out_dir: str | Path = "outputs", seeds: int = 3, config_path=None,
            pf_every: int = 2, verbose: bool = True) -> dict:
    t0 = time.time()
    out = Path(out_dir)
    charts, tables = out / "charts", out / "tables"
    charts.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)
    log = print if verbose else (lambda *a, **k: None)

    per_seed, primary = [], None
    for i in range(seeds):
        log(f"\n=== seed {i + 1}/{seeds} ===")
        base_seed = 42 + 100 * i
        res = stress_and_representative(config_path, {"simulation": {"seed": base_seed}}, verbose=verbose)
        comp = {v: monthly_composite(res["stress"].feeder[v].metrics, res["representative"].feeder[v].metrics)
                for v in VARIANTS}
        per_seed.append(comp)
        if primary is None:
            primary = res
    pilot = {v: _agg([s[v] for s in per_seed]) for v in VARIANTS}

    stress, rep = primary["stress"], primary["representative"]
    sc = stress.sc
    log("\n=== detailed studies on seed 1 ===")
    log("AC power flow (pandapower) over the stress week ...")
    c = stress.city["baseline"]
    pf_base = run_power_flow(sc, c["inputs"], c["rt"], stress.feeder["baseline"], every=pf_every)
    pf_gs = run_power_flow(sc, c["inputs"], c["rt"], stress.feeder["gridsetu"], every=pf_every)
    log("WAMS frequency event study ...")
    wams = wams_study(sc, c["inputs"], c["rt"])
    log("Comms-degraded sensitivity (control slice 60 % loss, no retries) ...")
    from .feeder import simulate_feeder
    bad = {k: dict(v) for k, v in sc.raw["comm_slices"].items()}
    bad["control_2g4g"].update(loss=0.6, retries=0)
    bad["urllc_protection"].update(loss=0.6, retries=0)
    degraded = simulate_feeder(sc, stress.feeder_loads, stress.forecast, stress.signals["baseline"],
                               "gridsetu", sc.rng(31337).random(sc.n_steps), bad)
    log("Isolated microgrid ...")
    island = {s: simulate_island(sc, stress.weather, s) for s in ("legacy", "gridsetu")}

    cf = class_factors(sc, c["inputs"].loads)
    pfact = plant_factors(sc, c["rt"])
    results = {
        "about": {
            "label": "SIMULATION: synthetic data, not field measurement",
            "seeds": seeds, "month_definition": f"{REP_WEEKS_PER_MONTH} representative weeks + 1 stress week",
            "headline_attribution": "baseline and gridsetu run on the same city signals; "
                                    "gridsetu_coordinated adds city-level solar-hour irrigation and industrial DR",
            "runtime_s": None,
        },
        "pilot_feeder_monthly": pilot,
        "pilot_feeder_weekly_seed1": {wk: {v: w.feeder[v].metrics for v in VARIANTS}
                                      for wk, w in (("stress", stress), ("representative", rep))},
        "fairness_stress_week": stress.feeder["gridsetu"].fairness,
        "comm_slices_stress_week": stress.feeder["gridsetu"].comms,
        "comms_degraded_stress_week": {"metrics": degraded.metrics, "slices": degraded.comms,
                                       "note": "control and protection slices at 60 % loss, no retries"},
        "reserve_sizing_stress_week": stress.feeder["gridsetu"].sizing,
        "forecast_skill": stress.forecast_skill,
        "feeder_factors": feeder_factors(sc, stress.feeder_loads),
        "city": {wk: {name: market_stats(w.sc, w.city[name]["da"], w.city[name]["rt"], w.city[name]["inputs"])
                      for name in ("baseline", "coordinated")}
                 for wk, w in (("stress", stress), ("representative", rep))},
        "system_factors_stress": system_factors(sc, c["inputs"].loads, c["rt"]),
        "wams": {"timestamp": wams["timestamp"], "fleet_ffr_mw": wams["fleet_ffr_mw"],
                 "runs": {k: v["summary"] for k, v in wams["runs"].items()}},
        "island_microgrid": {k: v[1] for k, v in island.items()},
        "power_flow_stress": {
            "max_line_loading_pct": float(pf_base["max_tie_loading_pct"].max()),
            "samples_over_100pct": int((pf_base["max_tie_loading_pct"] > 100).sum()),
            "mean_losses_mw": float(pf_base["losses_mw"].mean()),
            "feeder_min_v_pu_baseline": float(np.nanmin(pf_base["feeder_min_v_pu"])),
            "feeder_min_v_pu_gridsetu": float(np.nanmin(pf_gs["feeder_min_v_pu"])),
            "v_33kV_range_pu": [float(pf_base.filter(like="33kV").min().min()),
                                float(pf_base.filter(like="33kV").max().max())],
        },
    }

    # ---- tables
    cf.to_csv(tables / "load_class_factors.csv", index=False)
    pfact.to_csv(tables / "plant_factors.csv", index=False)
    for v in VARIANTS:
        stress.feeder[v].ts.to_csv(tables / f"feeder_timeseries_stress_{v}.csv")
    rt = c["rt"]
    pd.concat({"gen_mw": rt.gen, "flow_mw": rt.flow, "price_rt": rt.price,
               "mcp_da": c["da"].mcp(sc.raw["exchange_price"]["price_cap"])}, axis=1) \
        .to_csv(tables / "city_dispatch_stress_baseline.csv")
    pf_base.to_csv(tables / "power_flow_stress_baseline.csv")
    for k, v in wams["runs"].items():
        v["ts"].to_csv(tables / f"wams_{k}.csv", index=False)
    with open(out / "reliability_reserve_stress_week.json", "w") as fh:
        json.dump(_jsonable(stress.feeder["gridsetu"].reserves), fh, indent=2)

    # ---- charts
    log("Charts ...")
    plots.slide2_profile(rep, charts, day=1)
    plots.slide8_bars(pilot, charts)
    plots.city_dispatch(stress, charts, "baseline")
    plots.market_prices(stress, charts)
    plots.load_classes(stress, cf, charts)
    plots.feeder_week(stress, charts)
    plots.feeder_week(rep, charts)
    plots.forecast_bands(stress, charts)
    plots.fairness_hist(stress, charts)
    plots.wams_plot(wams, charts)
    plots.island_plot(results["island_microgrid"], charts)
    plots.security_plot(pf_base, charts)

    results["about"]["runtime_s"] = round(time.time() - t0, 1)
    with open(out / "results.json", "w") as fh:
        json.dump(_jsonable(results), fh, indent=2, default=str)
    summary = format_summary(results)
    (out / "summary.txt").write_text(summary, encoding="utf-8")
    log("\n" + summary)
    return results


def format_summary(r: dict) -> str:
    p = r["pilot_feeder_monthly"]
    rows = [
        ("Unserved energy, evening ramp 17:30-19:30", "kWh/month", "evening_window_unserved_kwh"),
        ("Unserved energy, all hours (net of rebound)", "kWh/month", "total_unserved_kwh"),
        ("Critical-load (Tier-1) outage", "h/month", "critical_outage_hours"),
        ("Whole-feeder outage", "h/month", "feeder_outage_hours"),
        ("Feeder peak import", "kW", "feeder_peak_import_kw"),
        ("Solar utilisation", "%", "solar_utilisation_pct"),
        ("Battery cycles", "per month", "battery_cycles"),
    ]
    lines = ["GridSetu Phase 1: pilot feeder, SIMULATION (synthetic data, not field measurement)",
             f"Monthly composite = {r['about']['month_definition']}; mean over {r['about']['seeds']} seeds",
             "", f"{'Metric':46s}{'Unit':>11s}{'Baseline':>11s}{'GridSetu':>11s}{'Change':>9s}{'+City coord':>13s}",
             "-" * 101]
    for name, unit, k in rows:
        b, g, gc = p["baseline"][k]["mean"], p["gridsetu"][k]["mean"], p["gridsetu_coordinated"][k]["mean"]
        chg = f"{(g - b) / b * 100:+.0f}%" if b else "n/a"
        lines.append(f"{name:46s}{unit:>11s}{b:11.1f}{g:11.1f}{chg:>9s}{gc:13.1f}")
    fs = r["fairness_stress_week"]
    w = r["wams"]["runs"]
    cs = r["city"]["stress"]
    lines += ["", "Fairness (stress week): "
              f"{fs['households_ever_curtailed']} households shared Tier-3 curtailment, max {fs['max_household_hours']:.2f} h each, "
              f"Gini {fs['gini_curtailment_hours']:.2f}, {fs['refusals']} user overrides honoured",
              f"Forecast (stress week): q10-q90 coverage {r['forecast_skill']['net_load']['coverage_q10_q90_pct']:.0f}% "
              f"(nominal 80%), MAPE {r['forecast_skill']['net_load']['mape_q50_pct']:.1f}%",
              f"City stress week: energy not served {cs['baseline']['energy_not_served_mwh']:.0f} MWh baseline -> "
              f"{cs['coordinated']['energy_not_served_mwh']:.0f} MWh with solar-hour irrigation + industrial DR",
              f"WAMS case A (G1B trip): SPS shed {w['A_baseline']['load_shed_mw']:.0f} MW baseline -> "
              f"{w['A_gridsetu']['load_shed_mw']:.0f} MW with GridSetu FFR; case B (islanding) nadir "
              f"{w['B_baseline']['nadir_hz']:.2f} -> {w['B_gridsetu']['nadir_hz']:.2f} Hz",
              f"Comms degraded (60 % loss, stress week): critical outage "
              f"{r['comms_degraded_stress_week']['metrics']['critical_outage_hours']:.1f} h, whole-feeder outage "
              f"{r['comms_degraded_stress_week']['metrics']['feeder_outage_hours']:.1f} h "
              f"(vs {r['pilot_feeder_weekly_seed1']['stress']['gridsetu']['feeder_outage_hours']:.1f} h nominal)",
              f"Isolated microgrid: unserved {r['island_microgrid']['legacy']['unserved_kwh']:.0f} -> "
              f"{r['island_microgrid']['gridsetu']['unserved_kwh']:.0f} kWh/week, diesel hours "
              f"{r['island_microgrid']['legacy']['diesel_run_hours']:.0f} -> {r['island_microgrid']['gridsetu']['diesel_run_hours']:.0f}",
              f"Power flow: max 220 kV line loading {r['power_flow_stress']['max_line_loading_pct']:.0f}% "
              f"({r['power_flow_stress']['samples_over_100pct']} samples over 100%)",
              f"Runtime {r['about']['runtime_s']} s"]
    return "\n".join(lines)
