"""Offline copilot: no language model. Recognises the common operator questions, calls the
same tools the model would, and writes the answer from templates. Less flexible than a
model, but every number still comes from the simulation and it needs no network."""
from __future__ import annotations

import re
from typing import Callable

from .tools import Context

HELP = """I'm running without a language model, so I understand a fixed set of requests:

- **What is happening now?** or **What happened at Thu 18:00?**
- **Why is the price high at Fri 19:00?**
- **What happened this week?**
- **How did GridSetu do?**
- **Show me HH-042**
- **Reliability reserve for Thursday**
- **Load factor and diversity factor**
- **What if the battery is 400 kWh?** (also transformer, packet loss, industrial DR, no outage)
- **Draft a note for the DISCOM**
- **Open the feeder page at Fri 18:30**

Set `ANTHROPIC_API_KEY` (or run Ollama) to ask anything in your own words."""

PAGE_WORDS = {"feeder": "feeder", "household": "households", "fairness": "households", "city": "city",
              "market": "city", "protection": "protection", "wams": "protection", "frequency": "protection",
              "architecture": "architecture", "layer": "architecture", "lab": "lab", "control room": "control room"}
TIME_RE = re.compile(r"\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*\b(\s+(at\s+)?(\d{1,2}([:.]\d{2})?\s*(am|pm)?|evening|morning|night|noon|midday))?"
                     r"|\b\d{1,2}[:.]\d{2}\s*(am|pm)?|\b\d{1,2}\s*(am|pm)\b|\bstep\s*\d+|\b(evening|morning|noon|night)\b",
                     re.I)


def f0(x):
    return "–" if x is None else f"{x:,.0f}"


def f1(x):
    return "–" if x is None else f"{x:,.1f}"


def pct_change(a, b):
    if not a:
        return "n/a"
    c = 100 * (b - a) / a
    return f"{'+' if c > 0 else '−' if c < 0 else ''}{abs(c):.0f}%"


class OfflineRouter:
    def __init__(self, call: Callable[[str, dict], dict], ctx: Context):
        self.call = call
        self.ctx = ctx

    def say(self, emit, text: str):
        for chunk in re.findall(r"\S+\s*|\n", text):
            emit({"type": "text", "delta": chunk})

    def time_of(self, q: str) -> str | None:
        m = TIME_RE.search(q)
        return m.group(0) if m else None

    def week_of(self, q: str) -> str | None:
        if re.search(r"\b(normal|representative|typical) week\b", q):
            return "representative"
        if re.search(r"\bstress week\b", q):
            return "stress"
        return None

    # ------------------------------------------------------------------ routing
    def answer(self, question: str, emit):
        q = question.lower().strip()
        wk = self.week_of(q)
        t = self.time_of(q)
        if not q or q in ("help", "?") or "what can you" in q:
            return self.say(emit, HELP)
        if re.search(r"\b(what if|simulate|run (a )?scenario|try|test)\b", q) or \
                (re.search(r"\b(battery|transformer|packet loss|loss|dr|outage)\b", q) and re.search(r"\d", q)
                 and re.search(r"\b(set|make|with|increase|reduce|change|double|halve)\b", q)):
            return self.scenario(q, emit)
        if re.search(r"\b(note|report|brief|email|letter)\b", q):
            return self.note(t, wk, emit)
        m = re.search(r"\bhh[- ]?(\d{1,3})\b|household\s+(\d{1,3})", q)
        if m:
            return self.household(m.group(1) or m.group(2), wk, emit)
        if re.search(r"\b(price|expensive|cost|mcp|₹|rupee|tariff)\b", q):
            return self.price(t, q, wk, emit)
        if "reserve" in q:
            return self.reserve(t, wk, emit)
        if re.search(r"load factor|diversity|demand factor|plant use|capacity factor|planning", q):
            return self.factors(emit)
        if re.search(r"\b(open|show|go to|take me|jump|switch)\b", q) and \
                (any(w in q for w in PAGE_WORDS) or t or wk):
            return self.navigate(q, t, wk, emit)
        if re.search(r"\b(events?|timeline|this week|what happened)\b", q) and not t:
            return self.events(wk, emit)
        if re.search(r"\b(how did|result|summary|overview|performance|impact|headline)\b", q):
            return self.overview(wk, emit)
        if t or re.search(r"\b(now|here|this moment|right now|happening|going on|state)\b", q):
            return self.moment(t, wk, emit)
        self.say(emit, "I didn't recognise that request.\n\n" + HELP)

    # ------------------------------------------------------------------ handlers
    def moment(self, t, wk, emit):
        if t and re.fullmatch(r"[a-z]+", t.strip().lower()) and t.strip().lower()[:3] in \
                ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
            t = f"{t} 18:00"   # a bare day: show its evening peak, where the stress is
        r = self.call("get_moment", {k: v for k, v in {"time": t, "week": wk}.items() if v})
        if "error" in r:
            return self.say(emit, r["error"])
        c, f = r["city"], r["pilot_feeder"]
        shed_regions = [f"{k} {v['shed_mw']:.0f} MW" for k, v in c["regions"].items() if v["shed_mw"] > 0.5]
        prices = {k: v["price_rt_inr_kwh"] for k, v in c["regions"].items()}
        gen = c["generation"]
        b, g = f["baseline"], f["gridsetu"]
        lines = [f"**{c['time']}** ({'stress' if c['week'] == 'stress' else 'normal'} week)\n",
                 f"- **City:** demand {f0(c['city_demand_mw'])} MW, "
                 + (f"**{f0(c['city_shed_mw'])} MW shed** ({', '.join(shed_regions)})." if shed_regions else "no load shedding."),
                 f"- **Prices:** " + ", ".join(f"{k} ₹{v:.2f}" for k, v in prices.items()) + " per kWh.",
                 f"- **Supply:** coal {f0(gen['G1A']['mw'] + gen['G1B']['mw'])} MW"
                 + (" (G1B out)" if gen["G1B"]["mw"] < 1 else "")
                 + f", gas {f0(gen['G2']['mw'])}, hydro {f0(gen['H1']['mw'])}, solar {f0(gen['S1']['mw'])}, "
                   f"wind {f0(gen['W1']['mw'])}, national import {f0(gen['IMP']['mw'])} MW.",
                 f"- **Pilot feeder, baseline:** {self._state(b['state'])}, {f0(b['import_kw'])} kW from the grid.",
                 f"- **Pilot feeder, GridSetu:** {self._state(g['state'])}, {f0(g['import_kw'])} kW from the grid, "
                 f"battery {f0(g['soc_pct'])}% ({self._bat(g['battery_kw'])}), "
                 f"{f0(g['homes_fully_supplied_pct'])}% of homes fully supplied"
                 + (f", {f0(g['tier3_paused_kw'])} kW of Tier-3 appliances paused" if (g['tier3_paused_kw'] or 0) > 0.5 else "")
                 + ".",
                 ]
        if (b["critical_load_unserved_kw"] or 0) > 0.01:
            lines.append(f"- The clinic, school, pump and street lights are **dark on the baseline** and "
                         f"{'on, islanded on the battery,' if (g['critical_load_unserved_kw'] or 0) < 0.01 else 'also dark'} under GridSetu.")
        if r["events_within_2h"]:
            lines.append("\nNearby events: " + "; ".join(f"{e['time']} {e['what']}" for e in r["events_within_2h"]) + ".")
        lines.append("\nI've moved the dashboard playhead here.")
        self.say(emit, "\n".join(lines))

    @staticmethod
    def _state(s):
        return {"normal": "normal", "cap": "meeting a DISCOM curtailment cap", "sps_relief": "giving fast relief to the protection scheme",
                "rotation_trip": "tripped by rotational shedding", "sps_trip": "tripped by the protection scheme",
                "local_trip": "out after a transformer overload trip", "overload_event": "overloaded and tripping"}.get(
            s, "tripped, critical loads islanded on the battery" if "island" in s else s.replace("_", " "))

    @staticmethod
    def _bat(kw):
        if kw is None or abs(kw) < 1:
            return "idle"
        return f"discharging {f0(kw)} kW" if kw > 0 else f"charging {f0(-kw)} kW"

    def price(self, t, q, wk, emit):
        reg = next((r.upper() for r in ("r1", "r2", "r3") if re.search(rf"\b{r}\b", q)), "R3")
        r = self.call("explain_price", {k: v for k, v in {"time": t, "week": wk, "region": reg}.items() if v})
        if "error" in r:
            return self.say(emit, r["error"])
        text = [f"**{r['region']} real-time price at {r['time']}: ₹{r['price_rt_inr_kwh']:.2f}/kWh** "
                f"(exchange reference ₹{r['exchange_price_inr_kwh']:.2f}).\n"]
        text += [f"- {x}" for x in r["reasons"]]
        self.say(emit, "\n".join(text))

    def events(self, wk, emit):
        r = self.call("list_events", {k: v for k, v in {"week": wk}.items() if v})
        ev = r["city_events"]
        lines = [f"**{'Stress' if r['week'] == 'stress' else 'Normal'} week timeline**\n"]
        if r["outages_configured"]:
            o = r["outages_configured"][0]
            lines.append(f"- Forced outage: {o['unit']} from {o['start']} to {o['end']}.")
        shed = [e for e in ev if e["kind"] == "shedding"]
        cap = [e for e in ev if e["kind"] == "scarcity"]
        if shed:
            lines.append(f"- Load shedding started {len(shed)} times: " + "; ".join(f"{e['time']} ({e['what'].split('(')[-1].rstrip(')')})" for e in shed[:6]) + ".")
        if cap:
            lines.append(f"- The day-ahead price hit the ₹10 ceiling {len(cap)} times, first {cap[0]['time']}.")
        be, ge = r["pilot_feeder_baseline_episodes"], r["pilot_feeder_gridsetu_episodes"]
        dark_b = sum(h for e in be for s, h in e["state_hours"].items() if "trip" in s and s != "overload_event")
        lines.append(f"- Pilot feeder, baseline: {len(be)} disturbed spells, about {f1(dark_b)} h dark.")
        isl = sum(h for e in ge for s, h in e["state_hours"].items() if "island" in s)
        cap = sum(h for e in ge for s, h in e["state_hours"].items() if s in ("cap", "sps_relief"))
        lines.append(f"- Pilot feeder, GridSetu: met DISCOM caps or gave fast relief for {f1(cap)} h; tripped with "
                     f"critical loads islanded on the battery for {f1(isl)} h.")
        if not shed and not cap and not be:
            lines.append("- A quiet week: no shedding, no price spikes, no feeder trips.")
        self.say(emit, "\n".join(lines))

    def overview(self, wk, emit):
        r = self.call("get_overview", {k: v for k, v in {"week": wk}.items() if v})
        b, g = r["monthly_pilot_feeder"]["baseline"], r["monthly_pilot_feeder"]["gridsetu"]
        rows = [("Unserved energy, 17:30 to 19:30", "evening_window_unserved_kwh", "kWh", f0),
                ("Critical-load outage", "critical_outage_hours", "h", f1),
                ("Whole feeder dark", "feeder_outage_hours", "h", f1),
                ("Transformer overload trips", "overload_trips", "", f0),
                ("Peak from the grid", "feeder_peak_import_kw", "kW", f0)]
        lines = ["**A month on feeder F07** (3 normal weeks + 1 stress week, simulation on synthetic data)\n",
                 "| Metric | Baseline | GridSetu | Change |", "|---|--:|--:|--:|"]
        for name, k, u, fmt in rows:
            lines.append(f"| {name} | {fmt(b[k])} {u} | {fmt(g[k])} {u} | {pct_change(b[k], g[k])} |")
        fs = r["fairness_stress_week"]
        lines.append(f"\nIn the stress week all {fs['households_ever_curtailed']} homes shared Tier-3 curtailment, "
                     f"at most {f1(fs['max_household_hours'])} h each (Gini {fs['gini_curtailment_hours']:.2f}), "
                     f"and {fs['refusals']} household overrides were honoured.")
        self.say(emit, "\n".join(lines))

    def household(self, num, wk, emit):
        r = self.call("get_household", {"household_id": f"HH-{int(num):03d}", **({"week": wk} if wk else {})})
        if "error" in r:
            return self.say(emit, r["error"])
        when = ", ".join(r["paused_intervals"][:6]) + ("…" if len(r["paused_intervals"]) > 6 else "")
        self.say(emit, f"**{r['id']}** (section {r['feeder_section']}, {r['week']} week)\n\n"
                       f"- Used {f1(r['energy_kwh'])} kWh, peak {r['peak_kw']:.2f} kW.\n"
                       f"- Tier-3 appliances paused for {r['tier3_paused_hours']:.2f} h across {r['curtailment_events']} events"
                       + (f": {when}." if when else ".") + "\n"
                       f"- Fully dark {r['dark_hours_baseline']:.2f} h on the baseline, {r['dark_hours_gridsetu']:.2f} h with GridSetu.\n"
                       f"- The most any home was paused this week: {f1(r['feeder_context']['max_hours_any_home'])} h.")

    def reserve(self, t, wk, emit):
        r = self.call("get_reliability_reserve", {k: v for k, v in {"day": t, "week": wk}.items() if v})
        if not r.get("stages"):
            return self.say(emit, f"No reserve was published for {r.get('day')}.")
        lines = [f"**Reliability Reserve for {r['day']}, {r['window']}**\n",
                 "| Stage | Reserve | Battery | Tier 3 + 2 | Confidence | Delivered |", "|---|--:|--:|--:|--:|--:|"]
        for s in r["stages"]:
            lines.append(f"| {s['stage']} | {f0(s['reserve_kw'])} kW | {f0(s['battery_kw'])} kW | "
                         f"{f0(s['tier3_kw'] + s['tier2_kw'])} kW | {f0(s['confidence_pct'])}% | "
                         f"{'–' if s['delivered_kw'] is None else f0(s['delivered_kw']) + ' kW'} |")
        lines.append(f"\n{r['note']}")
        self.say(emit, "\n".join(lines))

    def factors(self, emit):
        r = self.call("get_planning_factors", {})
        s = r["system"]
        lines = [f"**City:** peak {f0(s['city_peak_mw'])} MW at {s['city_peak_time'][5:16]}, load factor "
                 f"{s['city_load_factor']:.2f}, diversity across regions {s['diversity_factor_regions']:.2f}, "
                 f"utilisation {s['utilisation_factor']:.2f}, reserve margin at peak {s['reserve_margin_at_peak_pct']:.1f}%.\n",
                 "| Class | Priority | Max demand | Load factor | Demand factor | Diversity |", "|---|--:|--:|--:|--:|--:|"]
        for c in sorted(r["load_classes_city"], key=lambda x: x["priority"]):
            lines.append(f"| {c['class']} | {c['priority']} | {f0(c['max_demand_mw'])} MW | {c['load_factor']:.2f} | "
                         f"{c['demand_factor']:.2f} | {c.get('diversity_factor', 1):.2f} |")
        lines += ["\n| Plant | Capacity factor | Plant use factor |", "|---|--:|--:|"]
        for p in r["plants"]:
            lines.append(f"| {p['unit']} ({p['kind']}) | {100 * p['capacity_factor']:.0f}% | {100 * p['plant_use_factor']:.0f}% |")
        self.say(emit, "\n".join(lines))

    def navigate(self, q, t, wk, emit):
        page = next((v for k, v in PAGE_WORDS.items() if k in q), None)
        r = self.call("show_in_dashboard", {k: v for k, v in {"page": page, "time": t, "week": wk}.items() if v})
        self.say(emit, r.get("error") or "Done: " + ", ".join(r["done"]) + ".")

    def scenario(self, q, emit):
        args: dict = {}
        num = r"(\d+(?:\.\d+)?)"
        if m := re.search(rf"{num}\s*kwh", q):
            args["battery_kwh"] = float(m.group(1))
        if m := re.search(rf"battery[^\d]{{0,30}}{num}\s*kw\b(?!h)", q) or re.search(rf"{num}\s*kw\s*(inverter|battery power)", q):
            args["battery_kw"] = float(m.group(1))
        if m := re.search(rf"transformer[^\d]{{0,30}}{num}|{num}\s*kw\s*transformer", q):
            args["capacity_kw"] = float(m.group(1) or m.group(2))
        if m := re.search(rf"{num}\s*%\s*(packet )?loss|loss[^\d]{{0,20}}{num}\s*%", q):
            args["control_loss"] = float(m.group(1) or m.group(3)) / 100
        if m := re.search(rf"{num}\s*mw\s*(of )?(industrial )?(dr|demand response)|(dr|demand response)[^\d]{{0,20}}{num}\s*mw", q):
            args["industrial_dr_mw"] = float(m.group(1) or m.group(5))
        if m := re.search(rf"(island|critical)[^\d]{{0,30}}{num}\s*h", q):
            args["tier1_island_hours"] = float(m.group(2))
        if re.search(r"\b(no|without)\s+(the\s+)?(forced\s+)?outage", q):
            args["forced_outage"] = False
        if re.search(r"(no|without|legacy)\s+(solar[- ]hour\s+)?irrigation", q):
            args["irrigation_shift"] = False
        if "double" in q and "battery" in q and "battery_kwh" not in args:
            args["battery_kwh"] = 400.0
        if not args:
            return self.say(emit, "Tell me what to change, for example: *what if the battery is 400 kWh*, "
                                  "*transformer 350 kW*, *30% packet loss*, *20 MW industrial DR*, or *no outage*.")
        r = self.call("run_scenario", args)
        if "error" in r:
            return self.say(emit, r["error"])
        a, b, ch = r["a"]["gridsetu_month"], r["b"]["gridsetu_month"], r["change_pct_b_vs_a"]
        rows = [("Unserved energy, 17:30 to 19:30", "evening_window_unserved_kwh", "kWh", f0),
                ("Unserved energy, all hours", "total_unserved_kwh", "kWh", f0),
                ("Critical-load outage", "critical_outage_hours", "h", f1),
                ("Whole feeder dark", "feeder_outage_hours", "h", f1),
                ("Peak from the grid", "feeder_peak_import_kw", "kW", f0),
                ("Battery cycles", "battery_cycles", "", f1)]
        took = "was already computed" if r["runtime_s"] < 2 else f"finished in {r['runtime_s']} s"
        lines = [f"**{r['label']}** {took}. GridSetu per month, reference against your run:\n",
                 "| Metric | Reference | This run | Change |", "|---|--:|--:|--:|"]
        for name, k, u, fmt in rows:
            c = ch.get(k)
            lines.append(f"| {name} | {fmt(a[k])} {u} | {fmt(b[k])} {u} | {'n/a' if c is None else f'{c:+.0f}%'} |")
        lines.append(f"\n{r['caveat']} Use **Show everywhere** to open this run on every page.")
        if all(abs(v or 0) < 0.5 for v in ch.values()):
            lines.append("\nThis change made no measurable difference in this scenario.")
        self.say(emit, "\n".join(lines))

    def note(self, t, wk, emit):
        ov = self.call("get_overview", {k: v for k, v in {"week": wk}.items() if v})
        if t and re.fullmatch(r"[a-z]+", t.strip()):   # a bare day: use its evening window
            t = f"{t} 18:00"
        mo = self.call("get_moment", {"time": t or "Thu 18:00", "week": wk or "stress"})
        rs = self.call("get_reliability_reserve", {"day": (t or "Thu").split()[0], "week": wk or "stress"})
        c, f = mo["city"], mo["pilot_feeder"]
        g, b = ov["monthly_pilot_feeder"]["gridsetu"], ov["monthly_pilot_feeder"]["baseline"]
        rt = next((s for s in rs.get("stages", []) if s["stage"] == "real-time"), None)
        text = f"""**Subject:** Feeder F07 evening event, {c['time']}: GridSetu reliability report (simulation)

**Summary.** At {c['time']} {f"the city was short of supply ({f0(c['city_shed_mw'])} MW shed city-wide" if c['city_shed_mw'] > 0.5 else "the city had no load shedding ("}{", " if c['city_shed_mw'] > 0.5 else ""}R3 price ₹{c['regions']['R3']['price_rt_inr_kwh']:.2f}/kWh). On feeder F07 the baseline would have been {self._state(f['baseline']['state'])}. With GridSetu the feeder was {self._state(f['gridsetu']['state'])}, with the clinic, school, water pump and street lights {'kept on' if (f['gridsetu']['critical_load_unserved_kw'] or 0) < 0.01 else 'affected'}.

**What GridSetu did.**
- Battery at {f0(f['gridsetu']['soc_pct'])}% state of charge, {self._bat(f['gridsetu']['battery_kw'])}.
- {f0(f['gridsetu']['tier3_paused_kw'])} kW of Tier-3 appliances paused through the fairness ledger; {f0(f['gridsetu']['homes_fully_supplied_pct'])}% of homes fully supplied.
""" + (f"- Reliability Reserve for the 17:30 to 19:30 window: {f0(rt['reserve_kw'])} kW offered at {f0(rt['confidence_pct'])}% confidence, {f0(rt['delivered_kw'])} kW delivered on average.\n" if rt else "") + f"""
**Monthly effect on F07** (3 normal weeks + 1 stress week):
- Critical-load outage {f1(b['critical_outage_hours'])} h → {f1(g['critical_outage_hours'])} h.
- Whole-feeder outage {f1(b['feeder_outage_hours'])} h → {f1(g['feeder_outage_hours'])} h.
- Evening unserved energy {f0(b['evening_window_unserved_kwh'])} kWh → {f0(g['evening_window_unserved_kwh'])} kWh.

**Next steps.** Confirm the curtailment-request interface with the ADMS team, and review whether the feeder should stay in the rotational-shedding group now that it can deliver relief.

*All figures are simulation on synthetic data, not field measurement.*"""
        self.say(emit, text)
