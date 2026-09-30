"""`gridsetu replay`: publish a cached run to an MQTT broker as live telemetry."""
from __future__ import annotations

import os
from pathlib import Path

from .data import RunData
from .live import MqttBridge, stream


def _cache() -> Path:
    return Path(os.environ.get("GRIDSETU_CACHE", Path(__file__).resolve().parents[3] / ".cache" / "runs"))


def _reference(cache: Path) -> str:
    from ..api.engine import run_id_for
    rid = run_id_for({}, int(os.environ.get("GRIDSETU_SEEDS", "3")))
    if (cache / rid / "meta.json.gz").exists():
        return rid
    ready = sorted((p.parent for p in cache.glob("*/meta.json.gz")), key=lambda p: p.stat().st_mtime)
    if not ready:
        raise SystemExit("No finished runs in the cache. Start `gridsetu serve` once to compute the reference run.")
    return ready[-1].name


def replay(broker: str, run: str | None, week: str, speed: float, start: str, steps: int):
    cache = _cache()
    rid = run or _reference(cache)
    d = RunData(rid, lambda key: (cache / rid / f"{key.replace(':', '__')}.json.gz").read_bytes()
                if (cache / rid / f"{key.replace(':', '__')}.json.gz").exists() else None)
    s0 = d.parse_time(int(start) if start.isdigit() else start, week, default=0)
    bridge = MqttBridge(broker, rid)
    print(f"Publishing run {rid} ({week} week) from {d.when(week, s0)} to mqtt://{broker}/gridsetu/{rid}/# "
          f"at {speed} steps/s. Ctrl+C to stop.")
    try:
        for i, (step, msgs) in enumerate(stream(d, week, s0, speed)):
            bridge.publish(msgs)
            if i % max(1, int(speed * 5)) == 0:
                scada = next(p for t, p in msgs if t.endswith("/scada"))
                print(f"  {d.when(week, step)}  F07 {scada['state']:<28} {scada['import_kw'] or 0:6.0f} kW  SOC {scada['soc_pct'] or 0:5.1f}%")
            if steps and i + 1 >= steps:
                break
    except KeyboardInterrupt:
        pass
    finally:
        bridge.close()
