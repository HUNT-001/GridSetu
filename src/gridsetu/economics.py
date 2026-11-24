"""Rupee business case for the pilot feeder, priced with real IEX day-ahead prices.

    python -m gridsetu economics            # writes outputs/economics/

Costs (annual):
  battery        the 2025 Indian benchmark tariff for 2-hour standalone storage, INR 2.3 lakh per
                 MW per month (IEEFA-JMK, 2026), which already covers capital, O&M and return,
                 times a community-scale premium (default 2x: a 100 kW unit costs more per MW
                 than a 250 MW tender)
  smart plugs    Tier-3 relays for every home, spread over their life
  controller     edge controller, comms and the platform

Benefits (annual, GridSetu minus baseline):
  reliability    unserved energy avoided (lifeline and curtailment count as unserved)
  energy cost    change in what the DISCOM pays for the feeder's energy at IEX prices: more
                 energy is served, but the battery buys it at midday

Instead of assuming a value of lost load, the study reports the BREAK-EVEN value: what each kWh
of avoided outage must be worth for GridSetu to pay for itself. Reference points: the IEX price
ceiling (INR 10/kWh, what the market pays for scarce power) and diesel backup (INR 99.55/L in
Chennai, Nov 2026, at about 3 kWh per litre).

Annualisation: the headline "month" is 3 normal + 1 stress week, i.e. 13 stress weeks a year.
A sensitivity uses 4 (stress only in the hottest month).
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config import load_scenario
from .plots import AMBER, GREY, INK, MUTED, NAVY, TEAL, _save, _sim_tag, _style
from .realdata import iex_price_curve
from .simulate import stress_and_representative

LAKH = 1e5
ASSUMPTIONS = {
    "bess_benchmark_inr_per_mw_month": 2.3e5,     # IEEFA-JMK 2026: 2025 indicative benchmark, 2-hour BESS
    "bess_lowest_2025_inr_per_mw_month": 1.48e5,  # lowest 2025 discovered tariff, same source
    "community_scale_premium": 2.0,               # ASSUMPTION: small unit vs utility tender
    "smart_plug_inr_per_home": 1500.0,            # ASSUMPTION: Wi-Fi/4G relay plug, installed
    "smart_plug_life_years": 5.0,                 # ASSUMPTION
    "controller_comms_inr_per_year": 25000.0,     # ASSUMPTION: edge controller (5-yr life) + 4G + platform
    "stress_weeks_per_year": 13,                  # matches the headline month (3 normal + 1 stress)
    "diesel_inr_per_litre": 99.55,                # Chennai, 17 Nov 2026 (DT Next)
    "genset_kwh_per_litre": 3.0,                  # ASSUMPTION: small diesel generator
    "iex_ceiling_inr_per_kwh": 10.0,              # IEX day-ahead price ceiling
}
SOURCES = {
    "bess_benchmark": "https://www.ess-news.com/2026/05/19/india-awards-10-4-gw-of-standalone-bess-capacity-in-2025-but-tariff-viability-remains-a-concern/",
    "diesel": "https://www.dtnext.in/news/chennai/check-out-petrol-and-diesel-prices-in-chennai-on-november-17-2026",
    "iex": "data/real/iex_dam_2025-09-14_20.csv",
}


def _week_numbers(week, price: np.ndarray, dt: float) -> dict:
    out = {}
    for v in ("baseline", "gridsetu"):
        f = week.feeder[v]
        imp = f.ts["import"].to_numpy()
        out[v] = {"unserved_kwh": float(f.metrics["total_unserved_kwh"]),
                  "import_kwh": float(imp.sum() * dt),
                  "energy_cost_inr": float((imp * price).sum() * dt * 1000 / 1000),   # price is INR/kWh
                  "battery_discharge_kwh": float(f.metrics["battery_discharge_kwh"])}
    return out


def simulate(seeds: int = 3, config_path=None) -> dict:
    """Weekly energy and cost for baseline and GridSetu, stress and normal weeks, at IEX prices."""
    weeks = {"stress": [], "representative": []}
    for i in range(seeds):
        seed = 42 + 100 * i
        res = stress_and_representative(config_path, {"simulation": {"seed": seed}}, verbose=False)
        sc = load_scenario(config_path, {"simulation": {"seed": seed}})
        price = iex_price_curve(sc.index)
        for wk in weeks:
            weeks[wk].append(_week_numbers(res[wk], price, sc.dt_h))
    mean = {wk: {v: {k: float(np.mean([w[v][k] for w in ws])) for k in ws[0][v]} for v in ("baseline", "gridsetu")}
            for wk, ws in weeks.items()}
    return {"per_seed": weeks, "mean": mean}


def annual(weekly: dict, a: dict) -> dict:
    ns = a["stress_weeks_per_year"]
    nn = 52 - ns

    def yr(v, k):
        return ns * weekly["stress"][v][k] + nn * weekly["representative"][v][k]

    d_unserved = yr("baseline", "unserved_kwh") - yr("gridsetu", "unserved_kwh")
    d_energy_cost = yr("gridsetu", "energy_cost_inr") - yr("baseline", "energy_cost_inr")
    avg_price = {v: yr(v, "energy_cost_inr") / yr(v, "import_kwh") for v in ("baseline", "gridsetu")}
    cost = {
        "battery": a["bess_benchmark_inr_per_mw_month"] * 0.1 * 12 * a["community_scale_premium"],
        "smart_plugs": 420 * a["smart_plug_inr_per_home"] / a["smart_plug_life_years"],
        "controller_comms": a["controller_comms_inr_per_year"],
    }
    total_cost = sum(cost.values())
    diesel = a["diesel_inr_per_litre"] / a["genset_kwh_per_litre"]
    breakeven = (total_cost + d_energy_cost) / d_unserved if d_unserved > 0 else float("inf")
    ref = {}
    for name, voll in (("iex_ceiling", a["iex_ceiling_inr_per_kwh"]), ("diesel_backup", diesel)):
        benefit = d_unserved * voll
        ref[name] = {"value_inr_per_kwh": round(voll, 2),
                     "reliability_value_inr": round(benefit),
                     "net_inr_per_year": round(benefit - d_energy_cost - total_cost),
                     "benefit_cost_ratio": round(benefit / (total_cost + d_energy_cost), 2)}
    return {
        "unserved_avoided_kwh_per_year": round(d_unserved),
        "extra_energy_cost_inr_per_year": round(d_energy_cost),
        "avg_purchase_price_inr_per_kwh": {k: round(v, 2) for k, v in avg_price.items()},
        "costs_inr_per_year": {k: round(v) for k, v in cost.items()},
        "total_cost_inr_per_year": round(total_cost),
        "cost_per_home_per_month_inr": round(total_cost / 420 / 12, 1),
        "breakeven_value_inr_per_kwh": round(breakeven, 2),
        "at_reference_values": ref,
    }


def sensitivity(weekly: dict, a: dict) -> list[dict]:
    """Break-even value of a kWh of avoided outage when one assumption moves."""
    base = annual(weekly, a)["breakeven_value_inr_per_kwh"]
    cases = [
        ("Community-scale battery premium", "community_scale_premium", 1.0, 3.0, "1x (utility price)", "3x"),
        ("Battery tariff", "bess_benchmark_inr_per_mw_month", a["bess_lowest_2025_inr_per_mw_month"], 3.0e5,
         "₹1.48 lakh (lowest 2025 bid)", "₹3.0 lakh"),
        ("Stress weeks per year", "stress_weeks_per_year", 26, 4, "26", "4"),
        ("Smart plug cost per home", "smart_plug_inr_per_home", 750.0, 3000.0, "₹750", "₹3,000"),
    ]
    out = []
    for label, key, lo, hi, lo_txt, hi_txt in cases:
        b_lo = annual(weekly, {**a, key: lo})["breakeven_value_inr_per_kwh"]
        b_hi = annual(weekly, {**a, key: hi})["breakeven_value_inr_per_kwh"]
        out.append({"assumption": label, "low_setting": lo_txt, "high_setting": hi_txt,
                    "breakeven_low": b_lo, "breakeven_high": b_hi, "base": base})
    return out


def _charts(out: Path, res: dict) -> None:
    _style()
    (out / "charts").mkdir(parents=True, exist_ok=True)
    yr = res["annual"]
    # 1. annual cost vs reliability value at the two reference values
    fig, ax = plt.subplots(figsize=(11, 5.2))
    c = yr["costs_inr_per_year"]
    parts = [("Battery (benchmark tariff × premium)", c["battery"], NAVY),
             ("Smart plugs", c["smart_plugs"], GREY),
             ("Controller and comms", c["controller_comms"], MUTED),
             ("Extra energy bought at IEX prices", max(yr["extra_energy_cost_inr_per_year"], 0), AMBER)]
    left = 0
    for name, val, col in parts:
        ax.barh(2, val / LAKH, left=left, color=col, height=0.55, label=name)
        left += val / LAKH
    ref = yr["at_reference_values"]
    ax.barh(1, ref["iex_ceiling"]["reliability_value_inr"] / LAKH, color=TEAL, alpha=0.55, height=0.55)
    ax.barh(0, ref["diesel_backup"]["reliability_value_inr"] / LAKH, color=TEAL, height=0.55)
    ax.set_yticks([2, 1, 0], ["What it costs", f"Outages avoided\nat ₹{ref['iex_ceiling']['value_inr_per_kwh']:.0f}/kWh (IEX ceiling)",
                              f"Outages avoided\nat ₹{ref['diesel_backup']['value_inr_per_kwh']:.0f}/kWh (diesel backup)"])
    ax.set_xlabel("₹ lakh per year, one feeder (420 homes)")
    ax.set_title(f"GridSetu pays for itself if an avoided outage is worth more than "
                 f"₹{yr['breakeven_value_inr_per_kwh']:.1f} per kWh", loc="left")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=4, frameon=False, fontsize=9)
    fig.subplots_adjust(bottom=0.3)
    _sim_tag(fig, "Simulation priced with real IEX day-ahead prices (14–20 Sep 2025) · battery cost: 2025 Indian benchmark tariff")
    _save(fig, out / "charts" / "business_case.png")

    # 2. tornado on the break-even value
    sens = res["sensitivity"]
    fig, ax = plt.subplots(figsize=(11, 4.6))
    base = sens[0]["base"]
    for i, s in enumerate(sens):
        lo, hi = sorted((s["breakeven_low"], s["breakeven_high"]))
        ax.barh(i, hi - lo, left=lo, color=TEAL, height=0.5)
        ax.text(s["breakeven_low"], i + 0.32, s["low_setting"], ha="center", fontsize=8, color=MUTED)
        ax.text(s["breakeven_high"], i + 0.32, s["high_setting"], ha="center", fontsize=8, color=MUTED)
    ax.axvline(base, color=INK, lw=1.2)
    diesel = ASSUMPTIONS["diesel_inr_per_litre"] / ASSUMPTIONS["genset_kwh_per_litre"]
    for x, name in ((ASSUMPTIONS["iex_ceiling_inr_per_kwh"], "IEX ceiling ₹10"), (diesel, f"diesel backup ₹{diesel:.0f}")):
        ax.axvline(x, color=AMBER, lw=1.2, ls="--")
        ax.text(x, -0.75, f" {name}", color=AMBER, fontsize=9, va="center")
    ax.set_ylim(-1.0, len(sens) - 0.3)
    ax.set_yticks(range(len(sens)), [s["assumption"] for s in sens])
    ax.set_xlabel("Break-even value of a kWh of avoided outage (₹)")
    ax.set_title(f"What moves the break-even (base ₹{base:.1f}/kWh)", loc="left")
    ax.set_xlim(0, diesel * 1.08)
    _sim_tag(fig, "Simulation · one assumption moved at a time")
    _save(fig, out / "charts" / "business_case_sensitivity.png")


def run_study(out_dir: str | Path = "outputs/economics", config_path=None, seeds: int = 3) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sim = simulate(seeds, config_path)
    res = {"about": {"label": "SIMULATION priced with real IEX prices; costs from the 2025 Indian BESS benchmark",
                     "seeds": seeds, "assumptions": ASSUMPTIONS, "sources": SOURCES},
           "weekly_mean": sim["mean"],
           "annual": annual(sim["mean"], ASSUMPTIONS),
           "sensitivity": sensitivity(sim["mean"], ASSUMPTIONS)}
    (out / "economics.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    _charts(out, res)
    return res
