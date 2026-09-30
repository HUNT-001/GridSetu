"""Tools the operator copilot can call. Each tool reads the same cached run payloads the
dashboard shows (or starts a real simulator run), returns compact JSON for the model, and
may return `ui` actions (seek the playhead, open a page, switch run) that the dashboard
applies. Tools never invent numbers: if data is missing they say so."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..api.engine import knobs_to_overrides, load_scenario_defaults
from .data import RunData

PAGES = {"control room": "/", "overview": "/", "city": "/city", "market": "/city", "feeder": "/feeder",
         "households": "/households", "fairness": "/households", "protection": "/wams", "wams": "/wams",
         "architecture": "/architecture", "lab": "/lab", "scenario lab": "/lab"}


@dataclass
class Context:
    """What the operator is looking at, plus handles into the run store."""
    run_id: str
    reference_id: str
    lab_reference_id: str | None = None
    week: str = "stress"
    step: int = 0
    page: str = "/"
    open_run: Callable[[str], RunData] | None = None
    submit_run: Callable[[dict, str], Any] | None = None       # (overrides, label) -> RunRecord
    get_record: Callable[[str], Any] | None = None
    list_records: Callable[[], list] | None = None
    progress: Callable[[str], None] = lambda msg: None
    ui: list = field(default_factory=list)

    def data(self, run_id: str | None = None) -> RunData:
        return self.open_run(run_id or self.run_id)


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    fn: Callable[..., dict]
    label: Callable[[dict], str] = lambda a: "Working"


def _week(ctx: Context, w: str | None) -> str:
    if w in ("stress", "representative"):
        return w
    if w and w.lower().startswith(("normal", "rep")):
        return "representative"
    return ctx.week


def _r(x, nd=1):
    return None if x is None else round(float(x), nd)


# ------------------------------------------------------------------ tool bodies
def get_overview(ctx: Context, week: str | None = None) -> dict:
    d = ctx.data()
    s = d.summary
    wk = _week(ctx, week)
    keys = ["evening_window_unserved_kwh", "total_unserved_kwh", "critical_outage_hours", "feeder_outage_hours",
            "feeder_peak_import_kw", "overload_trips", "battery_cycles", "tier3_curtailed_kwh"]
    month = {v: {k: _r(s["monthly"][v][k]["mean"]) for k in keys if k in s["monthly"][v]} for v in s["monthly"]}
    weekly = {v: {k: _r(s["weekly"][wk][v].get(k)) for k in keys} for v in s["weekly"][wk]}
    city = {sc: {k: _r(v) if isinstance(v, (int, float)) else v for k, v in s["city"][wk][sc].items()
                 if k in ("energy_not_served_mwh", "shedding_hours", "scarcity_hours", "renewable_share_pct",
                          "industrial_dr_mwh", "ens_by_class_mwh")} for sc in s["city"][wk]}
    rec = ctx.get_record(ctx.run_id) if ctx.get_record else None
    return {"run": {"id": ctx.run_id, "label": getattr(rec, "label", None), "seeds": d.meta["seeds"]},
            "definition": "month = 3 normal weeks + 1 stress week; baseline vs GridSetu on the pilot feeder F07 (420 homes)",
            "monthly_pilot_feeder": month, f"{wk}_week_pilot_feeder": weekly, f"{wk}_week_city": city,
            "fairness_stress_week": s["fairness"], "forecast_skill_stress_week": s["forecast_skill"]["net_load"],
            "note": "All figures are simulation on synthetic data."}


def get_moment(ctx: Context, time: str | int | None = None, week: str | None = None,
               scenario: str = "baseline") -> dict:
    d = ctx.data()
    wk = _week(ctx, week)
    step = d.parse_time(time, wk, default=ctx.step)
    ev = [e for e in d.city(wk)["scenarios"][scenario]["events"] if abs(e["step"] - step) <= 8]
    ctx.ui.append({"type": "seek", "week": wk, "step": step})
    return {"city": d.city_at(wk, step, scenario), "pilot_feeder": d.feeder_at(wk, step),
            "events_within_2h": [{"time": d.when(wk, e["step"]), "what": e["label"]} for e in ev]}


def list_events(ctx: Context, week: str | None = None, include_feeder: bool = True) -> dict:
    d = ctx.data()
    wk = _week(ctx, week)
    city = [{"time": d.when(wk, e["step"]), "step": e["step"], "kind": e["kind"], "what": e["label"]}
            for e in d.city(wk)["scenarios"]["baseline"]["events"]]
    out = {"week": wk, "city_events": city[:40]}
    if include_feeder:
        for v in ("baseline", "gridsetu"):
            out[f"pilot_feeder_{v}_episodes"] = d.feeder_episodes(wk, v)[:30]
    out["outages_configured"] = d.meta["weeks"][wk]["outages"]
    return out


def explain_price(ctx: Context, time: str | int | None = None, region: str = "R3", week: str | None = None,
                  scenario: str = "baseline") -> dict:
    d = ctx.data()
    wk = _week(ctx, week)
    step = d.parse_time(time, wk, default=ctx.step)
    snap = d.city_at(wk, step, scenario)
    cap = d.meta["config"]["price_cap"]
    r = region.upper() if region else "R3"
    reg = snap["regions"].get(r) or next(iter(snap["regions"].values()))
    price = reg["price_rt_inr_kwh"]
    prices = [v["price_rt_inr_kwh"] for v in snap["regions"].values()]
    reasons = []
    at_max, marginal = [], []
    for g, v in snap["generation"].items():
        if v["kind"] in ("solar", "wind"):
            continue
        mc = snap["exchange_price_inr_kwh"] if v["kind"] == "import" else v.get("marginal_cost_inr_kwh")
        if v["mw"] >= v["pmax_mw"] - 0.5:
            at_max.append(g)
        elif v["mw"] > 0.5 and mc is not None and abs(mc - price) < 0.06:
            marginal.append(g)
    if price >= cap - 0.01:
        reasons.append(f"Price is at the ₹{cap:.0f}/kWh ceiling: supply is exhausted and load is being shed "
                       f"({snap['city_shed_mw']} MW city-wide). The shadow price is set by the value of the next "
                       "block of load to shed, capped by the exchange.")
    elif marginal:
        reasons.append(f"Set by the marginal unit(s) {', '.join(marginal)}: the cheapest resource still able to "
                       "move at this moment.")
    if max(prices) - min(prices) > 0.05:
        busy = [k for k, v in snap["interties"].items() if v["loading_pct"] >= 99]
        reasons.append(f"Regional prices differ (₹{min(prices):.2f} to ₹{max(prices):.2f}), so the market split: "
                       f"congested interties {', '.join(busy) or 'none at 100%'}.")
    else:
        reasons.append("All three regions share one price, so no intertie was congested.")
    if at_max:
        reasons.append(f"Units already at full output: {', '.join(at_max)}.")
    if snap["generation"]["S1"]["mw"] < 5 and snap["weather"]["clear_sky_index"] is not None:
        reasons.append("Solar is near zero (evening, night or heavy cloud), so the evening peak leans on thermal, "
                       "gas and the national import.")
    ctx.ui.append({"type": "seek", "week": wk, "step": step})
    return {"time": snap["time"], "region": r, "price_rt_inr_kwh": price, "regional_prices": {
        k: v["price_rt_inr_kwh"] for k, v in snap["regions"].items()}, "exchange_price_inr_kwh":
        snap["exchange_price_inr_kwh"], "reasons": reasons, "generation": snap["generation"],
        "interties": snap["interties"]}


def get_household(ctx: Context, household_id: str, week: str | None = None) -> dict:
    d = ctx.data()
    wk = _week(ctx, week)
    h = d.households(wk)
    ids = h["households"]["id"]
    hid = household_id.strip().upper()
    if hid.isdigit():
        hid = f"HH-{int(hid):03d}"
    if not hid.startswith("HH-") and hid[:2] == "HH":
        hid = "HH-" + hid[2:].lstrip("-").zfill(3)
    if hid not in ids:
        return {"error": f"No household {household_id}. Ids run HH-001 to HH-{len(ids):03d}."}
    i = ids.index(hid)
    x = h["households"]
    log = h["curtailment_log"]
    steps = [s for s, k in zip(log["step"], log["hh"]) if k == i]
    return {"id": hid, "week": wk, "feeder_section": x["node"][i], "peak_kw": x["peak_kw"][i],
            "energy_kwh": x["energy_kwh"][i], "tier3_paused_hours": x["curtailed_h"][i],
            "curtailment_events": x["events"][i], "dark_hours_baseline": x["dark_h_baseline"][i],
            "dark_hours_gridsetu": x["dark_h_gridsetu"][i],
            "paused_intervals": [d.when(wk, s) for s in steps][:24],
            "feeder_context": {"max_hours_any_home": h["fairness"].get("max_household_hours"),
                               "gini": h["fairness"].get("gini_curtailment_hours")}}


def get_reliability_reserve(ctx: Context, day: str | None = None, week: str | None = None) -> dict:
    d = ctx.data()
    wk = _week(ctx, week)
    step = d.parse_time(day or None, wk, default=ctx.step)
    reserves = d.feeder(wk)["variants"]["gridsetu"]["reserves"]
    date = d.when(wk, step)[:10]
    items = [r for r in reserves if _same_day(d, wk, r["window_start"], step)]
    return {"day": date, "window": "17:30 to 19:30", "stages": items,
            "note": "Confidence = probability the evening shortfall above the import target fits within the "
                    "battery energy (above the critical-load reserve) plus consented Tier-3 and Tier-2 load."}


def _same_day(d: RunData, wk: str, iso: str, step: int) -> bool:
    from datetime import datetime
    ws = datetime.fromisoformat(iso)
    return (ws - d.t0(wk)).days == step // 96


def get_planning_factors(ctx: Context) -> dict:
    s = ctx.data().summary
    return {"system": s["system_factors"], "load_classes_city": [
        {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}
        for r in s["class_factors"] if r["region"] == "CITY"],
        "plants": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()} for r in s["plant_factors"]],
        "definitions": {"load_factor": "average / maximum demand", "diversity_factor": "sum of individual maxima / group maximum",
                        "demand_factor": "maximum demand / connected load",
                        "capacity_factor": "energy / (capacity x period hours)",
                        "plant_use_factor": "energy / (capacity x hours actually running)"}}


def list_runs(ctx: Context) -> dict:
    recs = ctx.list_records() if ctx.list_records else []
    return {"reference": ctx.reference_id, "active": ctx.run_id,
            "runs": [{"id": r.id, "label": r.label, "status": r.status, "seeds": r.seeds, "knobs": r.knobs}
                     for r in recs]}


def _monthly(d: RunData, variant: str = "gridsetu") -> dict:
    keys = ["evening_window_unserved_kwh", "total_unserved_kwh", "critical_outage_hours", "feeder_outage_hours",
            "feeder_peak_import_kw", "overload_trips", "battery_cycles"]
    return {k: _r(d.summary["monthly"][variant][k]["mean"]) for k in keys}


def compare_runs(ctx: Context, run_id: str, other_run_id: str | None = None) -> dict:
    b = ctx.data(run_id)
    if not other_run_id:
        # compare like with like: a one-seed lab run against the one-seed reference
        other_run_id = ctx.lab_reference_id if (b.meta["seeds"] == 1 and ctx.lab_reference_id) else ctx.reference_id
    a = ctx.data(other_run_id)
    ma, mb = _monthly(a), _monthly(b)
    return {"a": {"id": a.run_id, "gridsetu_month": ma, "baseline_month": _monthly(a, "baseline")},
            "b": {"id": b.run_id, "gridsetu_month": mb},
            "change_pct_b_vs_a": {k: (None if not ma[k] else round(100 * (mb[k] - ma[k]) / ma[k], 1)) for k in ma},
            "caveat": f"Compared with {'the one-seed reference (same weather and loads)' if a.meta['seeds'] == b.meta['seeds'] else 'a run with a different seed count, so part of the difference is weather noise'}."}


def run_scenario(ctx: Context, label: str | None = None, battery_kwh: float | None = None,
                 battery_kw: float | None = None, capacity_kw: float | None = None,
                 tier1_island_hours: float | None = None, control_loss: float | None = None,
                 forced_outage: bool | None = None, irrigation_shift: bool | None = None,
                 industrial_dr_mw: float | None = None) -> dict:
    if not ctx.submit_run:
        return {"error": "Scenario runs need the local GridSetu API."}
    knobs = dict(load_scenario_defaults())
    given = {k: v for k, v in dict(battery_kwh=battery_kwh, battery_kw=battery_kw, capacity_kw=capacity_kw,
                                   tier1_island_hours=tier1_island_hours, control_loss=control_loss,
                                   forced_outage=forced_outage, irrigation_shift=irrigation_shift,
                                   industrial_dr_mw=industrial_dr_mw).items() if v is not None}
    bounds = {"battery_kwh": (25, 2000), "battery_kw": (10, 1000), "capacity_kw": (150, 800),
              "tier1_island_hours": (0, 8), "control_loss": (0, 0.95), "industrial_dr_mw": (0, 100)}
    for k, (lo, hi) in bounds.items():
        if k in given and not lo <= float(given[k]) <= hi:
            return {"error": f"{k}={given[k]} is outside the allowed range {lo} to {hi}."}
    knobs.update(given)
    if not given:
        return {"error": "Name at least one setting to change, for example battery_kwh=400."}
    name = (label or ", ".join(f"{k}={v}" for k, v in given.items()))[:60]
    if ctx.lab_reference_id and ctx.get_record and not getattr(ctx.get_record(ctx.lab_reference_id), "status", None):
        ctx.submit_run({}, "Reference, 1 seed (lab baseline)", load_scenario_defaults())
    rec = ctx.submit_run(knobs_to_overrides(knobs), f"Copilot: {name}", knobs)
    t0 = time.time()
    last = ""
    while rec.status not in ("ready", "failed") and time.time() - t0 < 240:
        if rec.message != last:
            last = rec.message
            ctx.progress(f"{int(rec.progress * 100)}% · {rec.message}")
        time.sleep(0.5)
    if rec.status != "ready":
        return {"error": f"The run did not finish: {rec.error or rec.status}", "run_id": rec.id}
    ref = ctx.get_record(ctx.lab_reference_id) if (ctx.get_record and ctx.lab_reference_id) else None
    while ref is not None and ref.status not in ("ready", "failed") and time.time() - t0 < 300:
        ctx.progress("Finishing the one-seed reference for a fair comparison")
        time.sleep(0.5)
    ctx.ui.append({"type": "offer_run", "run_id": rec.id, "label": rec.label})
    return {"run_id": rec.id, "label": rec.label, "changed": given, "runtime_s": round(time.time() - t0),
            **compare_runs(ctx, rec.id)}


def show_in_dashboard(ctx: Context, page: str | None = None, time: str | int | None = None,
                      week: str | None = None) -> dict:
    wk = _week(ctx, week)
    done = []
    if week:
        ctx.ui.append({"type": "week", "week": wk})
        done.append(f"week={wk}")
    if page:
        path = PAGES.get(page.lower().strip(), page if page.startswith("/") else None)
        if not path:
            return {"error": f"Unknown page {page}. Pages: {', '.join(sorted(set(PAGES)))}"}
        ctx.ui.append({"type": "navigate", "path": path})
        done.append(f"page={path}")
    if time is not None and time != "":
        step = ctx.data().parse_time(time, wk, default=ctx.step)
        ctx.ui.append({"type": "seek", "week": wk, "step": step})
        done.append(f"time={ctx.data().when(wk, step)}")
    return {"done": done or ["nothing to change"]}


# ------------------------------------------------------------------ registry
def _s(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


WEEK = {"type": "string", "enum": ["stress", "representative"],
        "description": "stress = forced coal outage + two overcast days; representative = normal week. Defaults to what the operator is viewing."}
TIME = {"type": "string", "description": "e.g. 'Thu 18:00', '18:00', 'Friday evening'. Defaults to the dashboard playhead."}

TOOLS: list[Tool] = [
    Tool("get_overview", "Headline results of the active run: monthly and weekly pilot-feeder metrics (baseline vs GridSetu), city energy not served, fairness and forecast skill.",
         _s({"week": WEEK}), get_overview, lambda a: "Reading the run summary"),
    Tool("get_moment", "Full state at one 15-minute interval: city demand, shedding by region and class, prices, generation by unit, intertie loading, weather, and the pilot feeder under baseline and GridSetu. Also moves the dashboard playhead there.",
         _s({"time": TIME, "week": WEEK, "scenario": {"type": "string", "enum": ["baseline", "coordinated"]}}),
         get_moment, lambda a: f"Looking at {a.get('time') or 'the playhead'}"),
    Tool("list_events", "Timeline of the week: forced outages, load-shedding starts, price-ceiling hits, and feeder trip, cap and islanding episodes.",
         _s({"week": WEEK, "include_feeder": {"type": "boolean"}}), list_events, lambda a: "Listing the week's events"),
    Tool("explain_price", "Explain the real-time price in a region at a time: marginal unit, scarcity at the ceiling, congestion between regions, units at full output.",
         _s({"time": TIME, "region": {"type": "string", "enum": ["R1", "R2", "R3"]}, "week": WEEK,
             "scenario": {"type": "string", "enum": ["baseline", "coordinated"]}}),
         explain_price, lambda a: f"Tracing the price at {a.get('time') or 'the playhead'}"),
    Tool("get_household", "One home on feeder F07: consumption, Tier-3 hours paused, events, dark hours under both scenarios, and when it was paused.",
         _s({"household_id": {"type": "string", "description": "e.g. HH-042"}, "week": WEEK}, ["household_id"]),
         get_household, lambda a: f"Opening {a.get('household_id', 'a household')}"),
    Tool("get_reliability_reserve", "The Reliability Reserve GridSetu published for one day's 17:30 to 19:30 window at T-24h, T-1h, T-15min, real time and post-event.",
         _s({"day": {"type": "string", "description": "e.g. 'Thu'"}, "week": WEEK}),
         get_reliability_reserve, lambda a: f"Pulling the reserve for {a.get('day') or 'today'}"),
    Tool("get_planning_factors", "Load factor, diversity factor, demand factor per consumer class; capacity and plant use factor per plant; reserve margin and utilisation.",
         _s({}), get_planning_factors, lambda a: "Reading planning factors"),
    Tool("list_runs", "Scenario runs available (reference and lab runs) with their settings.", _s({}), list_runs,
         lambda a: "Listing runs"),
    Tool("compare_runs", "Compare GridSetu monthly metrics between two runs (default: against the reference run).",
         _s({"run_id": {"type": "string"}, "other_run_id": {"type": "string"}}, ["run_id"]),
         compare_runs, lambda a: "Comparing runs"),
    Tool("run_scenario", "Run the simulator with changed settings (about 30 to 60 s, one seed) and compare to the reference. Only pass the settings the operator asked to change.",
         _s({"label": {"type": "string"}, "battery_kwh": {"type": "number"}, "battery_kw": {"type": "number"},
             "capacity_kw": {"type": "number", "description": "distribution transformer rating"},
             "tier1_island_hours": {"type": "number"},
             "control_loss": {"type": "number", "description": "per-attempt packet loss on the 2G/4G control slice, 0 to 0.95"},
             "forced_outage": {"type": "boolean"}, "irrigation_shift": {"type": "boolean"},
             "industrial_dr_mw": {"type": "number"}}),
         run_scenario, lambda a: "Running the simulator"),
    Tool("show_in_dashboard", "Move the operator's dashboard: open a page, jump to a time, switch week.",
         _s({"page": {"type": "string", "description": "control room, city, feeder, households, protection, architecture, lab"},
             "time": TIME, "week": WEEK}), show_in_dashboard, lambda a: "Updating the dashboard"),
]
TOOL_MAP = {t.name: t for t in TOOLS}


def call_tool(ctx: Context, name: str, args: dict) -> dict:
    t = TOOL_MAP.get(name)
    if not t:
        return {"error": f"Unknown tool {name}"}
    try:
        return t.fn(ctx, **(args or {}))
    except (ValueError, KeyError) as e:
        return {"error": str(e).strip("'")}
    except TypeError as e:
        return {"error": f"Bad arguments for {name}: {e}"}
