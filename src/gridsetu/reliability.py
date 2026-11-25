"""Reliability indices in the DISCOM's terms: SAIDI, SAIFI, CAIDI and evening supply availability.

Baseline (one sentence): today's rotational load-shedding by the DISCOM, with no storage and no
demand response on the feeder.

Definitions, per simulated period (a week; the runner sums weeks into the composite month):
  customers        the feeder's households (shops, workshops and Tier-1 sites are not counted)
  interruption     a household is dark: no supply at all (status 2). A home held to the
                   lifeline allowance (status 3) or with one appliance paused (status 1) is
                   still supplied, so it is not interrupted. Lifeline home-hours are reported
                   next to SAIDI so the difference stays visible.
  sustained        every interruption here lasts at least one 15-minute step, so all count as
                   sustained (IEEE 1366 uses > 5 minutes); momentary interruptions (MAIFI) are
                   below the simulator's resolution
  SAIDI            customer interruption hours / customers          (h per customer)
  SAIFI            customer interruptions / customers               (interruptions per customer)
  CAIDI            SAIDI / SAIFI                                    (h per interruption)
  evening avail.   share of household-steps in the evening window that are not dark
  ENS              energy not supplied = the simulator's ``total_unserved_kwh`` (all hours, net
                   of rebound). It is not recomputed here so the same quantity has one number.
A run of dark steps that starts in the first step of the period counts as one interruption.
"""
from __future__ import annotations

import numpy as np

DARK = 2


def interruption_counts(hh_status: np.ndarray) -> np.ndarray:
    """Interruptions per household: number of runs of consecutive dark steps.
    hh_status is [step][household] (uint8 codes, 2 = dark)."""
    dark = np.asarray(hh_status) == DARK
    if dark.size == 0:
        return np.zeros(dark.shape[1] if dark.ndim == 2 else 0, dtype=int)
    starts = dark[0].astype(int) + (dark[1:] & ~dark[:-1]).sum(axis=0)
    return starts.astype(int)


def reliability_indices(hh_status: np.ndarray, dt_h: float, evening_mask: np.ndarray) -> dict:
    """SAIDI, SAIFI, CAIDI and evening availability for one period of ``hh_status``."""
    st = np.asarray(hh_status)
    n_steps, n_hh = st.shape
    dark = st == DARK
    interruptions = interruption_counts(st)
    saidi = float(dark.sum() * dt_h / n_hh) if n_hh else 0.0
    saifi = float(interruptions.sum() / n_hh) if n_hh else 0.0
    ev = np.asarray(evening_mask, dtype=bool)
    ev_cells = int(ev.sum()) * n_hh
    avail = float(100 * (1 - dark[ev].sum() / ev_cells)) if ev_cells else 100.0
    return {
        "saidi_h": saidi,
        "saifi": saifi,
        "caidi_h": saidi / saifi if saifi else 0.0,
        "customer_interruptions": int(interruptions.sum()),
        "evening_supply_availability_pct": avail,
        "evening_dark_home_hours": float(dark[ev].sum() * dt_h),
        "customers": int(n_hh),
    }
