"""Scenario loading and the shared simulation time grid."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "city.yaml"

CLASSES = ["traction", "municipal", "domestic", "commercial", "irrigation", "industrial"]


@dataclass
class Scenario:
    raw: dict
    index: pd.DatetimeIndex
    dt_h: float
    steps_per_day: int
    rng_seed: int
    path: Path | None = None
    overrides: dict = field(default_factory=dict)

    # convenience accessors -------------------------------------------------
    @property
    def regions(self) -> dict:
        return self.raw["regions"]

    @property
    def generators(self) -> dict:
        return self.raw["generators"]

    @property
    def classes(self) -> dict:
        return self.raw["load_classes"]

    @property
    def feeder(self) -> dict:
        return self.raw["pilot_feeder"]

    @property
    def n_steps(self) -> int:
        return len(self.index)

    @property
    def n_days(self) -> int:
        return self.raw["simulation"]["days"]

    def rng(self, salt: int = 0) -> np.random.Generator:
        return np.random.default_rng(self.rng_seed + salt)

    def time_mask(self, start_hhmm: str, end_hhmm: str) -> np.ndarray:
        """Boolean mask of steps whose start falls inside [start, end) each day."""
        minutes = self.index.hour * 60 + self.index.minute
        s = _hhmm(start_hhmm)
        e = _hhmm(end_hhmm)
        return np.asarray((minutes >= s) & (minutes < e))

    def step_of(self, timestamp: str) -> int:
        ts = pd.Timestamp(timestamp)
        return int(np.searchsorted(self.index, ts))


def _hhmm(text: str) -> int:
    h, m = text.split(":")
    return int(h) * 60 + int(m)


def _deep_update(base: dict, upd: dict) -> dict:
    for k, v in upd.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
    return base


def load_scenario(path: str | Path | None = None, overrides: dict | None = None) -> Scenario:
    path = Path(path) if path else DEFAULT_CONFIG
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    raw = copy.deepcopy(raw)
    if overrides:
        _deep_update(raw, overrides)
    sim = raw["simulation"]
    step = int(sim["step_minutes"])
    steps_per_day = 24 * 60 // step
    index = pd.date_range(sim["start"], periods=sim["days"] * steps_per_day, freq=f"{step}min")
    return Scenario(raw=raw, index=index, dt_h=step / 60.0, steps_per_day=steps_per_day,
                    rng_seed=int(sim["seed"]), path=path, overrides=overrides or {})
