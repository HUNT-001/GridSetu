"""Synthetic households against real Indian smart-meter data (Prayas eMARC, CC0).

    python -m gridsetu household-check [--sensitivity]     # writes outputs/households/

Compares the simulator's homes (representative September week, seed 42) with 116 measured
main-line meters (data/real/emarc_mainline_summary.json, Aug-Oct and all year): daily energy,
evening load, how much evening load lies above the 200 W lifeline floor, the daily shape and how
coincident homes are, for both household models:
  fitted  (headline) 1,090 homes fitted to eMARC, feeder demand anchored at the evening peak
  legacy             the first model: 420 heavy, highly coincident homes
With --sensitivity it re-runs the monthly study under both models.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .plots import AMBER, GREY, INK, MUTED, NAVY, TEAL, _save, _sim_tag, _style
from .simulate import stress_and_representative

ROOT = Path(__file__).resolve().parents[2]
EMARC = ROOT / "data" / "real" / "emarc_mainline_summary.json"
TN_DOMESTIC_KWH_PER_DAY = 30602.014e6 / 23861586 / 365   # TN DES 2022-23: domestic MU / connections
KEYS = ("evening_window_unserved_kwh", "total_unserved_kwh", "critical_outage_hours", "feeder_outage_hours",
        "dark_home_hours", "lifeline_home_hours", "overload_trips")


def synthetic_stats(hh: np.ndarray) -> dict:
    n, T = hh.shape
    d = hh.reshape(n, T // 96, 96)
    days = d.reshape(-1, 96)
    daily, peak = days.sum(1) * 0.25, days.max(1)
    ev = days[:, 70:78]
    prof = days.mean(0)
    return {"home_days": int(days.shape[0]),
            "daily_kwh_mean": round(float(daily.mean()), 3),
            "daily_kwh_p10": round(float(np.percentile(daily, 10)), 3),
            "daily_kwh_p50": round(float(np.percentile(daily, 50)), 3),
            "daily_kwh_p90": round(float(np.percentile(daily, 90)), 3),
            "peak_kw_p50": round(float(np.percentile(peak, 50)), 3),
            "peak_kw_p90": round(float(np.percentile(peak, 90)), 3),
            "evening_mean_kw": round(float(ev.mean()), 4),
            "evening_above_200w_share": round(float(np.maximum(ev - 0.2, 0).sum() / ev.sum()), 4),
            "profile_peak_block": int(prof.argmax()),
            "profile_peak_over_mean": round(float(prof.max() / prof.mean()), 3),
            "coincidence": round(float(d.mean(0).max(1).mean() / peak.mean()), 3),
            "profile": [round(float(x), 4) for x in prof]}


LEGACY = {"pilot_feeder": {"households": 420, "household_model": {"source": "legacy"}, "target_peak_window": "any"}}
CASES = {"fitted_1090": {}, "legacy_420": LEGACY}


def sensitivity(seeds=(42, 142, 242)) -> dict:
    out = {}
    for name, over in CASES.items():
        acc, kwh = {}, None
        for seed in seeds:
            r = stress_and_representative(None, {**over, "simulation": {"seed": seed}}, verbose=False)
            for wk, w in (("stress", 1), ("representative", 3)):
                for v in ("baseline", "gridsetu"):
                    m = r[wk].feeder[v].metrics
                    for k in KEYS:
                        acc.setdefault((v, k), []).append(m[k] * w)
            if kwh is None:
                hh = r["representative"].feeder_loads.hh_load
                kwh = float(hh.sum() * 0.25 / hh.shape[0] / (hh.shape[1] / 96))
        res = {v: {k: round(float(np.reshape(acc[(v, k)], (len(seeds), 2)).sum(1).mean()), 1) for k in KEYS}
               for v in ("baseline", "gridsetu")}
        res["home_kwh_per_day"] = round(kwh, 2)
        out[name] = res
    return out


def _chart(out: Path, syn: dict, real: dict, leg: dict) -> None:
    _style()
    x = np.arange(96) / 4
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(13, 5), gridspec_kw={"width_ratios": [1.6, 1]})
    ax.plot(x, leg["profile"], color=GREY, lw=1.8, ls="--", label="First model: 420 heavy homes (replaced)")
    ax.plot(x, syn["profile"], color=NAVY, lw=2, label="Fitted model: 1,090 homes (now used)")
    ax.plot(x, real["profile"], color=TEAL, lw=2.2, label="Measured Indian home, Aug–Oct (Prayas eMARC, 116 meters)")
    ax.axhline(0.2, color=AMBER, ls="--", lw=1.2)
    ax.text(0.3, 0.215, "200 W lifeline floor", color=AMBER, fontsize=9)
    ax.axvspan(17.5, 19.5, color=MUTED, alpha=0.08, lw=0)
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 3))
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("Average load per home (kW)")
    ax.set_title("Average day per home: fitted model against measured homes", loc="left")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=1, frameon=False, fontsize=9)

    rows = [("Daily energy (kWh)", "daily_kwh_mean"), ("Evening load (kW)", "evening_mean_kw"),
            ("Evening load above 200 W", "evening_above_200w_share"), ("Coincidence", "coincidence")]
    y = np.arange(len(rows))
    h = 0.26
    for j, (src, col, lab) in enumerate(((leg, GREY, "first model"), (syn, NAVY, "fitted model"), (real, TEAL, "measured"))):
        vals = [src[k] for _, k in rows]
        rel = [v / real[k] for v, (_, k) in zip(vals, rows)]
        ax2.barh(y + (j - 1) * h, rel, height=h, color=col, label=lab)
        for i, v in enumerate(vals):
            ax2.text(rel[i] + 0.03, i + (j - 1) * h, f"{v:.2f}", va="center", fontsize=7.5, color=INK)
    ax2.set_yticks(y, [r for r, _ in rows])
    ax2.invert_yaxis()
    ax2.set_xlim(0, 3.2)
    ax2.axvline(1, color=TEAL, lw=1, ls=":")
    ax2.set_title("Each model ÷ measured (1 = matches)", loc="left")
    ax2.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=1, frameon=False, fontsize=9)
    fig.subplots_adjust(bottom=0.27, wspace=0.45)
    _sim_tag(fig, f"Real data: Prayas eMARC (Maharashtra, Uttar Pradesh), CC0 · Tamil Nadu average: "
                  f"{TN_DOMESTIC_KWH_PER_DAY:.1f} kWh/day per domestic connection (TN DES 2022-23)")
    _save(fig, out / "charts" / "households_real_vs_synthetic.png")


def run_study(out_dir: str | Path = "outputs/households", with_sensitivity: bool = False) -> dict:
    out = Path(out_dir)
    (out / "charts").mkdir(parents=True, exist_ok=True)
    emarc = json.loads(EMARC.read_text(encoding="utf-8"))
    r = stress_and_representative(None, {"simulation": {"seed": 42}}, verbose=False)
    syn = synthetic_stats(r["representative"].feeder_loads.hh_load)
    rl = stress_and_representative(None, {**LEGACY, "simulation": {"seed": 42}}, verbose=False)
    leg = synthetic_stats(rl["representative"].feeder_loads.hh_load)
    real, real_all = emarc["groups"]["all|aug_oct"], emarc["groups"]["all|all_year"]
    res = {"about": {"label": "Synthetic homes (simulation) against measured Indian homes (REAL, Prayas eMARC)",
                     "emarc_source": emarc["source"], "tn_domestic_kwh_per_day": round(TN_DOMESTIC_KWH_PER_DAY, 2),
                     "tn_source": "https://des.tn.gov.in/sites/default/files/2025-07/10.%20ELECTRICITY.pdf"},
           "synthetic": {k: v for k, v in syn.items() if k != "profile"},
           "legacy_synthetic": {k: v for k, v in leg.items() if k != "profile"},
           "measured_aug_oct": {k: v for k, v in real.items() if k != "profile"},
           "measured_all_year": {k: v for k, v in real_all.items() if k != "profile"},
           "synthetic_over_measured_daily_kwh": round(syn["daily_kwh_mean"] / real["daily_kwh_mean"], 2),
           "synthetic_over_tn_average_daily_kwh": round(syn["daily_kwh_mean"] / TN_DOMESTIC_KWH_PER_DAY, 2)}
    if with_sensitivity:
        res["fitted_vs_legacy"] = sensitivity()
    else:
        prev = out / "households.json"
        if prev.exists():
            old = json.loads(prev.read_text(encoding="utf-8"))
            if "fitted_vs_legacy" in old:
                res["fitted_vs_legacy"] = old["fitted_vs_legacy"]
    (out / "households.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    _chart(out, syn, real, leg)
    return res
