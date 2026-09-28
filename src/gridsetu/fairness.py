"""Fairness rotation ledger for Tier-3 household curtailment.

Rules (enforced here, inside dispatch, not as a post-hoc report):
1. A household curtailed in one 15-minute dispatch interval is not eligible in the next,
   so no household is ever curtailed for two consecutive intervals.
2. Households with the lowest cumulative curtailment go first.
3. Each request can be refused (user override); refusals are logged, never forced.
If rule 1 would leave the request unmet, it is relaxed and a violation is recorded.
An "event" is a contiguous run of intervals with curtailment (reported, not a rule)."""
from __future__ import annotations

import numpy as np


class FairnessLedger:
    def __init__(self, n_households: int, refusal_prob: float, rng: np.random.Generator):
        self.n = n_households
        self.refusal_prob = refusal_prob
        self.rng = rng
        self.hours = np.zeros(n_households)          # cumulative curtailment hours
        self.events = np.zeros(n_households, int)    # number of events curtailed in
        self.last_event = np.full(n_households, -10)
        self.last_step = np.full(n_households, -10)
        self.step_id = -1
        self.event_id = -1
        self.in_event = False
        self.refusals = 0
        self.requests = 0
        self.violations = 0

    def step(self, needed_kw: float, tier3_kw: np.ndarray, dt_h: float) -> tuple[float, np.ndarray]:
        """Curtail at least needed_kw of Tier-3 load if possible. Returns (kw curtailed, mask)."""
        mask = np.zeros(self.n, bool)
        self.step_id += 1
        if needed_kw <= 1e-6:
            self.in_event = False
            return 0.0, mask
        if not self.in_event:
            self.event_id += 1
            self.in_event = True
        rested = self.last_step < self.step_id - 1
        eligible = (tier3_kw > 0.02) & rested
        got = self._fill(needed_kw, tier3_kw, eligible, mask)
        if got < needed_kw - 1e-6:
            relaxed = (tier3_kw > 0.02) & ~mask & ~rested
            if relaxed.any():
                extra = self._fill(needed_kw - got, tier3_kw, relaxed, mask)
                if extra > 0:
                    self.violations += 1
                got += extra
        self.hours[mask] += dt_h
        newly = mask & (self.last_event != self.event_id)
        self.events[newly] += 1
        self.last_event[mask] = self.event_id
        self.last_step[mask] = self.step_id
        return got, mask

    def _fill(self, needed: float, tier3: np.ndarray, eligible: np.ndarray, mask: np.ndarray) -> float:
        cand = np.flatnonzero(eligible)
        if cand.size == 0:
            return 0.0
        # lowest cumulative hours first; random tie-break so ordering is not by index
        order = cand[np.lexsort((self.rng.random(cand.size), self.hours[cand]))]
        got = 0.0
        for i in order:
            if got >= needed:
                break
            self.requests += 1
            if self.rng.random() < self.refusal_prob:
                self.refusals += 1
                continue
            mask[i] = True
            got += tier3[i]
        return got

    def summary(self) -> dict:
        h = self.hours
        curtailed = h[h > 0]
        gini = 0.0
        if h.sum() > 0:
            s = np.sort(h)
            n = len(s)
            gini = float((2 * np.arange(1, n + 1) - n - 1) @ s / (n * s.sum()))
        return {
            "events": int(self.event_id + 1),
            "households_ever_curtailed": int((h > 0).sum()),
            "max_household_hours": float(h.max()) if h.size else 0.0,
            "mean_hours_if_curtailed": float(curtailed.mean()) if curtailed.size else 0.0,
            "gini_curtailment_hours": gini,
            "consecutive_interval_violations": int(self.violations),
            "requests": int(self.requests),
            "refusals": int(self.refusals),
        }
