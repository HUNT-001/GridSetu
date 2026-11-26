"""Command line: python -m gridsetu run [--seeds 3] [--out outputs] [--config config/city.yaml]"""
from __future__ import annotations

import json

import argparse
import logging
import warnings


def main(argv=None):
    from .envfile import load_env
    load_env()
    ap = argparse.ArgumentParser(prog="gridsetu", description="GridSetu Phase 1 smart-grid simulator")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the full Phase 1 study and write outputs")
    r.add_argument("--seeds", type=int, default=3, help="weather/load seeds to average over")
    r.add_argument("--out", default="outputs", help="output folder")
    r.add_argument("--config", default=None, help="scenario YAML (default config/city.yaml)")
    r.add_argument("--pf-every", type=int, default=2, help="run AC power flow every N steps")
    r.add_argument("--quiet", action="store_true")
    ca = sub.add_parser("calibrate", help="check the Reliability Reserve's stated confidence against outcomes")
    ca.add_argument("--seeds", type=int, default=30)
    ca.add_argument("--out", default="outputs")
    ca.add_argument("--config", default=None)
    ca.add_argument("--workers", type=int, default=2)
    ca.add_argument("--bounded-calls", action="store_true",
                    help="scenario: the DISCOM dispatches the feeder only up to its day-ahead offer "
                         "(writes outputs/calibration_bounded/)")
    nu = sub.add_parser("numbers", help="rebuild outputs/numbers.json and check documents against it")
    nu.add_argument("--out", default="outputs")
    nu.add_argument("--check", nargs="*", default=["README.md"], help="files whose figures must match")
    mx = sub.add_parser("export-matlab", help="write per-bus load profiles of feeder F07 for the MATLAB model")
    mx.add_argument("--out", default="outputs/matlab")
    mx.add_argument("--config", default=None)
    mx.add_argument("--seed", type=int, default=42)
    lv = sub.add_parser("lv-study", help="low-voltage network study (Python twin of matlab/run_f07.m) + charts")
    lv.add_argument("--in", dest="in_dir", default="outputs/matlab")
    lv.add_argument("--out", default="outputs/lv")
    hc = sub.add_parser("household-check", help="synthetic homes against real Indian smart-meter data")
    hc.add_argument("--out", default="outputs/households")
    hc.add_argument("--sensitivity", action="store_true", help="also re-run with 720 and 1,030 homes (~10 min)")
    ec = sub.add_parser("economics", help="rupee business case priced with real IEX prices")
    ec.add_argument("--out", default="outputs/economics")
    p2 = sub.add_parser("phase2", help="20-feeder fleet and unit-commitment studies into outputs/ (~minutes)")
    p2.add_argument("--out", default="outputs/phase2")
    ow = sub.add_parser("ownership", help="who owns, runs and pays: the funding model for one feeder")
    ow.add_argument("--out", default="outputs/economics")
    rd = sub.add_parser("real-data", help="validate the scenario against real weather (NASA POWER) and prices (IEX)")
    rd.add_argument("--out", default="outputs/real_data")
    sv = sub.add_parser("serve", help="start the API (and the built dashboard, if web/dist exists)")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--seeds", type=int, default=3, help="seeds for the reference run")
    rp = sub.add_parser("replay", help="publish a finished run as live telemetry to an MQTT broker")
    rp.add_argument("--broker", default="127.0.0.1:1883", help="MQTT broker host:port")
    rp.add_argument("--run", default=None, help="run id (default: the cached reference run)")
    rp.add_argument("--week", default="stress", choices=["stress", "representative"])
    rp.add_argument("--speed", type=float, default=4.0, help="15-minute steps per second")
    rp.add_argument("--start", default="0", help="step number or a time like 'Thu 17:00'")
    rp.add_argument("--steps", type=int, default=0, help="stop after this many steps (0 = loop forever)")
    fo = sub.add_parser("fetch-osm", help="download real streets from OpenStreetMap for the city map")
    fo.add_argument("--bbox", default=None,
                    help="south,west,north,east in degrees (default: Coimbatore's south-eastern periphery)")
    fo.add_argument("--endpoint", default="https://overpass-api.de/api/interpreter", help="Overpass API URL")
    args = ap.parse_args(argv)
    warnings.filterwarnings("ignore")
    logging.getLogger("pandapower").setLevel(logging.ERROR)
    logging.getLogger("pyomo").setLevel(logging.ERROR)
    if args.cmd == "serve":
        import os
        import uvicorn
        os.environ.setdefault("GRIDSETU_SEEDS", str(args.seeds))
        print(f"GridSetu control room on http://{args.host}:{args.port}")
        uvicorn.run("gridsetu.api.app:app", host=args.host, port=args.port, log_level="warning")
        return
    if args.cmd == "fetch-osm":
        from .citymap import DEFAULT_BBOX, OSM_FILE, fetch_osm
        bbox = tuple(float(x) for x in args.bbox.split(",")) if args.bbox else DEFAULT_BBOX
        if len(bbox) != 4:
            raise SystemExit("--bbox needs four numbers: south,west,north,east")
        print(f"Fetching streets in {bbox} from {args.endpoint} ...")
        try:
            res = fetch_osm(bbox, OSM_FILE, args.endpoint)
        except Exception as e:  # network, proxy or Overpass errors
            raise SystemExit(f"Could not download streets ({type(e).__name__}: {e}). Check the internet "
                             "connection, or try another Overpass server with --endpoint.") from None
        if not res["features"]:
            raise SystemExit("Overpass returned no streets for that box. Check the --bbox order: south,west,north,east.")
        print(f"Saved {res['features']} streets to {res['path']}.")
        print("Restart `gridsetu serve`: the reference run is recomputed once with the real streets.")
        return
    if args.cmd == "replay":
        from .copilot.replay_cli import replay
        replay(args.broker, args.run, args.week, args.speed, args.start, args.steps)
        return
    if args.cmd == "calibrate":
        from pathlib import Path
        from .calibration import run_calibration
        from .numbers import build_numbers
        if args.bounded_calls:
            r = run_calibration(args.seeds, args.out, args.config, args.workers,
                                overrides={"pilot_feeder": {"discom_calls_bounded_by_offer": True}},
                                sub="calibration_bounded")
        else:
            r = run_calibration(args.seeds, args.out, args.config, args.workers)
        a = r["all_stages"]["held"]
        print(f"{a['n_forecasts']} forecasts: stated {a['stated_mean_pct']}%, call met {a['observed_pct']}%, "
              f"own peak held {r['all_stages']['own_peak_held']['observed_pct']}%")
        if (Path(args.out) / "results.json").exists():
            build_numbers(args.out)      # fold the calibration figures into numbers.json
        return
    if args.cmd == "export-matlab":
        from .matlab_export import export
        print("wrote", export(args.out, args.config, args.seed))
        return
    if args.cmd == "household-check":
        from .householdcheck import run_study as run_hh
        r = run_hh(args.out, args.sensitivity)
        print(json.dumps({k: v for k, v in r.items() if k != "about"}, indent=1))
        return
    if args.cmd == "economics":
        from .economics import run_study as run_econ
        r = run_econ(args.out)
        print(json.dumps(r["annual"], indent=2))
        for srow in r["sensitivity"]:
            print(f"  {srow['assumption']}: break-even {srow['breakeven_low']} .. {srow['breakeven_high']} INR/kWh")
        return
    if args.cmd == "phase2":
        from .phase2 import run_studies
        r = run_studies(args.out)
        print(json.dumps({"fleet_curve_stress": r["fleet"]["stress"]["curve"], "uc": r["uc"]["stress"]},
                         indent=1, default=float))
        return
    if args.cmd == "ownership":
        from .ownership import run_study as run_own
        r = run_own(args.out)
        print(json.dumps({k: v for k, v in r.items() if k != "about"}, indent=1))
        return
    if args.cmd == "real-data":
        from .realstudy import run_study
        r = run_study(args.out)
        p, w = r["prices"], r["weather"]
        print("IEX 14-20 Sep 2025:", p["iex_2025_09_14_20"])
        print("scenario curve:    ", p["scenario_curve"])
        for k in ("synthetic", "nasa_power"):
            print(k, {m: v for m, v in w[k].items() if m not in ("daily_insolation", "dates")})
        print("forecast backtest (mean of test weeks):", r["forecast_backtest"]["mean"])
        for case, c in r["stress_week"].items():
            f = c["feeders"]
            print(f"{case:26s} evening unserved: baseline {f['baseline']['evening_window_unserved_kwh']:.0f} kWh, "
                  f"gridsetu {f['gridsetu']['evening_window_unserved_kwh']:.0f} kWh; critical outage "
                  f"{f['baseline']['critical_outage_hours']:.1f} -> {f['gridsetu']['critical_outage_hours']:.1f} h; "
                  f"forecast coverage {c['forecast_net_load']['coverage_q10_q90_pct']:.0f}%")
        return
    if args.cmd == "lv-study":
        from .lvfigures import make_figures
        from .lvnetwork import run_study
        for case, r in run_study(args.in_dir, args.out).items():
            print(f"{case:34s} losses {r['technical_loss_kwh']:8.1f} kWh ({r['technical_loss_pct']:.2f} %)  "
                  f"violations {r['voltage_violation_bus_hours']:6.1f} bus-h  peak loading "
                  f"{r['peak_transformer_loading_pu']:.3f} pu")
        for f in make_figures(f"{args.out}/charts"):
            print("chart:", f)
        return
    if args.cmd == "numbers":
        from .numbers import build_numbers, check_files
        build_numbers(args.out)
        problems = check_files(args.out, args.check)
        for p in problems:
            print("MISMATCH:", p)
        raise SystemExit(1 if problems else 0)
    if args.cmd == "run":
        from .runner import run_all
        run_all(args.out, seeds=args.seeds, config_path=args.config, pf_every=args.pf_every,
                verbose=not args.quiet)


if __name__ == "__main__":
    main()
