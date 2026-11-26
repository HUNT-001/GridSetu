"""One source of truth for every headline figure.

``build_numbers`` reads the study outputs (``results.json`` and, when present,
``calibration/calibration.json``) and writes ``numbers.json``: each figure with its value,
unit, the exact text used in the README, deck and forms, and the path it came from, plus
the provenance of the run (git commit, Python and library versions).

``check_files`` fails if a document quotes a headline figure that no longer matches, so
the README, deck text and submission answers cannot drift from the simulator.

    python -m gridsetu numbers --check README.md docs/submission/phase2_answers.md
"""
from __future__ import annotations

import json
import platform
import subprocess
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

LIBS = ("numpy", "pandas", "scipy", "lightgbm", "highspy", "pyomo", "pandapower", "pypsa")
MINUS = "−"


def _get(d: dict, path: str):
    for k in path.split("."):
        d = d[k]
    return d


def _num(v: float, dp: int) -> str:
    return f"{v:,.{dp}f}"


def _pct_change(b: float, p: float) -> str:
    c = round((p - b) / b * 100) if b else 0
    return f"{MINUS}{abs(c)}%" if c < 0 else f"+{c}%"


# (key, json field, unit, decimals, README text template)
PILOT = "pilot_feeder_monthly"
SPEC = [
    ("evening_unserved_kwh", "evening_window_unserved_kwh", "kWh/month", 0, "{v} kWh"),
    ("all_hours_unserved_kwh", "total_unserved_kwh", "kWh/month", 0, "{v} kWh"),
    ("critical_outage_h", "critical_outage_hours", "h/month", 1, "{v} h"),
    ("feeder_outage_h", "feeder_outage_hours", "h/month", 1, "{v} h"),
    ("overload_trips", "overload_trips", "per month", 0, "{v}"),
    ("peak_import_kw", "feeder_peak_import_kw", "kW", 0, "{v} kW"),
]


def _git_commit(root: Path) -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True,
                              text=True, timeout=5).stdout.strip() or None
    except Exception:
        return None


def build_numbers(out_dir: str | Path = "outputs") -> dict:
    out = Path(out_dir)
    res = json.loads((out / "results.json").read_text(encoding="utf-8"))
    figs: dict[str, dict] = {}

    def add(key, value, unit, display, source, check=True):
        figs[key] = {"value": value, "unit": unit, "display": display, "source": source, "check": check}

    for key, mkey, unit, dp, tmpl in SPEC:
        b = _get(res, f"{PILOT}.baseline.{mkey}.mean")
        p = _get(res, f"{PILOT}.gridsetu.{mkey}.mean")
        add(f"pilot.baseline.{key}", round(b, dp), unit, tmpl.format(v=_num(b, dp)),
            f"results.json:{PILOT}.baseline.{mkey}.mean")
        add(f"pilot.gridsetu.{key}", round(p, dp), unit, tmpl.format(v=_num(p, dp)),
            f"results.json:{PILOT}.gridsetu.{mkey}.mean")
        if key == "overload_trips":   # bare integers are too common in prose to check
            figs[f"pilot.baseline.{key}"]["check"] = figs[f"pilot.gridsetu.{key}"]["check"] = False
        add(f"pilot.change.{key}", _pct_change(b, p), "%", _pct_change(b, p),
            f"derived from pilot.baseline/gridsetu.{key}", check=False)
    for side in ("baseline", "gridsetu"):
        lo = _get(res, f"{PILOT}.{side}.evening_window_unserved_kwh.min")
        hi = _get(res, f"{PILOT}.{side}.evening_window_unserved_kwh.max")
        add(f"pilot.{side}.evening_unserved_seed_range", [round(lo), round(hi)], "kWh/month",
            f"{_num(lo, 0)} to {_num(hi, 0)} kWh", f"results.json:{PILOT}.{side}.evening_window_unserved_kwh.min/max")

    for side in ("baseline", "gridsetu"):        # households fully without supply, and on lifeline
        for k in ("dark_home_hours", "lifeline_home_hours"):
            node = res[PILOT][side].get(k)
            if node is not None:
                add(f"pilot.{side}.{k}", round(node["mean"]), "home-hours/month", f"{node['mean']:,.0f} home-hours",
                    f"results.json:{PILOT}.{side}.{k}.mean", check=not (side == "baseline" and k == "lifeline_home_hours"))

    # "+ city DR" column of the README results table
    co = res[PILOT].get("gridsetu_coordinated")
    if co:
        src = f"results.json:{PILOT}.gridsetu_coordinated"
        for k, field, dp, tmpl in (("evening_unserved_kwh", "evening_window_unserved_kwh", 0, "{v} kWh"),
                                   ("all_hours_unserved_kwh", "total_unserved_kwh", 0, "{v} kWh"),
                                   ("feeder_outage_h", "feeder_outage_hours", 1, "{v} h"),
                                   ("dark_home_hours", "dark_home_hours", 0, "{v} home-hours"),
                                   ("lifeline_home_hours", "lifeline_home_hours", 0, "{v} home-hours"),
                                   ("battery_cycles", "battery_cycles", 1, "{v}")):
            if field in co:
                v = co[field]["mean"]
                add(f"pilot.coordinated.{k}", round(v, dp), "per month", tmpl.format(v=_num(v, dp)), f"{src}.{field}.mean")
    g = res[PILOT]["gridsetu"]
    add("pilot.gridsetu.battery_cycles", round(g["battery_cycles"]["mean"], 1), "per month",
        f"{g['battery_cycles']['mean']:.1f}", f"results.json:{PILOT}.gridsetu.battery_cycles.mean")

    # reliability in the DISCOM's terms (reliability.py); not yet quoted in the README, so not checked
    if "saidi_h" in g:
        for side in ("baseline", "gridsetu", "gridsetu_coordinated"):
            m = res[PILOT][side]
            tag = "coordinated" if side == "gridsetu_coordinated" else side
            src = f"results.json:{PILOT}.{side}"
            add(f"reliability.{tag}.saidi_h", round(m["saidi_h"]["mean"], 1), "h per household per month",
                f"{m['saidi_h']['mean']:.1f} h", f"{src}.saidi_h.mean", check=False)
            add(f"reliability.{tag}.saifi", round(m["saifi"]["mean"], 1), "interruptions per household per month",
                f"{m['saifi']['mean']:.1f}", f"{src}.saifi.mean", check=False)
            add(f"reliability.{tag}.caidi_h", round(m["caidi_h"]["mean"], 2), "h per interruption",
                f"{m['caidi_h']['mean']:.2f} h", f"{src}.caidi_h.mean", check=False)
            add(f"reliability.{tag}.evening_availability_pct", round(m["evening_supply_availability_pct"]["mean"], 1),
                "% of household-hours 17:00-23:00", f"{m['evening_supply_availability_pct']['mean']:.1f}%",
                f"{src}.evening_supply_availability_pct.mean", check=False)
        for side, tag in (("baseline", "baseline"), ("gridsetu", "gridsetu")):
            s = res[PILOT][side]["saidi_h"]["mean"]
            add(f"reliability.{tag}.saidi_h_per_year", round(12 * s), "h per household per year",
                f"{12 * s:,.0f} h a year", f"12 x results.json:{PILOT}.{side}.saidi_h.mean "
                "(if the simulated month repeats all year)", check=False)

    # city, protection, isolated microgrid, AC power flow, planning factors (results.json)
    cs = res["city"]["stress"]
    add("city.baseline.ens_mwh", round(cs["baseline"]["energy_not_served_mwh"]), "MWh/stress week",
        f"{cs['baseline']['energy_not_served_mwh']:,.0f} MWh", "results.json:city.stress.baseline.energy_not_served_mwh")
    add("city.coordinated.ens_mwh", round(cs["coordinated"]["energy_not_served_mwh"]), "MWh/stress week",
        f"{cs['coordinated']['energy_not_served_mwh']:,.0f} MWh", "results.json:city.stress.coordinated.energy_not_served_mwh")
    w = res["wams"]["runs"]
    add("wams.A_baseline.nadir_hz", round(w["A_baseline"]["nadir_hz"], 2), "Hz", f"{w['A_baseline']['nadir_hz']:.2f} Hz",
        "results.json:wams.runs.A_baseline.nadir_hz")
    add("wams.B_baseline.nadir_hz", round(w["B_baseline"]["nadir_hz"], 2), "Hz", f"{w['B_baseline']['nadir_hz']:.2f} Hz",
        "results.json:wams.runs.B_baseline.nadir_hz")
    add("wams.A.sps_shed_mw", [round(w["A_baseline"]["load_shed_mw"]), round(w["A_gridsetu"]["load_shed_mw"])], "MW",
        f"{w['A_baseline']['load_shed_mw']:.0f} to {w['A_gridsetu']['load_shed_mw']:.0f} MW",
        "results.json:wams.runs.A_baseline/A_gridsetu.load_shed_mw")
    isl = res["island_microgrid"]
    for k, unit, suffix in (("unserved_kwh", "kWh/week", ""), ("diesel_run_hours", "h/week", ""),
                            ("pv_curtailed_kwh", "kWh/week", " kWh")):
        if k in isl.get("legacy", {}):
            a, b = isl["legacy"][k], isl["gridsetu"][k]
            add(f"island.{k}_change", [round(a), round(b)], unit, f"{a:.0f} to {b:.0f}{suffix}",
                f"results.json:island_microgrid.legacy/gridsetu.{k}")
    pf = res["power_flow_stress"]
    add("power_flow.max_220kv_line_loading_pct", round(pf["max_line_loading_pct"]), "%",
        f"{pf['max_line_loading_pct']:.0f}%", "results.json:power_flow_stress.max_line_loading_pct")
    add("power_flow.samples_over_100pct", pf["samples_over_100pct"], "samples", f"in {pf['samples_over_100pct']} samples",
        "results.json:power_flow_stress.samples_over_100pct")
    lo, hi = pf["v_33kV_range_pu"]
    add("power_flow.v_33kv_range_pu", [round(lo, 2), round(hi, 2)], "pu", f"{lo:.2f} to {hi:.2f} pu",
        "results.json:power_flow_stress.v_33kV_range_pu (the 33 kV buses, not the 11 kV feeder)")
    for side in ("baseline", "gridsetu"):     # pilot 11 kV feeder line losses, stress week
        fl = pf.get("feeder_11kv_losses", {}).get(side)
        if fl:
            src = f"results.json:power_flow_stress.feeder_11kv_losses.{side}"
            add(f"losses.python_11kv.{side}.kwh", round(fl["loss_kwh"]), "kWh/stress week", f"{fl['loss_kwh']:,.0f} kWh",
                f"{src}.loss_kwh", check=False)
            add(f"losses.python_11kv.{side}.pct", round(fl["loss_pct"], 2), "% of energy into the feeder",
                f"{fl['loss_pct']:.2f}%", f"{src}.loss_pct", check=False)
    sf = res["system_factors_stress"]
    add("planning.city_peak_mw", round(sf["city_peak_mw"]), "MW", f"{sf['city_peak_mw']:.0f} MW",
        "results.json:system_factors_stress.city_peak_mw")
    add("planning.city_load_factor", round(sf["city_load_factor"], 2), "", f"load factor {sf['city_load_factor']:.2f}",
        "results.json:system_factors_stress.city_load_factor")
    add("planning.reserve_margin_at_peak_pct", round(sf["reserve_margin_at_peak_pct"], 1), "%",
        f"{sf['reserve_margin_at_peak_pct']:.1f}%", "results.json:system_factors_stress.reserve_margin_at_peak_pct")

    fair = res["fairness_stress_week"]
    add("fairness.gini", round(fair["gini_curtailment_hours"], 2), "", f"{fair['gini_curtailment_hours']:.2f}",
        "results.json:fairness_stress_week.gini_curtailment_hours")
    add("fairness.max_hours_per_home", round(fair["max_household_hours"], 1), "h/stress week",
        f"{fair['max_household_hours']:.1f} hours", "results.json:fairness_stress_week.max_household_hours")
    add("fairness.overrides_honoured", fair["refusals"], "count", f"{fair['refusals']:,}",
        "results.json:fairness_stress_week.refusals")
    add("fairness.homes_sharing", fair["households_ever_curtailed"], "count", f"{fair['households_ever_curtailed']}",
        "results.json:fairness_stress_week.households_ever_curtailed")
    if "households_with_shiftable_load" in fair:
        add("fairness.homes_with_shiftable_load", fair["households_with_shiftable_load"], "count",
            f"{fair['households_with_shiftable_load']}", "results.json:fairness_stress_week.households_with_shiftable_load")
    add("fairness.back_to_back_relaxations", fair["consecutive_interval_violations"], "intervals/stress week",
        f"{fair['consecutive_interval_violations']}", "results.json:fairness_stress_week.consecutive_interval_violations",
        check=False)

    fc = res["forecast_skill"]["net_load"]
    add("forecast.coverage_q10_q90_pct", round(fc["coverage_q10_q90_pct"]), "%", f"{fc['coverage_q10_q90_pct']:.0f}%",
        "results.json:forecast_skill.net_load.coverage_q10_q90_pct")
    add("forecast.median_error_pct", round(fc["mape_q50_pct"], 1), "%", f"{fc['mape_q50_pct']:.1f}%",
        "results.json:forecast_skill.net_load.mape_q50_pct")

    deg = res["comms_degraded_stress_week"]["metrics"]
    add("comms_60pct_loss.critical_outage_h", round(deg["critical_outage_hours"], 1), "h/stress week",
        f"{deg['critical_outage_hours']:.1f} h", "results.json:comms_degraded_stress_week.metrics.critical_outage_hours",
        check=False)

    isl = res["island_microgrid"]
    for k in ("unserved_kwh", "diesel_run_hours"):
        if k in isl.get("legacy", {}):
            add(f"island.legacy.{k}", round(isl["legacy"][k]), "per week", f"{isl['legacy'][k]:,.0f}",
                f"results.json:island_microgrid.legacy.{k}", check=False)
            add(f"island.gridsetu.{k}", round(isl["gridsetu"][k]), "per week", f"{isl['gridsetu'][k]:,.0f}",
                f"results.json:island_microgrid.gridsetu.{k}", check=False)

    cal_path = out / "calibration" / "calibration.json"
    if cal_path.exists():
        cal = json.loads(cal_path.read_text(encoding="utf-8"))
        allst = cal["all_stages"]
        add("reserve_calibration.n_forecasts", allst["held"]["n_forecasts"], "count",
            f"{allst['held']['n_forecasts']:,}", "calibration.json:all_stages.held.n_forecasts")
        add("reserve_calibration.stated_pct", allst["held"]["stated_mean_pct"], "%",
            f"{allst['held']['stated_mean_pct']:.0f}%", "calibration.json:all_stages.held.stated_mean_pct",
            check=False)
        add("reserve_calibration.own_peak_held_pct", allst["own_peak_held"]["observed_pct"], "%",
            f"{allst['own_peak_held']['observed_pct']:.0f}%", "calibration.json:all_stages.own_peak_held.observed_pct",
            check=False)
        for wk, d in cal["by_week"].items():
            add(f"reserve_calibration.{wk}.call_met_pct", d["held"]["observed_pct"], "%",
                f"{d['held']['observed_pct']:.0f}%", f"calibration.json:by_week.{wk}.held.observed_pct", check=False)
        rq = cal["discom_request_evenings"]
        if rq.get("n_evenings"):
            add("reserve_calibration.call_evenings", rq["n_evenings"], "count", f"{rq['n_evenings']} evenings",
                "calibration.json:discom_request_evenings.n_evenings")
            add("reserve_calibration.call_evenings_met_pct", rq["held_pct"], "%", f"{rq['held_pct']:.0f}%",
                "calibration.json:discom_request_evenings.held_pct", check=False)
            add("reserve_calibration.request_over_reserve_range", [rq["request_over_reserve_min"],
                rq["request_over_reserve_max"]], "x", f"{rq['request_over_reserve_min']:.1f} to "
                f"{rq['request_over_reserve_max']:.1f} times", "calibration.json:discom_request_evenings.request_over_reserve_min/max")
            add("reserve_calibration.request_over_reserve_median", rq["request_over_reserve_median"], "x",
                f"{rq['request_over_reserve_median']:.1f} times",
                "calibration.json:discom_request_evenings.request_over_reserve_median")

    # second confidence: DISCOM calls, as the headline runs them and with calls bounded by the offer
    for sub, tag in (("calibration", "calls"), ("calibration_bounded", "bounded_calls")):
        pth = out / sub / "calibration.json"
        if not pth.exists():
            continue
        c = json.loads(pth.read_text(encoding="utf-8"))
        rq = c.get("discom_request_evenings", {})
        if "all_calls_met_pct" in rq:
            add(f"{tag}.n_evenings", rq["n_evenings"], "count", f"{rq['n_evenings']} call evenings",
                f"{sub}/calibration.json:discom_request_evenings.n_evenings", check=False)
            add(f"{tag}.met_pct", rq["all_calls_met_pct"], "%", f"{rq['all_calls_met_pct']:.0f}%",
                f"{sub}/calibration.json:discom_request_evenings.all_calls_met_pct", check=False)
            met_n = round(rq["all_calls_met_pct"] * rq["n_evenings"] / 100)
            add(f"{tag}.met_evenings", met_n, "count", f"{met_n} of {rq['n_evenings']}",
                f"{sub}/calibration.json:discom_request_evenings.all_calls_met_pct x n_evenings")
            if rq.get("request_over_call_capacity_median") is not None:
                add(f"{tag}.request_over_call_capacity_median", rq["request_over_call_capacity_median"], "x",
                    f"{rq['request_over_call_capacity_median']:.2f} times",
                    f"{sub}/calibration.json:discom_request_evenings.request_over_call_capacity_median",
                    check=tag == "calls")
        cc = c.get("call_confidence", {}).get("within_offer")
        if cc and cc["n_forecasts"]:
            add(f"{tag}.call_confidence_stated_pct", cc["stated_mean_pct"], "%", f"{cc['stated_mean_pct']:.0f}%",
                f"{sub}/calibration.json:call_confidence.within_offer.stated_mean_pct", check=False)
            add(f"{tag}.call_confidence_observed_pct", cc["observed_pct"], "%", f"{cc['observed_pct']:.1f}%",
                f"{sub}/calibration.json:call_confidence.within_offer.observed_pct",
                check=tag == "bounded_calls")      # too few in-offer calls to quote in the unbounded case
            add(f"{tag}.call_confidence_n", cc["n_forecasts"], "count", f"{cc['n_forecasts']:,} forecasts",
                f"{sub}/calibration.json:call_confidence.within_offer.n_forecasts", check=False)

    # business case (python -m gridsetu economics)
    ec_path = out / "economics" / "economics.json"
    if ec_path.exists():
        e = json.loads(ec_path.read_text(encoding="utf-8"))["annual"]
        src = "economics/economics.json:annual"
        add("economics.breakeven_inr_per_kwh", e["breakeven_value_inr_per_kwh"], "INR/kWh",
            f"₹{e['breakeven_value_inr_per_kwh']:.1f} per kWh", f"{src}.breakeven_value_inr_per_kwh")
        add("economics.total_cost_lakh", round(e["total_cost_inr_per_year"] / 1e5, 1), "INR lakh/year",
            f"₹{e['total_cost_inr_per_year'] / 1e5:.1f} lakh a year", f"{src}.total_cost_inr_per_year")
        add("economics.cost_per_home_month", round(e["cost_per_home_per_month_inr"]), "INR/home/month",
            f"₹{e['cost_per_home_per_month_inr']:.0f} per home per month", f"{src}.cost_per_home_per_month_inr")
        add("economics.unserved_avoided_kwh", e["unserved_avoided_kwh_per_year"], "kWh/year",
            f"{e['unserved_avoided_kwh_per_year']:,} kWh", f"{src}.unserved_avoided_kwh_per_year")
        for k in ("iex_ceiling", "diesel_backup"):
            r = e["at_reference_values"][k]
            add(f"economics.bcr_{k}", r["benefit_cost_ratio"], "ratio", f"{r['benefit_cost_ratio']:.2f}",
                f"{src}.at_reference_values.{k}.benefit_cost_ratio", check=False)
        for k, v in e["costs_inr_per_year"].items():           # README cost table
            add(f"economics.cost_{k}_lakh", round(v / 1e5, 2), "INR lakh/year", f"{v / 1e5:.2f} lakh",
                f"{src}.costs_inr_per_year.{k}")
        add("economics.extra_energy_cost_lakh", round(e["extra_energy_cost_inr_per_year"] / 1e5, 2), "INR lakh/year",
            f"{e['extra_energy_cost_inr_per_year'] / 1e5:.2f} lakh", f"{src}.extra_energy_cost_inr_per_year")
        if e.get("cost_per_avoided_home_outage_hour_inr") is not None:
            add("economics.cost_per_avoided_home_outage_hour", e["cost_per_avoided_home_outage_hour_inr"], "INR/home-hour",
                f"₹{e['cost_per_avoided_home_outage_hour_inr']:.1f} per household-hour of outage avoided",
                f"{src}.cost_per_avoided_home_outage_hour_inr", check=False)
            add("economics.home_outage_hours_avoided", e["home_outage_hours_avoided_per_year"], "home-hours/year",
                f"{e['home_outage_hours_avoided_per_year']:,} home-hours", f"{src}.home_outage_hours_avoided_per_year",
                check=False)
        if e.get("battery_cost_per_kwh_delivered_inr") is not None:
            add("economics.battery_cost_per_kwh_delivered", e["battery_cost_per_kwh_delivered_inr"], "INR/kWh",
                f"₹{e['battery_cost_per_kwh_delivered_inr']:.1f} per kWh delivered",
                f"{src}.battery_cost_per_kwh_delivered_inr", check=False)

    # 20-feeder fleet and unit commitment (python -m gridsetu phase2)
    p2_path = out / "phase2" / "phase2.json"
    if p2_path.exists():
        p2 = json.loads(p2_path.read_text(encoding="utf-8"))
        fs = p2["fleet"]["stress"]
        src = "phase2/phase2.json:fleet.stress"
        add("fleet.feeders_overloaded", fs["feeders_overloaded_at_peak"], "count",
            f"{fs['feeders_overloaded_at_peak']} of {fs['n_feeders']}", f"{src}.feeders_overloaded_at_peak")
        for c in fs["curve"]:
            n, i = c["feeders"], f"{src}.curve[adoption={c['adoption']}]"
            add(f"fleet.stress.{n}.critical_site_hours", round(c["critical_site_hours"]), "h/stress week",
                f"{c['critical_site_hours']:,.0f}", f"{i}.critical_site_hours", check=False)   # bare numbers
            add(f"fleet.stress.{n}.home_hours_dark", round(c["household_dark_hours"]), "home-hours/stress week",
                f"{c['household_dark_hours']:,.0f}", f"{i}.household_dark_hours", check=c["household_dark_hours"] >= 1000)
            add(f"fleet.stress.{n}.unserved_kwh", round(c["total_unserved_kwh"]), "kWh/stress week",
                f"{c['total_unserved_kwh']:,.0f} kWh", f"{i}.total_unserved_kwh")
            if c["batteries_kwh"]:
                add(f"fleet.stress.{n}.batteries_kwh", round(c["batteries_kwh"]), "kWh",
                    f"{c['batteries_kwh']:,.0f} kWh", f"{i}.batteries_kwh")
        c0, c1 = fs["curve"][0], fs["curve"][-1]
        ch = _pct_change(c0["household_dark_hours"], c1["household_dark_hours"])
        add("fleet.stress.home_hours_dark_change", ch, "%", ch, f"derived from {src}.curve[0/-1].household_dark_hours")
        r0 = p2["fleet"]["representative"]["curve"][0]
        add("fleet.representative.0.home_hours_dark", round(r0["household_dark_hours"]), "home-hours/week",
            f"{r0['household_dark_hours']:,.0f} home-hours", "phase2/phase2.json:fleet.representative.curve[0].household_dark_hours")
        u = p2["uc"]["stress"]
        src = "phase2/phase2.json:uc.stress"
        gas = next(iter(u["hours_on_lp"]))
        add("uc.gas_starts", u["startups"][gas], "starts/stress week", f"{u['startups'][gas]} times", f"{src}.startups.{gas}")
        add("uc.gas_hours_uc", round(u["hours_on_uc"][gas]), "h", f"{u['hours_on_uc'][gas]:.0f} hours", f"{src}.hours_on_uc.{gas}")
        add("uc.gas_hours_lp", round(u["hours_on_lp"][gas]), "h", f"{u['hours_on_lp'][gas]:.0f} in", f"{src}.hours_on_lp.{gas}")
        add("uc.shed_uc_mwh", round(u["shed_uc_mwh"]), "MWh", f"{u['shed_uc_mwh']:.0f}", f"{src}.shed_uc_mwh", check=False)
        add("uc.shed_lp_mwh", round(u["shed_lp_mwh"]), "MWh", f"{u['shed_lp_mwh']:.0f} MWh", f"{src}.shed_lp_mwh")
        d = u["cost_uc_inr"]["total"] - u["cost_lp_inr"]["total"]
        add("uc.extra_cost_lakh", round(d / 1e5), "INR lakh", f"₹{d / 1e5:.0f} lakh", f"{src}.cost_uc_inr.total - cost_lp_inr.total")
        pct = 100 * d / u["cost_lp_inr"]["total"]
        add("uc.extra_cost_pct", round(pct, 1), "%", f"{pct:.1f}%", f"{src}.cost_uc_inr.total / cost_lp_inr.total - 1")

    # who owns, runs and pays (python -m gridsetu ownership)
    ow_path = out / "economics" / "ownership.json"
    if ow_path.exists():
        o = json.loads(ow_path.read_text(encoding="utf-8"))
        src = "economics/ownership.json"
        lk = lambda x: f"₹{x / 1e5:.2f} lakh"
        add("ownership.discom_fee_lakh", round(o["who_pays"]["discom_availability_fee"] / 1e5, 2), "INR lakh/year",
            lk(o["who_pays"]["discom_availability_fee"]), f"{src}:who_pays.discom_availability_fee")
        add("ownership.plug_grant_lakh", round(o["who_pays"]["plug_grant_one_off_inr"] / 1e5, 1), "INR lakh",
            f"₹{o['who_pays']['plug_grant_one_off_inr'] / 1e5:.1f} lakh", f"{src}:who_pays.plug_grant_one_off_inr")
        add("ownership.deferral_lakh", round(o["discom_gets_back"]["transformer_upgrade_deferred"] / 1e5, 2),
            "INR lakh/year", lk(o["discom_gets_back"]["transformer_upgrade_deferred"]),
            f"{src}:discom_gets_back.transformer_upgrade_deferred")
        add("ownership.losses_lakh", round(o["discom_gets_back"]["technical_losses_avoided_inr"] / 1e5, 2),
            "INR lakh/year", lk(o["discom_gets_back"]["technical_losses_avoided_inr"]),
            f"{src}:discom_gets_back.technical_losses_avoided_inr")
        add("ownership.discom_net_lakh", round(o["discom_net_cost"] / 1e5, 2), "INR lakh/year",
            lk(o["discom_net_cost"]), f"{src}:discom_net_cost")
        add("ownership.discom_net_per_kwh", o["discom_net_cost_per_avoided_outage_kwh"], "INR/kWh",
            f"₹{o['discom_net_cost_per_avoided_outage_kwh']:.2f} per kWh", f"{src}:discom_net_cost_per_avoided_outage_kwh")
        add("ownership.per_home_month", o["per_home_per_month_inr"], "INR/home/month",
            f"₹{o['per_home_per_month_inr']:.1f} per home per month", f"{src}:per_home_per_month_inr")
        add("ownership.tn_free_power_per_home_month", o["tn_free_power_increase_per_home_per_month_inr"],
            "INR/home/month", f"₹{o['tn_free_power_increase_per_home_per_month_inr']:.0f}",
            f"{src}:tn_free_power_increase_per_home_per_month_inr", check=False)

    # households against real Indian smart-meter data (python -m gridsetu household-check)
    hh_path = out / "households" / "households.json"
    if hh_path.exists():
        h = json.loads(hh_path.read_text(encoding="utf-8"))
        src = "households/households.json"
        add("households.synthetic_daily_kwh", h["synthetic"]["daily_kwh_mean"], "kWh/day",
            f"{h['synthetic']['daily_kwh_mean']:.1f} kWh a day", f"{src}:synthetic.daily_kwh_mean")
        add("households.measured_daily_kwh", h["measured_aug_oct"]["daily_kwh_mean"], "kWh/day",
            f"{h['measured_aug_oct']['daily_kwh_mean']:.1f} kWh a day", f"{src}:measured_aug_oct.daily_kwh_mean")
        add("households.tn_daily_kwh", h["about"]["tn_domestic_kwh_per_day"], "kWh/day",
            f"{h['about']['tn_domestic_kwh_per_day']:.1f} kWh a day", f"{src}:about.tn_domestic_kwh_per_day")
        for side, node in (("synthetic", h["synthetic"]), ("measured", h["measured_aug_oct"])):
            add(f"households.{side}_evening_above_200w_pct", round(100 * node["evening_above_200w_share"]), "%",
                f"{100 * node['evening_above_200w_share']:.0f}%", f"{src}:{side}.evening_above_200w_share", check=False)
            add(f"households.{side}_coincidence", node["coincidence"], "", f"{node['coincidence']:.2f}",
                f"{src}:{side}.coincidence", check=False)
        if "legacy_synthetic" in h:
            add("households.legacy_daily_kwh", h["legacy_synthetic"]["daily_kwh_mean"], "kWh/day",
                f"{h['legacy_synthetic']['daily_kwh_mean']:.1f} kWh a day", f"{src}:legacy_synthetic.daily_kwh_mean")
        for case, r in h.get("fitted_vs_legacy", {}).items():
            for v in ("baseline", "gridsetu"):
                for k in ("evening_window_unserved_kwh", "dark_home_hours", "feeder_outage_hours"):
                    add(f"households.{case}.{v}.{k}", r[v][k], "per month", f"{r[v][k]:,.1f}" if "hours" in k and "home" not in k
                        else f"{r[v][k]:,.0f}", f"{src}:fitted_vs_legacy.{case}.{v}.{k}", check=False)

    # low-voltage network study (MATLAB reference results, matlab/run_f07.m)
    lv_path = out.resolve().parent / "matlab" / "results" / "summary.json"
    if lv_path.exists():
        lv = json.loads(lv_path.read_text(encoding="utf-8"))
        for case, r in lv.items():
            week, scen = case.split("_", 1)
            src = f"matlab/results/summary.json:{case}"
            add(f"lv.{week}.{scen}.technical_loss_kwh", r["technical_loss_kwh"], "kWh/week",
                f"{r['technical_loss_kwh']:,.0f} kWh", f"{src}.technical_loss_kwh", check=week == "stress")
            add(f"lv.{week}.{scen}.technical_loss_pct", r["technical_loss_pct"], "%",
                f"{r['technical_loss_pct']:.1f}%", f"{src}.technical_loss_pct", check=False)
            add(f"lv.{week}.{scen}.voltage_violation_bus_hours", r["voltage_violation_bus_hours"], "bus-hours/week",
                f"{r['voltage_violation_bus_hours']:,.0f} bus-hours", f"{src}.voltage_violation_bus_hours",
                check=week == "stress")
            add(f"lv.{week}.{scen}.min_voltage_pu", r["min_voltage_pu"], "pu",
                f"{r['min_voltage_pu']:.2f} pu", f"{src}.min_voltage_pu", check=False)
            add(f"lv.{week}.{scen}.peak_transformer_loading_pu", r["peak_transformer_loading_pu"], "pu",
                f"{r['peak_transformer_loading_pu']:.2f} pu", f"{src}.peak_transformer_loading_pu",
                check=week == "stress")
            add(f"lv.{week}.{scen}.max_hotspot_c", r["max_hotspot_c"], "deg C",
                f"{r['max_hotspot_c']:.1f} °C", f"{src}.max_hotspot_c", check=week == "stress")
            add(f"lv.{week}.{scen}.ageing_equivalent_hours", r["ageing_equivalent_hours"], "h/week",
                f"{r['ageing_equivalent_hours']:.2f} h", f"{src}.ageing_equivalent_hours", check=False)

    # real-data validation (python -m gridsetu real-data)
    rd_path = out / "real_data" / "real_data.json"
    if rd_path.exists():
        rd = json.loads(rd_path.read_text(encoding="utf-8"))
        src = "real_data/real_data.json"
        iex = rd["prices"]["iex_2025_09_14_20"]
        add("real.iex.days_reaching_cap", iex["days_reaching_cap"], "days", f"{iex['days_reaching_cap']} of "
            f"{iex['n_days']} days", f"{src}:prices.iex_2025_09_14_20.days_reaching_cap")
        add("real.iex.peak_blocks_at_cap_pct", iex["peak_blocks_at_cap_pct"], "%",
            f"{iex['peak_blocks_at_cap_pct']:.0f}%", f"{src}:prices.iex_2025_09_14_20.peak_blocks_at_cap_pct",
            check=False)
        add("real.iex.solar_hours_mean", iex["solar_10_16_mean_inr_kwh"], "INR/kWh",
            f"₹{iex['solar_10_16_mean_inr_kwh']:.2f}/kWh", f"{src}:prices.iex_2025_09_14_20.solar_10_16_mean_inr_kwh")
        for k in ("synthetic", "nasa_power"):
            v = rd["weather"][k]["insolation_kwh_m2_day_mean"]
            add(f"real.weather.{k}.insolation", v, "kWh/m2/day", f"{v:.2f} kWh/m²/day",
                f"{src}:weather.{k}.insolation_kwh_m2_day_mean")
            c = rd["forecast_backtest"]["mean"][k]["net_load"]["coverage_q10_q90_pct"]
            add(f"real.backtest.{k}.net_load_coverage_pct", c, "%", f"{c:.1f}%",
                f"{src}:forecast_backtest.mean.{k}.net_load.coverage_q10_q90_pct")
        for case in ("synthetic", "real_weather", "real_weather_and_prices"):
            for var in ("baseline", "gridsetu"):
                v = rd["stress_week"][case]["feeders"][var]["evening_window_unserved_kwh"]
                add(f"real.stress_week.{case}.{var}.evening_unserved_kwh", round(v), "kWh/week", f"{v:,.0f} kWh",
                    f"{src}:stress_week.{case}.feeders.{var}.evening_window_unserved_kwh")

    versions = {}
    for lib in LIBS:
        try:
            versions[lib] = metadata.version(lib)
        except metadata.PackageNotFoundError:
            versions[lib] = None
    doc = {
        "about": {
            "label": res["about"]["label"],
            "seeds": res["about"]["seeds"],
            "month_definition": res["about"]["month_definition"],
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "git_commit": _git_commit(out.resolve().parent),
            "python": platform.python_version(),
            "libraries": versions,
            "how_to_check": "python -m gridsetu numbers --check README.md",
        },
        "figures": figs,
    }
    (out / "numbers.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return doc


def check_files(out_dir: str | Path, files: list[str]) -> list[str]:
    """Every figure marked check=True must appear, as written in `display`, in each file."""
    doc = json.loads((Path(out_dir) / "numbers.json").read_text(encoding="utf-8"))
    problems = []
    for f in files:
        p = Path(f)
        if not p.exists():
            problems.append(f"{f}: file not found")
            continue
        text = p.read_text(encoding="utf-8")
        for key, fig in doc["figures"].items():
            if fig["check"] and fig["display"] not in text:
                problems.append(f"{f}: '{fig['display']}' ({key}) not found")
    return problems
