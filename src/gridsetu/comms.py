"""Slice layer: communication slices with latency, packet loss and retries.

Each control message either arrives within its step (after up to `retries` resends) or
is lost; the edge controller's fail-safe decides what happens on loss."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Slice:
    name: str
    latency_ms: float
    loss: float
    retries: int
    rng: np.random.Generator
    sent: int = 0
    delivered: int = 0
    attempts: int = 0
    log: list = field(default_factory=list)

    def send(self) -> bool:
        self.sent += 1
        for _ in range(self.retries + 1):
            self.attempts += 1
            if self.rng.random() >= self.loss:
                self.delivered += 1
                return True
        return False

    def bulk(self, n: int) -> int:
        """Send n independent telemetry messages (no per-message retry logic needed)."""
        ok = int(self.rng.binomial(n, 1 - self.loss ** (self.retries + 1))) if n else 0
        self.sent += n
        self.delivered += ok
        self.attempts += n
        return ok

    def stats(self) -> dict:
        return {"slice": self.name, "latency_ms": self.latency_ms, "packet_loss": self.loss,
                "retries": self.retries, "messages": self.sent,
                "delivered_pct": 100 * self.delivered / self.sent if self.sent else 100.0,
                "transmissions": self.attempts}


def build_slices(cfg: dict, rng: np.random.Generator) -> dict[str, Slice]:
    return {name: Slice(name, v["latency_ms"], v["loss"], v["retries"], rng)
            for name, v in cfg.items()}
