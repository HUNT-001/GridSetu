"""Uncertainty engine and the Reliability Reserve object.

The day-ahead plan already keeps import under the feeder rating for the median (q50)
forecast. The uncertainty engine sizes the *extra* energy the battery must hold at the
start of the evening window so that the plan survives a q90 outcome, estimates the risk
that even that is not enough, and widens the buffer when the risk is too high."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

Z90 = 1.2816


@dataclass
class ReserveSizing:
    day: int
    window_start_step: int
    buffer_kwh: float           # uncertainty buffer on top of the q50 plan
    expected_cap_kwh: float     # energy expected to be requested by the DISCOM (DA scarcity)
    risk: float                 # P(needed energy > held energy)
    widened: bool
    need_q50_kwh: float
    need_q90_kwh: float


def _need(net: np.ndarray, pv: np.ndarray, target: float, dt: float) -> float:
    return float(np.maximum(net - pv - target, 0).sum() * dt)


def size_reserve(day: int, steps: np.ndarray, window_mask: np.ndarray, fc_net, fc_pv,
                 target_kw: float, dt: float, usable_kwh: float, cfg: dict,
                 cap_fraction: np.ndarray, rng: np.random.Generator,
                 n_samples: int = 1000) -> ReserveSizing:
    """steps: global step indices of the evening period to protect (e.g. 17:00-23:00).
    window_mask: which of those steps are in the declared evening window."""
    q10n, q50n, q90n = fc_net.q10[steps], fc_net.q50[steps], fc_net.q90[steps]
    q10p, q50p, q90p = fc_pv.q10[steps], fc_pv.q50[steps], fc_pv.q90[steps]
    need50 = _need(q50n, q50p, target_kw, dt)
    need90 = _need(q90n, q10p, target_kw, dt)      # high load paired with low solar
    buffer = cfg["k_sigma"] * max(0.0, need90 - need50)
    expected_cap = float((cap_fraction[steps] * np.maximum(q50n - q50p, 0)).sum() * dt)

    # Monte Carlo: a common shock across the evening (conservative, fully correlated) plus
    # an independent step-level component.
    sig_n = np.maximum(q90n - q10n, 1e-6) / (2 * Z90)
    sig_p = np.maximum(q90p - q10p, 1e-6) / (2 * Z90)
    zc = rng.normal(size=(n_samples, 1))
    zi = rng.normal(size=(n_samples, len(steps)))
    zp = rng.normal(size=(n_samples, 1))
    net_s = q50n + sig_n * (0.8 * zc + 0.6 * zi)
    pv_s = np.clip(q50p + sig_p * zp, 0, None)
    need_s = np.maximum(net_s - pv_s - target_kw, 0).sum(axis=1) * dt - need50

    held = min(buffer, usable_kwh)
    risk = float(np.mean(need_s > held))
    widened = False
    if risk > cfg["risk_threshold"]:
        held = min(buffer * cfg["widen_factor"] + 1e-9, usable_kwh)
        widened = True
        risk = float(np.mean(need_s > held))
    return ReserveSizing(day, int(steps[window_mask][0]) if window_mask.any() else int(steps[0]),
                         held, expected_cap, risk, widened, need50, need90)


@dataclass
class ReliabilityReserve:
    """What GridSetu publishes into ADMS/DERMS (maps onto an IEC 61968-5 DERGroupForecast)."""
    feeder_id: str
    stage: str                  # T-24h | T-1h | T-15min | real-time | post-event
    issued_at: str
    window_start: str
    window_end: str
    reserve_kw: float
    energy_kwh: float
    duration_h: float
    confidence_pct: float
    cost_inr_kwh: float
    battery_kw: float
    tier3_kw: float
    tier2_kw: float
    delivered_kw: float | None = None
    cim_profile: str = "IEC 61968-5 DERGroupForecast"

    def to_dict(self) -> dict:
        return asdict(self)
