"""City-wide fleet study (Phase 2): GridSetu on many feeders, not just F07.

R3 South Peri-urban & Agri has 20 domestic feeder groups that the DISCOM rotates through
when it has to shed. Each group here is one 11 kV feeder with its own number of homes,
transformer rating, rooftop solar and critical loads (group 7 is the pilot F07). Every
feeder is simulated under the baseline and under GridSetu against the same city signals,
so any mix of adopters can be evaluated: a feeder's outcome depends only on its own
controller, because DISCOM requests are a share of each feeder's own load (no feeder can
push its burden onto a neighbour; see the 95 % relief rule in feeder.py).

Forecasts reuse the pilot's trained quantile model on per-unit profiles: each feeder's net
load is scaled to the pilot's size, forecast, and scaled back."""
from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass

import numpy as np

from .feeder import rotation_schedule, simulate_feeder
from .forecast import QuantileForecast
from .profiles import feeder_loads

ADOPTION_LEVELS = (0, 0.25, 0.5, 0.75, 1.0)


@dataclass
class FleetFeeder:
    group: int
    id: str
    households: int
    peak_kw: float
    rating_kw: float
    rooftop_kwp: float
    community_kwp: float
    critical: dict
    sps_member: bool
    battery_kw: float
    battery_kwh: float
    is_pilot: bool = False
    rank: int = 0


def define_fleet(sc) -> list[FleetFeeder]:
    reg = sc.regions["R3"]
    n = int(reg["domestic_feeder_groups"])
    pilot = int(reg["pilot_feeder_group"])
    f = sc.feeder
    rng = np.random.default_rng(sc.rng_seed + 20260)
    out = []
    for g in range(n):
        if g == pilot:
            ff = FleetFeeder(g, "F07", int(f["households"]), float(f["target_peak_kw"]), float(f["capacity_kw"]),
                             float(f["rooftop_solar_kwp"]), float(f["community_solar_kwp"]),
                             dict(f["critical_loads_kw"]), True, float(f["battery"]["power_kw"]),
                             float(f["battery"]["energy_kwh"]), True)
        else:
            hh = int(rng.integers(260, 600))
            peak = round(hh * f["target_peak_kw"] / f["households"] * rng.uniform(0.9, 1.1), 1)
            rating = float(max(100, 25 * round(peak * rng.uniform(0.84, 1.05) / 25)))
            scale = hh / f["households"]
            crit = {"health_subcentre": f["critical_loads_kw"]["health_subcentre"] * scale if rng.random() < 0.4 else 0.0,
                    "school": f["critical_loads_kw"]["school"] * scale if rng.random() < 0.6 else 0.0,
                    "water_pumping": f["critical_loads_kw"]["water_pumping"] * scale,
                    "street_lighting_core": f["critical_loads_kw"]["street_lighting_core"] * scale}
            bkw = float(max(20, 10 * round(peak * sc.raw["coordination"]["gridsetu_battery_kw_per_feeder_peak_kw"] / 10)))
            ff = FleetFeeder(g, f"F{g:02d}", hh, peak, rating, round(hh * rng.uniform(0.08, 0.3), 0),
                             round(0.18 * peak / 5) * 5, crit, g % 4 == pilot % 4, bkw,
                             bkw * sc.raw["coordination"]["gridsetu_battery_hours"])
        out.append(ff)
    # the planner rolls GridSetu out where it helps most: overloaded transformers first,
    # then feeders with a clinic or school, then size
    order = sorted(out, key=lambda x: (-(x.peak_kw / x.rating_kw > 1.0), -(x.critical["health_subcentre"] > 0),
                                       -(x.critical["school"] > 0), -x.peak_kw / x.rating_kw, -x.households))
    for i, x in enumerate(order):
        x.rank = i
    return out


def _feeder_scenario(sc, ff: FleetFeeder):
    s = copy.copy(sc)
    raw = copy.deepcopy(sc.raw)
    p = raw["pilot_feeder"]
    p.update(households=ff.households, micro_enterprises=max(5, ff.households // 12), target_peak_kw=ff.peak_kw,
             capacity_kw=ff.rating_kw, rooftop_solar_kwp=ff.rooftop_kwp, community_solar_kwp=ff.community_kwp,
             critical_loads_kw={k: max(v, 1e-6) for k, v in ff.critical.items()})
    p["battery"] = {**p["battery"], "power_kw": ff.battery_kw, "energy_kwh": ff.battery_kwh}
    s.raw = raw
    s.rng_seed = sc.rng_seed + 7717 * (ff.group + 1)
    return s


class _Scaled:
    """Just enough of FeederLoads for the forecaster: net load scaled to pilot size."""
    def __init__(self, fl, k):
        self.index, self.weather = fl.index, fl.weather
        self.net_load = fl.net_load * k
        self.community_pv = fl.community_pv


def _forecast(week, fl, ff: FleetFeeder, pilot_peak: float, pilot_comm: float) -> dict:
    k = pilot_peak / ff.peak_kw
    raw = week.model.predict(_Scaled(fl, k), last_history=_ScaledHist(week.history_last, 1.0))
    net = QuantileForecast(*(q / k for q in (raw["net_load"].q10, raw["net_load"].q50, raw["net_load"].q90)))
    ratio = ff.community_kwp / pilot_comm if pilot_comm else 0.0
    pv = QuantileForecast(*(q * ratio for q in (raw["community_pv"].q10, raw["community_pv"].q50,
                                                   raw["community_pv"].q90)))
    return {"net_load": net, "community_pv": pv}


class _ScaledHist:
    def __init__(self, h, k):
        self.net_load = h.net_load * k


def run_fleet(week) -> dict:
    """Simulate every feeder in R3 under baseline and GridSetu for one week."""
    sc = week.sc
    fleet = define_fleet(sc)
    sig0 = week.signals["baseline"]
    n_groups = len(fleet)
    draws_base = sc.rng(31337)
    pilot_peak, pilot_comm = sc.feeder["target_peak_kw"], sc.feeder["community_solar_kwp"]
    feeders = []
    for ff in fleet:
        if ff.is_pilot:
            fl, fc = week.feeder_loads, week.forecast
            res = {"baseline": week.feeder["baseline"], "gridsetu": week.feeder["gridsetu"]}
            fsc = sc
        else:
            fsc = _feeder_scenario(sc, ff)
            fl, _ = feeder_loads(fsc, week.weather, seed=fsc.rng_seed + 5)
            fc = _forecast(week, fl, ff, pilot_peak, pilot_comm)
            sig = dataclasses.replace(
                sig0, rotation_trip=rotation_schedule(sig0.shed_frac_rt, n_groups, ff.group),
                sps_trip=sig0.sps_trip if ff.sps_member else np.zeros_like(sig0.sps_trip))
            draws = np.random.default_rng(int(draws_base.integers(1 << 31))).random(sc.n_steps)
            res = {m: simulate_feeder(fsc, fl, fc, sig, m, draws) for m in ("baseline", "gridsetu")}
        feeders.append((ff, fl, res))
    return summarise(sc, feeders)


def _dark(ts):
    st = ts["state"].astype(str)
    return (st.str.contains("trip") & (st != "overload_event")).values


def summarise(sc, feeders) -> dict:
    dt = sc.dt_h
    rows, series = [], {}
    for ff, fl, res in feeders:
        row = dataclasses.asdict(ff)
        for m, r in res.items():
            met = r.metrics
            dark = _dark(r.ts)
            row[m] = {"critical_outage_hours": met["critical_outage_hours"], "feeder_outage_hours": met["feeder_outage_hours"],
                      "total_unserved_kwh": met["total_unserved_kwh"], "evening_unserved_kwh": met["evening_window_unserved_kwh"],
                      "overload_trips": met["overload_trips"], "peak_import_kw": met["feeder_peak_import_kw"],
                      "household_dark_hours": float(dark.sum() * dt * ff.households),
                      "critical_sites": int(sum(v > 0.01 for v in ff.critical.values()))}
            series[(ff.group, m)] = {"import": r.ts["import"].values, "state": r.ts["state"].astype(str).values,
                                     "dark": dark, "tier1_unserved": r.ts["tier1_unserved"].values}
        rows.append(row)
    rows.sort(key=lambda r: r["group"])
    # adoption curve: GridSetu on the top-ranked k feeders, baseline elsewhere
    curve = []
    n = len(rows)
    for lvl in ADOPTION_LEVELS:
        k = int(round(lvl * n))
        adopted = {r["group"] for r in rows if r["rank"] < k}
        pick = lambda r: "gridsetu" if r["group"] in adopted else "baseline"  # noqa: E731
        agg = {key: float(sum(r[pick(r)][key] for r in rows)) for key in
               ("critical_outage_hours", "feeder_outage_hours", "total_unserved_kwh", "evening_unserved_kwh",
                "overload_trips", "household_dark_hours")}
        head = sum(series[(r["group"], pick(r))]["import"] for r in rows)
        crit_site_hours = sum((series[(r["group"], pick(r))]["tier1_unserved"] > 0.01).sum() * dt * r[pick(r)]["critical_sites"]
                              for r in rows)
        curve.append({"adoption": lvl, "feeders": k, **agg, "critical_site_hours": float(crit_site_hours),
                      "r3_feeder_head_peak_kw": float(head.max()),
                      "batteries_kwh": float(sum(r["battery_kwh"] for r in rows if r["group"] in adopted))})
    return {"feeders": rows, "curve": curve, "series": series,
            "note": "Feeders do not interact: DISCOM requests are a share of each feeder's own load."}
