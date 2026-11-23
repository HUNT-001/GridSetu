"""Does the Reliability Reserve keep its word?

Every evening GridSetu publishes a reserve with a confidence (T-24h, T-1h, T-15min).
This study re-runs the full simulation over many weather/load seeds, then checks each
published confidence against what actually happened in that evening window.

Three outcomes are scored separately:

* ``own_peak_held`` -- what the published confidence models: import kept under the import
  target in intervals with no DISCOM request, and no local overload trip.
* ``held`` -- the DISCOM's call was met as well: import at or under its limit (the import
  target, or the DISCOM cap) for the whole window, no overload trip, no trip for failing to
  deliver a DISCOM request.
* ``end_to_end`` -- ``held`` and no trip caused by a lost protection (SPS) message, which
  the confidence does not model.

Scores: stated vs observed rates, the Brier score, a reliability table by confidence bin,
and, on evenings with a DISCOM call, the request compared with the published reserve.
Run with ``python -m gridsetu calibrate --seeds 30``.
"""
from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

STAGES = ("T-24h", "T-1h", "T-15min")
OUTCOMES = ("own_peak_held", "held", "end_to_end")
BINS = [0, 50, 70, 80, 90, 95, 99, 100.0001]
TOL_KW = 1.0          # numerical tolerance on the import limit
FAIL_STATES = ("cap_shortfall_trip", "overload_event", "local_trip")


def window_outcomes(feeder_result, week: str, seed: int) -> list[dict]:
    """One row per (evening window, published stage) with stated confidence and outcomes."""
    ts = feeder_result.ts
    state = ts["state"].astype(str)
    rows = []
    for r in feeder_result.reserves:
        if r["stage"] not in STAGES:
            continue
        ws, we = pd.Timestamp(r["window_start"]), pd.Timestamp(r["window_end"])
        m = (ts.index >= ws) & (ts.index < we)
        st = state[m]
        energized = ~st.str.contains("trip")
        lim = ts["limit"][m]
        residual = (ts["import"][m] - lim).where(energized & lim.notna(), 0.0).fillna(0.0)
        failed_state = st.str.startswith(FAIL_STATES).any()
        held = bool(residual.max() <= TOL_KW and not failed_state)
        e2e = held and not st.str.startswith("sps_trip").any()
        req = ts["relief_requested"][m] if "relief_requested" in ts else pd.Series(0.0, index=st.index)
        # SPS emergency calls cap import at 0 without a relief_requested entry: they are DISCOM calls too
        own = energized & (req <= 1e-6) & lim.notna() & ~st.str.startswith("sps")
        own_resid = (ts["import"][m] - lim).where(own, 0.0).fillna(0.0)
        own_peak_held = bool(own_resid.max() <= TOL_KW and not st.str.startswith("overload_event").any())
        max_req = float(req.max()) if len(req) else 0.0
        rows.append({"seed": seed, "week": week, "stage": r["stage"], "window_start": str(ws),
                     "confidence_pct": float(r["confidence_pct"]), "reserve_kw": float(r["reserve_kw"]),
                     "held": held, "end_to_end": e2e, "own_peak_held": own_peak_held,
                     "discom_request": max_req > 1e-6, "max_request_kw": round(max_req, 1),
                     "request_over_reserve": round(max_req / r["reserve_kw"], 2) if r["reserve_kw"] else None,
                     "max_residual_kw": round(float(residual.max()), 2)})
    return rows


def _one_seed(args) -> list[dict]:
    i, config_path = args
    import logging
    import warnings
    warnings.filterwarnings("ignore")
    logging.getLogger("pandapower").setLevel(logging.ERROR)
    logging.getLogger("pyomo").setLevel(logging.ERROR)
    from .simulate import stress_and_representative
    seed = 42 + 100 * i            # same seed schedule as `gridsetu run`
    res = stress_and_representative(config_path, {"simulation": {"seed": seed}}, verbose=False)
    rows = []
    for week in ("stress", "representative"):
        rows += window_outcomes(res[week].feeder["gridsetu"], week, seed)
    return rows


def _request_stats(df: pd.DataFrame) -> dict:
    """Evenings where the DISCOM asked this feeder for relief, at the T-15min stage."""
    d = df[(df.stage == "T-15min") & df.discom_request]
    if d.empty:
        return {"n_evenings": 0}
    return {"n_evenings": int(len(d)),
            "share_of_all_evenings_pct": round(100 * len(d) / int((df.stage == "T-15min").sum()), 1),
            "held_pct": round(100 * float(d.held.mean()), 1),
            "request_over_reserve_median": round(float(d.request_over_reserve.median()), 2),
            "request_over_reserve_min": round(float(d.request_over_reserve.min()), 2),
            "request_over_reserve_max": round(float(d.request_over_reserve.max()), 2),
            "stated_confidence_mean_pct": round(float(d.confidence_pct.mean()), 1)}


def score(df: pd.DataFrame, outcome: str = "held") -> dict:
    p = df["confidence_pct"].to_numpy() / 100
    y = df[outcome].to_numpy().astype(float)
    table = []
    cut = pd.cut(df["confidence_pct"], BINS, right=False)
    for b, g in df.groupby(cut, observed=True):
        table.append({"bin": f"{b.left:g}-{min(b.right, 100):g}%", "n": int(len(g)),
                      "stated_mean_pct": round(float(g["confidence_pct"].mean()), 1),
                      "observed_pct": round(100 * float(g[outcome].mean()), 1)})
    hi = df["confidence_pct"] >= 99
    return {
        "n_forecasts": int(len(df)),
        "brier": round(float(np.mean((p - y) ** 2)), 4),
        "stated_mean_pct": round(100 * float(p.mean()), 1),
        "observed_pct": round(100 * float(y.mean()), 1),
        "n_stated_ge_99": int(hi.sum()),
        "observed_when_stated_ge_99_pct": round(100 * float(df.loc[hi, outcome].mean()), 1) if hi.any() else None,
        "reliability_table": table,
    }


def run_calibration(seeds: int = 30, out_dir: str | Path = "outputs", config_path=None,
                    workers: int = 2, verbose: bool = True) -> dict:
    out = Path(out_dir) / "calibration"
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(i, config_path) for i in range(seeds)]
    rows: list[dict] = []
    with ProcessPoolExecutor(max_workers=max(1, workers)) as ex:
        for k, r in enumerate(ex.map(_one_seed, jobs), 1):
            rows += r
            if verbose:
                print(f"seed {k}/{seeds} done ({len(r)} forecasts)", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(out / "reserve_forecasts.csv", index=False)
    result = {
        "about": {"label": "SIMULATION: synthetic data, not field measurement",
                  "seeds": seeds, "weeks_per_seed": ["stress", "representative"],
                  "outcome_held": "import kept at or under the limit for the whole evening window, "
                                  "no overload trip, no trip for a missed DISCOM request",
                  "outcome_end_to_end": "held, and no trip from a lost SPS protection message",
                  "outcome_own_peak_held": "what the published confidence models: import kept under the "
                                           "import target in intervals with no DISCOM request, no overload trip"},
        "by_stage": {s: {o: score(df[df.stage == s], o) for o in OUTCOMES} for s in STAGES},
        "all_stages": {o: score(df, o) for o in OUTCOMES},
        "by_week": {w: {o: score(df[df.week == w], o) for o in OUTCOMES} for w in sorted(df.week.unique())},
        "discom_request_evenings": _request_stats(df),
    }
    (out / "calibration.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    plot_reliability(df, out / "reserve_calibration.png", seeds)
    return result


def plot_reliability(df: pd.DataFrame, path: Path, seeds: int) -> Path:
    """Left: stated confidence vs observed outcome, by outcome and week type.
    Right: on evenings the DISCOM asked for relief, its request vs the published reserve."""
    from .plots import AMBER, GREY, INK, MUTED, NAVY, SIM_LABEL, TEAL, _save, _sim_tag, _style
    import matplotlib.pyplot as plt
    _style()
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(13, 6.2), gridspec_kw={"width_ratios": [1.1, 1]})
    t15 = df[df.stage == "T-15min"]
    groups = [("Normal week", t15[t15.week == "representative"]), ("Stress week", t15[t15.week == "stress"])]
    series = [("Stated confidence", None, GREY),
              ("Own evening peak held\n(what the confidence models)", "own_peak_held", NAVY),
              ("DISCOM call met\n(no shortfall trip)", "held", TEAL)]
    x = np.arange(len(groups))
    w = 0.26
    for j, (label, col, colour) in enumerate(series):
        vals = [g.confidence_pct.mean() if col is None else 100 * g[col].mean() for _, g in groups]
        bars = ax.bar(x + (j - 1) * w, vals, w, color=colour, label=label)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 1, f"{v:.0f}%", ha="center", va="bottom",
                    fontsize=10.5, color=INK, fontweight="bold")
    ax.set_xticks(x, [f"{n}\n({len(g)} evenings)" for n, g in groups])
    ax.set_ylim(0, 118)
    ax.set_ylabel("% of evenings")
    ax.set_title("Stated vs observed (T−15 min reserve)", loc="left")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.17), fontsize=9, ncol=3)
    ax.grid(axis="x", visible=False)

    d = t15[t15.discom_request]
    if len(d):
        ok, bad = d[d.held], d[~d.held]
        ax2.scatter(bad.reserve_kw, bad.max_request_kw, s=28, color=AMBER, edgecolor=INK, lw=0.4,
                    label=f"call not met: feeder rotated off, Tier 1 islanded ({len(bad)})")
        if len(ok):
            ax2.scatter(ok.reserve_kw, ok.max_request_kw, s=28, color=TEAL, edgecolor="white", lw=0.4,
                        label=f"call met ({len(ok)})")
        top_v = max(d.max_request_kw.max(), d.reserve_kw.max()) * 1.1
        ax2.plot([0, top_v], [0, top_v], color=GREY, ls="--", lw=1.2)
        ax2.text(top_v * 0.62, top_v * 0.55, "request = published reserve", color=MUTED, fontsize=9, rotation=36)
        ax2.set_xlim(0, top_v)
        ax2.set_ylim(0, top_v)
        ax2.legend(loc="upper left", fontsize=9)
    ax2.set_xlabel("Published reserve at T−15 min (kW)")
    ax2.set_ylabel("Largest DISCOM relief request (kW)")
    ax2.set_title("Evenings with a DISCOM call: request vs offer", loc="left")
    fig.suptitle(f"Does the Reliability Reserve keep its word?  {len(df):,} published forecasts, "
                 f"{seeds} seeds × 2 weeks", x=0.01, ha="left", fontsize=14, fontweight="bold", color=INK)
    fig.tight_layout(rect=(0, 0.03, 1, 0.94))
    _sim_tag(fig, SIM_LABEL + " · T−24h and T−1h stages give the same result")
    return _save(fig, path)
