"""Command line: python -m gridsetu run [--seeds 3] [--out outputs] [--config config/city.yaml]"""
from __future__ import annotations

import argparse
import logging
import warnings


def main(argv=None):
    ap = argparse.ArgumentParser(prog="gridsetu", description="GridSetu Phase 1 smart-grid simulator")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the full Phase 1 study and write outputs")
    r.add_argument("--seeds", type=int, default=3, help="weather/load seeds to average over")
    r.add_argument("--out", default="outputs", help="output folder")
    r.add_argument("--config", default=None, help="scenario YAML (default config/city.yaml)")
    r.add_argument("--pf-every", type=int, default=2, help="run AC power flow every N steps")
    r.add_argument("--quiet", action="store_true")
    sv = sub.add_parser("serve", help="start the API (and the built dashboard, if web/dist exists)")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--seeds", type=int, default=3, help="seeds for the reference run")
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
    if args.cmd == "run":
        from .runner import run_all
        run_all(args.out, seeds=args.seeds, config_path=args.config, pf_every=args.pf_every,
                verbose=not args.quiet)


if __name__ == "__main__":
    main()
