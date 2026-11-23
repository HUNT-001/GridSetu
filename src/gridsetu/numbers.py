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

    fair = res["fairness_stress_week"]
    add("fairness.gini", round(fair["gini_curtailment_hours"], 2), "", f"{fair['gini_curtailment_hours']:.2f}",
        "results.json:fairness_stress_week.gini_curtailment_hours")
    add("fairness.max_hours_per_home", round(fair["max_household_hours"], 1), "h/stress week",
        f"{fair['max_household_hours']:.1f} hours", "results.json:fairness_stress_week.max_household_hours")
    add("fairness.overrides_honoured", fair["refusals"], "count", f"{fair['refusals']:,}",
        "results.json:fairness_stress_week.refusals")
    add("fairness.homes_sharing", fair["households_ever_curtailed"], "count", f"{fair['households_ever_curtailed']}",
        "results.json:fairness_stress_week.households_ever_curtailed")
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
