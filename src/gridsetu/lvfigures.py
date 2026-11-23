"""Charts for the low-voltage study (deck graphs 3-8), drawn from the MATLAB results.

Reads ``matlab/results/`` (written by ``matlab/run_f07.m``); falls back to the Python twin's
``outputs/lv/`` when MATLAB results are absent. ``matlab/make_figures.m`` draws the same
charts in MATLAB.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .lvnetwork import ROOT, load_params
from .plots import AMBER, GREY, INK, MUTED, NAVY, SIM_LABEL, TEAL, _save, _sim_tag, _style

SCEN = [("baseline", "Baseline", GREY), ("gridsetu", "GridSetu (battery at transformer)", NAVY),
        ("gridsetu_distributed", "GridSetu (storage split across circuits)", TEAL)]
TAG = SIM_LABEL + " · MATLAB low-voltage model, assumed network (matlab/f07_params.json)"


def _steps(res: Path, week: str, name: str) -> pd.DataFrame:
    return pd.read_csv(res / f"f07_{week}_{name}_steps.csv", index_col=0, parse_dates=True)


def _results_dir() -> Path:
    m = ROOT / "matlab" / "results"
    return m if (m / "summary.json").exists() else ROOT / "outputs" / "lv"


def make_figures(out_dir: str | Path = "outputs/lv/charts") -> list[Path]:
    _style()
    res = _results_dir()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    p = load_params()
    lo, hi = p["v_limit_pu"]
    topo = p["topology"]
    nbc = topo["buses_per_circuit"]
    seg = topo["circuit_length_m"] / nbc
    summ = json.loads((res / "summary.json").read_text(encoding="utf-8"))
    key = (lambda w, n: f"{w}_{n}") if "stress_baseline" in summ else (lambda w, n: f"{w}/{n}")
    st = {n: _steps(res, "stress", n) for n, _, _ in SCEN}
    paths = []

    # 3 -- voltage along the worst circuit at the worst evening step (baseline)
    b = st["baseline"]
    ev = b.between_time("17:30", "19:15")
    t_star = ev["v_min_pu"].idxmin()
    worst_bus = int(b.loc[t_star, "v_min_bus"])
    circ = (worst_bus - 1) // nbc
    buses = [circ * nbc + k + 1 for k in range(nbc)]
    x = np.arange(0, nbc + 1) * seg
    fig, ax = plt.subplots(figsize=(11, 5.6))
    ax.axhspan(lo, hi, color=TEAL, alpha=0.07, lw=0)
    ax.axhline(lo, color=AMBER, lw=1.2, ls="--")
    ax.text(x[-1], lo + 0.004, f"lower limit {lo:.2f} pu", ha="right", color=MUTED, fontsize=9)
    for n, label, colour in SCEN:
        d = st[n]
        if t_star in d.index and d.loc[t_star, "energized"] == 1:
            vs = [d.loc[t_star, f"v_bus_{bb:02d}"] for bb in buses]
            ax.plot(x[1:], vs, marker="o", color=colour, lw=2.2, label=f"{label}: tail {vs[-1]:.3f} pu")
    ax.set_xlim(0, x[-1] * 1.04)
    ax.set_xlabel(f"Distance along circuit {'ABC'[circ]} from the transformer (m)")
    ax.set_ylabel("Voltage (pu of 415 V)")
    ax.set_title(f"Voltage along circuit {'ABC'[circ]} at {t_star:%a %H:%M}, the worst evening step of the stress week",
                 loc="left")
    ax.legend(loc="lower left", fontsize=9)
    _sim_tag(fig, TAG)
    paths.append(_save(fig, out / "lv_voltage_profile.png"))

    # 4 -- week-long voltage heat-strip, baseline vs storage split across circuits
    fig, axes = plt.subplots(2, 1, figsize=(13, 6.4), sharex=True)
    vcols = [f"v_bus_{k:02d}" for k in range(1, topo["circuits"] * nbc + 1)]
    for ax, (n, label, _) in zip(axes, [SCEN[0], SCEN[2]]):
        m = st[n][vcols].to_numpy().T
        im = ax.imshow(m, aspect="auto", cmap="RdYlGn", vmin=0.80, vmax=1.06, interpolation="nearest",
                       extent=[0, m.shape[1] / 96, m.shape[0] + 0.5, 0.5])
        ax.set_ylabel("Bus")
        ax.set_title(f"{label}: violation bus-hours {summ[key('stress', n)]['voltage_violation_bus_hours']:.0f}",
                     loc="left", fontsize=11)
        for c in range(1, topo["circuits"]):
            ax.axhline(c * nbc + 0.5, color="white", lw=1.5)
    axes[-1].set_xlabel("Day of the stress week (white = feeder off)")
    cb = fig.colorbar(im, ax=axes, shrink=0.85, pad=0.01)
    cb.set_label("Voltage (pu)")
    fig.suptitle("Bus voltages, every 15 minutes for a week (red = below the limit)", x=0.01, ha="left",
                 fontsize=14, fontweight="bold", color=INK)
    _sim_tag(fig, TAG)
    paths.append(_save(fig, out / "lv_voltage_heatstrip.png"))

    # 5 -- daily technical losses
    fig, ax = plt.subplots(figsize=(11, 5.4))
    w = 0.27
    days = None
    for j, (n, label, colour) in enumerate(SCEN):
        d = st[n]
        daily = ((d["line_loss_kw"] + d["dt_cu_loss_kw"] + d["dt_nl_loss_kw"]) * 0.25).groupby(d.index.date).sum()
        days = daily.index
        ax.bar(np.arange(len(daily)) + (j - 1) * w, daily.values, w, color=colour,
               label=f"{label}: {summ[key('stress', n)]['technical_loss_kwh']:,.0f} kWh/week")
    ax.set_xticks(np.arange(len(days)), [pd.Timestamp(d).strftime("%a") for d in days])
    ax.set_ylabel("Technical losses (kWh/day)")
    ax.set_title("Technical losses per day, stress week (lines + transformer)", loc="left")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), fontsize=9, ncol=3)
    ax.grid(axis="x", visible=False)
    _sim_tag(fig, TAG)
    paths.append(_save(fig, out / "lv_losses_daily.png"))

    # 6 -- transformer hot-spot temperature
    fig, ax = plt.subplots(figsize=(12, 5.2))
    for n, label, colour in SCEN[:2]:
        d = st[n]
        ax.plot(d.index, d["theta_hotspot_c"], color=colour, lw=1.6,
                label=f"{label}: peak {summ[key('stress', n)]['max_hotspot_c']:.1f} °C, "
                      f"peak loading {summ[key('stress', n)]['peak_transformer_loading_pu']:.2f} pu")
    ax.axhline(98, color=AMBER, ls="--", lw=1.2)
    ax.text(st["baseline"].index[3], 99, "98 °C: normal ageing rate (IEC 60076-7)", color=MUTED, fontsize=9)
    ax.set_ylabel("Hot-spot temperature (°C)")
    ax.set_title("Transformer hot-spot temperature, stress week", loc="left")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), fontsize=9, ncol=2)
    _sim_tag(fig, TAG)
    paths.append(_save(fig, out / "lv_hotspot.png"))

    # 7 -- what a one-point model misses
    d = st["baseline"]
    on = d["energized"] == 1
    fig, ax = plt.subplots(figsize=(7.4, 6.4))
    ax.scatter(d.loc[on, "python_import_kw"], d.loc[on, "p_dt_kw"], s=8, color=NAVY, alpha=0.5)
    lim = [0, max(d.loc[on, "p_dt_kw"].max(), d.loc[on, "python_import_kw"].max()) * 1.05]
    ax.plot(lim, lim, color=GREY, ls="--", lw=1.2)
    ax.text(lim[1] * 0.55, lim[1] * 0.47, "1:1 (no losses)", color=MUTED, fontsize=9, rotation=40)
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.set_xlabel("Feeder import, one-point Python model (kW)")
    ax.set_ylabel("Power into the transformer, MATLAB network model (kW)")
    ax.set_title("The gap above the line is the technical loss\nthe one-point model cannot see", loc="left")
    _sim_tag(fig, TAG)
    paths.append(_save(fig, out / "lv_model_agreement.png"))

    # 8 -- scenario comparison
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.8))
    metrics = [("technical_loss_kwh", "Technical losses (kWh/week)"),
               ("voltage_violation_bus_hours", "Voltage violations (bus-hours/week)"),
               ("peak_transformer_loading_pu", "Peak transformer loading (pu)")]
    for ax, (m, title) in zip(axes, metrics):
        vals = [summ[key("stress", n)][m] for n, _, _ in SCEN]
        bars = ax.bar(range(3), vals, color=[c for _, _, c in SCEN])
        for bb, v in zip(bars, vals):
            ax.text(bb.get_x() + bb.get_width() / 2, v, f"{v:,.2f}" if v < 10 else f"{v:,.0f}",
                    ha="center", va="bottom", fontsize=10, fontweight="bold", color=INK)
        ax.set_xticks(range(3), ["Baseline", "GridSetu\n(at transformer)", "GridSetu\n(split)"], fontsize=9)
        ax.set_title(title, loc="left", fontsize=11)
        ax.grid(axis="x", visible=False)
    fig.suptitle("Where the storage sits matters: same battery, three placements (stress week)", x=0.01,
                 ha="left", fontsize=14, fontweight="bold", color=INK)
    fig.tight_layout(rect=(0, 0.04, 1, 0.92))
    _sim_tag(fig, TAG)
    paths.append(_save(fig, out / "lv_placement.png"))
    return paths
