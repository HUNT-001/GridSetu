"""Deck-ready charts (matplotlib, PNG). Colours follow the GridSetu deck design system,
with the proposed/teal series stepped darker so baseline-vs-proposed stays separable for
colour-vision-deficient readers (validated: CVD dE 17.8, normal-vision dE 21.9).
Every chart carries a SIMULATION label and values are direct-labelled."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

NAVY = "#0B1F3A"
TEAL = "#0F766E"        # proposed / GridSetu
TEAL_LIGHT = "#99D5CF"  # bands and fills behind the teal line
GREY = "#9CA3AF"        # baseline / neutral
AMBER = "#F5A623"       # gap / alert highlight (fills only, never text)
INK = "#1F2937"
MUTED = "#6B7280"
GRID = "#E5E7EB"
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SIM_LABEL = "SIMULATION: synthetic data, not field measurement"


def _style():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": GRID,
        "axes.labelcolor": INK, "axes.titlecolor": INK, "axes.titlesize": 13,
        "axes.titleweight": "bold", "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
        "figure.facecolor": "white", "axes.facecolor": "white", "savefig.dpi": 200,
    })


def _sim_tag(fig, text=SIM_LABEL):
    fig.text(0.995, 0.005, text, ha="right", va="bottom", fontsize=8.5, color=MUTED)


def _save(fig, path: Path):
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


# ------------------------------------------------------------------ slide 2
def slide2_profile(week, out: Path, day: int = 1) -> Path:
    _style()
    sc, fl = week.sc, week.feeder_loads
    s = slice(day * sc.steps_per_day, (day + 1) * sc.steps_per_day)
    idx = sc.index[s]
    hours = idx.hour + idx.minute / 60
    demand = fl.gross_load[s]
    solar = fl.rooftop_pv[s] + fl.community_pv[s]
    cap = sc.feeder["capacity_kw"]
    fig, ax = plt.subplots(figsize=(11, 5.2))
    win = (hours >= 17.5) & (hours < 19.5)
    ax.fill_between(hours, solar, demand, where=win, color=AMBER, alpha=0.35, step=None,
                    linewidth=0, label="Reliability gap")
    ax.plot(hours, demand, color=GREY, lw=2.4, label="Feeder demand")
    ax.plot(hours, solar, color=TEAL, lw=2.4, label="Solar (rooftop + community)")
    ax.axhline(cap, color=INK, lw=1, ls=(0, (4, 3)))
    ax.text(0.3, cap + 6, f"Transformer rating {cap:.0f} kW", color=INK, fontsize=10)
    pk = int(np.argmax(demand))
    ax.annotate(f"{demand[pk]:.0f} kW", (hours[pk], demand[pk]), xytext=(8, 6),
                textcoords="offset points", color=INK, fontsize=10, fontweight="bold")
    ax.text(18.5, max(demand[win].min() * 0.55, 40), "Reliability\nGap", ha="center",
            color=INK, fontsize=12, fontweight="bold")
    ax.text(hours[-1], demand[-1], "  Demand", color=MUTED, va="center", fontsize=10)
    spk = int(np.argmax(solar))
    ax.text(hours[spk], solar[spk] + 8, "Solar", color=MUTED, ha="center", fontsize=10)
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 3))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 25, 3)])
    ax.set_ylabel("kW")
    ax.set_ylim(0, max(demand.max(), cap) * 1.15)
    ax.set_title(f"Pilot feeder, one day ({idx[0]:%a %d %b}): demand vs solar")
    ax.legend(loc="upper left", ncol=3, bbox_to_anchor=(0, -0.1))
    fig.text(0.995, 0.93, SIM_LABEL, ha="right", fontsize=8.5, color=MUTED)
    return _save(fig, out / "slide2_24h_profile.png")


# ------------------------------------------------------------------ slide 8
def slide8_bars(summary: dict, out: Path) -> Path:
    _style()
    items = [
        ("Unserved energy, evening ramp", "kWh / month", "evening_window_unserved_kwh"),
        ("Critical-load outage", "hours / month", "critical_outage_hours"),
        ("Feeder peak import", "kW", "feeder_peak_import_kw"),
        ("Whole-feeder outage", "hours / month", "feeder_outage_hours"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5))
    for ax, (title, unit, key) in zip(axes.flat, items):
        b = summary["baseline"][key]["mean"]
        p = summary["gridsetu"][key]["mean"]
        bars = ax.bar(["Baseline", "GridSetu"], [b, p], color=[GREY, TEAL], width=0.55,
                      edgecolor="white", linewidth=2)
        for bar, v, key2 in zip(bars, [b, p], ["baseline", "gridsetu"]):
            lo, hi = summary[key2][key]["min"], summary[key2][key]["max"]
            ax.text(bar.get_x() + bar.get_width() / 2, v, f"{v:,.0f}" if v >= 100 else f"{v:,.1f}",
                    ha="center", va="bottom", color=INK, fontsize=12, fontweight="bold")
            if hi > lo:
                ax.plot([bar.get_x() + bar.get_width() / 2] * 2, [lo, hi], color=INK, lw=1)
        chg = (p - b) / b * 100 if b else 0.0
        ax.set_title(f"{title}\n", loc="left")
        ax.text(0, 1.02, f"{unit}   ·   change {chg:+.0f}%", transform=ax.transAxes,
                color=MUTED, fontsize=10)
        ax.set_ylim(0, max(b, p) * 1.25 if max(b, p) > 0 else 1)
        ax.grid(axis="x", visible=False)
    fig.suptitle("Baseline vs GridSetu, pilot feeder (monthly composite: 3 normal + 1 stress week)",
                 x=0.01, ha="left", fontsize=14, fontweight="bold", color=INK)
    fig.tight_layout(rect=(0, 0.02, 1, 0.96))
    _sim_tag(fig, SIM_LABEL + " · bars = mean, whiskers = range across seeds")
    return _save(fig, out / "slide8_baseline_vs_proposed.png")


# ------------------------------------------------------------------ city dispatch
KIND_ORDER = ["thermal", "gas", "hydro", "import", "wind", "solar"]


def city_dispatch(week, out: Path, scenario: str = "baseline") -> Path:
    _style()
    sc = week.sc
    rt = week.city[scenario]["rt"]
    inp = week.city[scenario]["inputs"]
    by_kind = {}
    for gid, g in sc.generators.items():
        by_kind[g["kind"]] = by_kind.get(g["kind"], 0) + rt.gen[gid].values
    rooftop = sum(inp.rooftop.values())
    demand = sum(inp.loads[r].sum(axis=1).values for r in inp.loads)
    shed = sum(rt.shed[r].sum(axis=1).values for r in rt.shed)
    fig, ax = plt.subplots(figsize=(13, 5.5))
    stack = [by_kind.get(k, np.zeros(sc.n_steps)) for k in KIND_ORDER] + [rooftop]
    labels = [k.capitalize() if k != "import" else "National import" for k in KIND_ORDER] + ["Rooftop solar"]
    ax.stackplot(sc.index, *stack, colors=CAT[:len(stack)], labels=labels, edgecolor="white", linewidth=0.3)
    ax.plot(sc.index, demand, color=INK, lw=1.6, label="Demand")
    ax.fill_between(sc.index, demand - shed, demand, where=shed > 0.01, facecolor="white",
                    edgecolor=INK, hatch="////", linewidth=0.6, label="Load shed")
    for o in sc.raw.get("forced_outages", []):
        ax.axvline(np.datetime64(o["start"]), color=INK, lw=1, ls=":")
        ax.text(np.datetime64(o["start"]), demand.max() * 1.04, " G1B forced outage", color=INK, fontsize=9)
    ax.set_ylabel("MW")
    ax.set_ylim(0, demand.max() * 1.12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %d"))
    ax.set_title(f"Setu Nagar city dispatch by source, real time ({scenario})")
    ax.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0))
    _sim_tag(fig)
    return _save(fig, out / f"city_dispatch_{scenario}.png")


def market_prices(week, out: Path) -> Path:
    _style()
    sc = week.sc
    da = week.city["baseline"]["da"]
    cap = sc.raw["exchange_price"]["price_cap"]
    mcp = da.mcp(cap)
    fig, ax = plt.subplots(figsize=(13, 4.5))
    for i, r in enumerate(mcp.columns):   # widest first so coinciding prices stay visible
        ax.plot(sc.index, mcp[r], color=CAT[i], lw=[4.5, 2.8, 1.3][i % 3], label=f"{r} {sc.regions[r]['name']}")
    scarce = da.price.max(axis=1).values >= cap - 1e-6
    ax.fill_between(sc.index, 0, cap * 1.05, where=scarce, color=AMBER, alpha=0.25, linewidth=0,
                    label="Scarcity (price at cap)")
    ax.axhline(cap, color=INK, lw=1, ls=(0, (4, 3)))
    ax.text(sc.index[2], cap + 0.2, f"Exchange ceiling ₹{cap:.0f}/kWh", color=INK, fontsize=9)
    ax.set_ylabel("₹ / kWh")
    ax.set_ylim(0, cap * 1.15)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %d"))
    ax.set_title("Day-ahead market clearing price by bid area (areas split only when interties congest)")
    ax.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0))
    _sim_tag(fig)
    return _save(fig, out / "market_clearing_price.png")


def load_classes(week, factors_df, out: Path) -> Path:
    _style()
    sc = week.sc
    loads = week.city["baseline"]["inputs"].loads
    from .config import CLASSES
    fig, axes = plt.subplots(2, 3, figsize=(13, 6.5), sharex=True)
    h = np.arange(sc.steps_per_day) * sc.dt_h
    city_rows = factors_df[factors_df.region == "CITY"].set_index("class")
    for i, (ax, c) in enumerate(zip(axes.flat, CLASSES)):
        x = sum(loads[r][c].values for r in loads).reshape(sc.n_days, -1)
        ax.fill_between(h, x.min(axis=0), x.max(axis=0), color=CAT[i], alpha=0.18, linewidth=0)
        ax.plot(h, x.mean(axis=0), color=CAT[i], lw=2)
        row = city_rows.loc[c]
        ax.set_title(f"{c.capitalize()}  (priority {int(row.priority)})", loc="left", fontsize=12)
        ax.text(0.02, 0.95, f"peak {row.max_demand_mw:.0f} MW\nload factor {row.load_factor:.2f}\n"
                f"demand factor {row.demand_factor:.2f}\ndiversity {row.diversity_factor:.2f}",
                transform=ax.transAxes, va="top", fontsize=9, color=INK)
        ax.set_xticks([0, 6, 12, 18, 24])
        ax.set_ylim(0, x.max() * 1.45)
    for ax in axes[1]:
        ax.set_xlabel("hour of day")
    for ax in axes[:, 0]:
        ax.set_ylabel("MW")
    fig.suptitle("Load curves by consumer class (line = weekly mean, band = daily range)",
                 x=0.01, ha="left", fontweight="bold", color=INK)
    fig.tight_layout(rect=(0, 0.02, 1, 0.95))
    _sim_tag(fig)
    return _save(fig, out / "load_curves_by_class.png")


def feeder_week(week, out: Path) -> Path:
    _style()
    sc = week.sc
    b = week.feeder["baseline"].ts
    g = week.feeder["gridsetu"].ts
    cap = sc.feeder["capacity_kw"]
    E = sc.feeder["battery"]["energy_kwh"]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 7), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
    a1.plot(sc.index, b["import"], color=GREY, lw=1.6, label="Baseline import")
    a1.plot(sc.index, g["import"], color=TEAL, lw=1.6, label="GridSetu import")
    out_b = b["state"].astype(str).str.contains("trip").values
    a1.fill_between(sc.index, 0, cap * 1.2, where=out_b, color=AMBER, alpha=0.35, linewidth=0,
                    label="Baseline feeder outage")
    a1.axhline(cap, color=INK, lw=1, ls=(0, (4, 3)))
    a1.text(sc.index[2], cap + 5, f"rating {cap:.0f} kW", fontsize=9, color=INK)
    a1.set_ylabel("kW at feeder head")
    a1.set_ylim(0, cap * 1.25)
    a1.legend(loc="upper left", ncol=3, bbox_to_anchor=(0, 1.13))
    a1.set_title(f"Pilot feeder, {week.label}", pad=28)
    a2.plot(sc.index, 100 * g["soc"] / E, color=TEAL, lw=1.6)
    a2.set_ylabel("Battery SOC %")
    a2.set_ylim(0, 100)
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%a %d"))
    _sim_tag(fig)
    fig.tight_layout()
    name = "feeder_week_" + week.label.split()[0] + ".png"
    return _save(fig, out / name)


def forecast_bands(week, out: Path, days=(1, 3)) -> Path:
    _style()
    sc = week.sc
    fc = week.forecast["net_load"]
    fl = week.feeder_loads
    s = slice(days[0] * sc.steps_per_day, days[1] * sc.steps_per_day)
    idx = sc.index[s]
    fig, ax = plt.subplots(figsize=(13, 4.6))
    ax.fill_between(idx, fc.q10[s], fc.q90[s], color=TEAL_LIGHT, alpha=0.6, linewidth=0, label="q10 to q90 band")
    ax.plot(idx, fc.q50[s], color=TEAL, lw=2, label="q50 forecast")
    ax.plot(idx, fl.net_load[s], color=INK, lw=1.2, label="Actual")
    sk = week.forecast_skill["net_load"]
    ax.set_title(f"Day-ahead quantile forecast of feeder net load  ·  coverage {sk['coverage_q10_q90_pct']:.0f}% "
                 f"(nominal 80%)  ·  MAPE {sk['mape_q50_pct']:.1f}%")
    ax.set_ylabel("kW")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %H:%M"))
    ax.legend(loc="upper left", ncol=3)
    ax.set_ylim(0, fl.net_load[s].max() * 1.25)
    _sim_tag(fig)
    return _save(fig, out / "forecast_quantiles.png")


def fairness_hist(week, out: Path) -> Path:
    _style()
    res = week.feeder["gridsetu"]
    base_out = week.feeder["baseline"].metrics["feeder_outage_hours"]
    gs_out = res.metrics["feeder_outage_hours"]
    hours = res.extra.get("household_hours", np.zeros(week.feeder_loads.hh_load.shape[0]))
    fig, ax = plt.subplots(figsize=(11, 4.8))
    top = max(hours.max(), base_out) + 0.75
    ax.hist(hours, bins=np.arange(0, top, 0.25), color=TEAL, edgecolor="white", linewidth=1.5,
            label="GridSetu: Tier-3 appliance curtailment per household")
    ymax = ax.get_ylim()[1] * 1.4
    ax.set_ylim(0, ymax)
    for x, txt in ((base_out, f"Baseline: whole feeder dark {base_out:.1f} h\n(critical loads included)"),
                   (gs_out, f"GridSetu: whole feeder dark {gs_out:.1f} h\n(critical loads kept on)")):
        ax.axvline(x, color=INK, lw=1.4, ls=(0, (4, 3)))
        left = x != base_out
        ax.text(x - 0.05 if left else x + 0.05, ymax * 0.95, txt, color=INK, fontsize=9.5, va="top",
                ha="right" if left else "left",
                bbox=dict(facecolor="white", edgecolor="none", pad=1.5))
    fs = res.fairness
    ax.set_title(f"Who carries the curtailment? {week.label}, Gini {fs['gini_curtailment_hours']:.2f}", loc="left")
    ax.set_xlim(0, top + 1.2)
    ax.set_xlabel("hours per household in the week")
    ax.set_ylabel("households")
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.15))
    _sim_tag(fig)
    return _save(fig, out / "fairness_ledger.png")


def wams_plot(wams: dict, out: Path) -> Path:
    _style()
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    for ax, case, title in ((axes[0], "A", "Case A: G1B trips, tie picks up, SPS acts"),
                            (axes[1], "B", "Case B: national tie trips, city islands, UFLS")):
        for variant, color in (("baseline", GREY), ("gridsetu", TEAL)):
            r = wams["runs"][f"{case}_{variant}"]
            ts = r["ts"]
            ax.plot(ts.t_s, ts.f_city_hz, color=color, lw=1.8,
                    label=f"{variant.replace('gridsetu', 'GridSetu').replace('baseline', 'Baseline')}"
                          f"  nadir {r['summary']['nadir_hz']:.2f} Hz")
        if case == "B":
            for st in (49.4, 49.2, 49.0):
                ax.axhline(st, color=MUTED, lw=0.8, ls=":")
                ax.text(29.5, st + 0.01, f"UFLS {st} Hz", ha="right", fontsize=8, color=MUTED)
        ax.set_xlim(0, 30)
        ax.set_title(title, loc="left", fontsize=12)
        ax.set_xlabel("seconds after event (PMU, 50 frames/s)")
        ax.set_ylabel("city frequency, Hz")
        ax.legend(loc="lower right" if case == "A" else "upper right")
    fig.tight_layout()
    _sim_tag(fig)
    return _save(fig, out / "wams_frequency_event.png")


def island_plot(island: dict, out: Path) -> Path:
    _style()
    keys = [("unserved_kwh", "Unserved energy, kWh"), ("diesel_run_hours", "Diesel run hours"),
            ("pv_curtailed_kwh", "Solar wasted, kWh"), ("diesel_litres", "Diesel, litres")]
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.8))
    for ax, (k, t) in zip(axes, keys):
        v = [island["legacy"][k], island["gridsetu"][k]]
        bars = ax.bar(["Legacy", "GridSetu"], v, color=[GREY, TEAL], width=0.55)
        for bar, x in zip(bars, v):
            ax.text(bar.get_x() + bar.get_width() / 2, x, f"{x:,.0f}", ha="center", va="bottom",
                    color=INK, fontweight="bold")
        ax.set_title(t, loc="left", fontsize=11)
        ax.set_ylim(0, max(v) * 1.25 if max(v) else 1)
        ax.grid(axis="x", visible=False)
    fig.suptitle("Isolated microgrid (no grid connection), one week", x=0.01, ha="left",
                 fontweight="bold", color=INK)
    fig.tight_layout(rect=(0, 0.03, 1, 0.93))
    _sim_tag(fig)
    return _save(fig, out / "island_microgrid.png")


def security_plot(pf, out: Path) -> Path:
    _style()
    fig, ax = plt.subplots(figsize=(13, 4.2))
    cols = [c for c in pf.columns if c.startswith("loading_") and c != "loading_NAT-R1_pct"]
    for i, c in enumerate(cols + ["loading_NAT-R1_pct"]):
        ax.plot(pf.index, pf[c], color=CAT[i], lw=1.5, label=c.replace("loading_", "").replace("_pct", ""))
    ax.axhline(100, color=INK, lw=1, ls=(0, (4, 3)))
    ax.text(pf.index[1], 102, "thermal limit", fontsize=9, color=INK)
    ax.set_ylabel("line loading, % of thermal rating")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %d"))
    ax.set_title("AC power-flow security check of the 220 kV network (pandapower)")
    ax.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0))
    _sim_tag(fig)
    return _save(fig, out / "network_security.png")
