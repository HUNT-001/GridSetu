"""Read-only access to a finished run's payloads, with the helpers the copilot tools need:
time parsing, per-step snapshots and event detection. Everything here works on the same
cached payloads the dashboard shows, so the copilot and the UI always agree."""
from __future__ import annotations

import gzip
import json
import re
from datetime import datetime, timedelta
from typing import Callable

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
CLASSES = ["traction", "municipal", "domestic", "commercial", "irrigation", "industrial"]


class RunData:
    """Lazy, cached view of one run. `loader(key) -> gzipped bytes | None`."""

    def __init__(self, run_id: str, loader: Callable[[str], bytes | None]):
        self.run_id = run_id
        self._loader = loader
        self._cache: dict[str, dict] = {}

    def get(self, key: str) -> dict:
        if key not in self._cache:
            blob = self._loader(key)
            if blob is None:
                raise KeyError(f"{key} is not available for run {self.run_id}")
            self._cache[key] = json.loads(gzip.decompress(blob))
        return self._cache[key]

    @property
    def meta(self) -> dict:
        return self.get("meta")

    @property
    def summary(self) -> dict:
        return self.get("summary")

    def city(self, week: str) -> dict:
        return self.get(f"city:{week}")

    def feeder(self, week: str) -> dict:
        return self.get(f"feeder:{week}")

    def households(self, week: str) -> dict:
        return self.get(f"households:{week}")

    # ------------------------------------------------------------------ time
    def t0(self, week: str) -> datetime:
        return datetime.fromisoformat(self.meta["weeks"][week]["t0"])

    def n(self, week: str) -> int:
        return int(self.meta["weeks"][week]["n"])

    def when(self, week: str, step: int) -> str:
        d = self.t0(week) + timedelta(minutes=15 * int(step))
        return d.strftime("%a %d %b %H:%M")

    def parse_time(self, text: str | int | None, week: str, default: int | None = None) -> int:
        """Accepts a step number, 'Thu 18:00', 'thursday 6pm', '18:00', '2026-09-17 18:00'."""
        n = self.n(week)
        if text is None or text == "":
            if default is None:
                raise ValueError("A time is needed, for example 'Thu 18:00'.")
            return default
        if isinstance(text, (int, float)):
            return int(max(0, min(n - 1, int(text))))
        s = str(text).strip().lower()
        if re.fullmatch(r"(step\s*)?\d+", s) and ":" not in s:
            return int(max(0, min(n - 1, int(re.sub(r"\D", "", s)))))
        m = re.search(r"(\d{4}-\d{2}-\d{2})[ t](\d{1,2}):(\d{2})", s)
        if m:
            d = datetime.fromisoformat(f"{m.group(1)} {int(m.group(2)):02d}:{m.group(3)}")
            return self._clip((d - self.t0(week)).total_seconds() / 900, n)
        day = None
        for i, name in enumerate(DAYS):
            if re.search(rf"\b{name}", s):
                day = i
                break
        hh, mm = None, 0
        m = re.search(r"(\d{1,2})[:.](\d{2})\s*(am|pm)?", s) or re.search(r"\b(\d{1,2})\s*(am|pm)\b", s)
        if m:
            hh = int(m.group(1))
            if len(m.groups()) == 3:
                mm = int(m.group(2) or 0)
                ap = m.group(3)
            else:
                ap = m.group(2)
            if ap == "pm" and hh < 12:
                hh += 12
            if ap == "am" and hh == 12:
                hh = 0
        elif "evening" in s:
            hh = 18
        elif "noon" in s or "midday" in s:
            hh = 12
        elif "morning" in s:
            hh = 8
        elif "night" in s:
            hh = 21
        if hh is None and day is None:
            raise ValueError(f"Could not read a time from '{text}'. Try 'Thu 18:00'.")
        start_dow = self.t0(week).weekday()
        if day is None:
            day_idx = (default // 96) if default is not None else 0
        else:
            day_idx = (day - start_dow) % 7
        step = day_idx * 96 + (hh or 0) * 4 + mm // 15
        return self._clip(step, n)

    @staticmethod
    def _clip(x: float, n: int) -> int:
        return int(max(0, min(n - 1, round(x))))

    # ------------------------------------------------------------------ snapshots
    def city_at(self, week: str, step: int, scenario: str = "baseline") -> dict:
        c = self.city(week)["scenarios"][scenario]
        gens = self.meta["config"]["generators"]
        regions = {}
        tot_load = tot_shed = 0.0
        for r in c["load"]:
            load = sum((c["load"][r][k][step] or 0) for k in CLASSES)
            shed_by = {k: round(c["shed"][r][k][step] or 0, 1) for k in CLASSES if (c["shed"][r][k][step] or 0) > 0.05}
            shed = sum(shed_by.values())
            tot_load += load
            tot_shed += shed
            regions[r] = {"name": self.meta["config"]["regions"][r]["name"], "demand_mw": round(load, 1),
                          "shed_mw": round(shed, 1), "shed_by_class_mw": shed_by,
                          "price_da_inr_kwh": c["price_da"][r][step], "price_rt_inr_kwh": c["price_rt"][r][step]}
        gen = {}
        for g, v in gens.items():
            out = c["gen"][g][step] or 0
            row = {"kind": v["kind"], "mw": round(out, 1), "pmax_mw": v["pmax_mw"]}
            if g in c["avail"]:
                row["available_mw"] = round(c["avail"][g][step] or 0, 1)
            if v.get("mc_inr_kwh") is not None:
                row["marginal_cost_inr_kwh"] = v["mc_inr_kwh"]
            gen[g] = row
        limits = self.city(week)["tie_limit"]
        flows = {k: {"mw": round(v[step] or 0, 1), "limit_mw": limits[k],
                     "loading_pct": round(100 * abs(v[step] or 0) / limits[k])} for k, v in c["flow"].items()}
        w = self.city(week)["weather"]
        return {"time": self.when(week, step), "step": step, "week": week, "scenario": scenario,
                "city_demand_mw": round(tot_load, 1), "city_shed_mw": round(tot_shed, 1),
                "exchange_price_inr_kwh": c["exchange_price"][step],
                "industrial_dr_mw": round(c["dr"][step] or 0, 1),
                "weather": {"clear_sky_index": w["csi"][step], "temp_c": w["temp"][step],
                            "wind_capacity_factor": w["wind_cf"][step]},
                "regions": regions, "generation": gen, "interties": flows}

    def feeder_at(self, week: str, step: int) -> dict:
        f = self.feeder(week)
        codes = f["state_codes"]
        out = {"time": self.when(week, step), "capacity_kw": f["capacity_kw"]}
        for v, d in f["variants"].items():
            s = d["series"]
            out[v] = {"state": codes[d["state"][step]], "import_kw": s["import"][step],
                      "battery_kw": s["battery_kw"][step], "soc_pct": s["soc_pct"][step],
                      "unserved_kw": s["unserved"][step], "tier3_paused_kw": s["curtail_t3"][step],
                      "tier2_shifted_kw": s["curtail_t2"][step],
                      "critical_load_unserved_kw": s["tier1_unserved"][step],
                      "homes_fully_supplied_pct": d["hh_lit_pct"][step],
                      "discom_cap_kw": s["cap_request"][step]}
        return out

    def feeder_episodes(self, week: str, variant: str) -> list[dict]:
        """Contiguous runs of non-normal feeder states."""
        f = self.feeder(week)
        codes = f["state_codes"]
        st = [codes[c] for c in f["variants"][variant]["state"]]
        eps, i = [], 0
        while i < len(st):
            if st[i] == "normal":
                i += 1
                continue
            j = i
            while j + 1 < len(st) and st[j + 1] != "normal":
                j += 1
            span = st[i:j + 1]
            hours = {k: span.count(k) / 4 for k in sorted(set(span))}
            eps.append({"start": self.when(week, i), "end": self.when(week, j + 1), "start_step": i,
                        "hours": (j + 1 - i) / 4, "state_hours": hours})
            i = j + 1
        return eps

