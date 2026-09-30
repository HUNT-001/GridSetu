"""Live telemetry replay: plays a finished run back in (accelerated) real time as the
messages a control room would receive: feeder SCADA every 15 minutes, smart-meter (AMI)
aggregates, city state, and Reliability Reserve publications. The same message stream feeds
the dashboard's Live mode (Server-Sent Events) and, optionally, an MQTT broker, so the
dashboard can later be pointed at real telemetry with the same message shapes.

MQTT topics (QoS 0, JSON payloads):
  gridsetu/<run>/city/state
  gridsetu/<run>/feeder/F07/scada
  gridsetu/<run>/feeder/F07/ami
  gridsetu/<run>/feeder/F07/reserve"""
from __future__ import annotations

import json
import time
from datetime import timedelta
from typing import Iterator

from .data import CLASSES, RunData

FEEDER = "F07"


def messages_at(d: RunData, week: str, step: int, delivered_pct: float | None = None) -> list[tuple[str, dict]]:
    """All messages the control room receives for one 15-minute interval."""
    city = d.city(week)["scenarios"]["baseline"]
    f = d.feeder(week)
    g = f["variants"]["gridsetu"]
    b = f["variants"]["baseline"]
    ts = (d.t0(week) + timedelta(minutes=15 * step)).isoformat()
    codes = f["state_codes"]
    demand = sum(city["load"][r][k][step] or 0 for r in city["load"] for k in CLASSES)
    shed = sum(city["shed"][r][k][step] or 0 for r in city["shed"] for k in CLASSES)
    n_hh = f["n_households"]
    lit = g["hh_lit_pct"][step] or 0
    ami_pct = delivered_pct if delivered_pct is not None else 85.0
    out = [
        ("city/state", {"ts": ts, "step": step, "demand_mw": round(demand, 1), "shed_mw": round(shed, 1),
                        "price_rt_inr_kwh": {r: city["price_rt"][r][step] for r in city["price_rt"]},
                        "import_mw": city["gen"]["IMP"][step],
                        "renewables_mw": round((city["gen"]["S1"][step] or 0) + (city["gen"]["W1"][step] or 0), 1)}),
        (f"feeder/{FEEDER}/scada", {"ts": ts, "step": step, "state": codes[g["state"][step]],
                                    "import_kw": g["series"]["import"][step], "battery_kw": g["series"]["battery_kw"][step],
                                    "soc_pct": g["series"]["soc_pct"][step], "critical_on": (g["series"]["tier1_unserved"][step] or 0) < 0.01,
                                    "baseline_state": codes[b["state"][step]]}),
        (f"feeder/{FEEDER}/ami", {"ts": ts, "step": step, "meters": n_hh, "reads_received": round(n_hh * ami_pct / 100),
                                  "fully_supplied_pct": lit, "tier3_paused_kw": g["series"]["curtail_t3"][step],
                                  "net_load_kw": f["actual_net"][step]}),
    ]
    for r in g["reserves"]:
        issued = r["issued_at"].replace(" ", "T")
        if issued[:16] == ts[:16]:
            out.append((f"feeder/{FEEDER}/reserve", r))
    return out


def stream(d: RunData, week: str, start: int, speed: float) -> Iterator[tuple[int, list[tuple[str, dict]]]]:
    """Yields (step, messages) paced at `speed` steps per second, forever (wraps the week)."""
    n = d.n(week)
    step = max(0, min(n - 1, start))
    ami_pct = next((c["delivered_pct"] for c in d.summary.get("comms", []) if c["slice"] == "mmtc_ami"), 85.0)
    interval = 1.0 / max(speed, 0.1)
    nxt = time.monotonic()
    while True:
        yield step, messages_at(d, week, step, ami_pct)
        step = (step + 1) % n
        nxt += interval
        time.sleep(max(0.0, nxt - time.monotonic()))


class MqttBridge:
    """Optional: publish replay messages to an MQTT broker (paho-mqtt)."""

    def __init__(self, broker: str, run_id: str):
        import paho.mqtt.client as mqtt
        host, _, port = broker.partition(":")
        self.prefix = f"gridsetu/{run_id}"
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"gridsetu-replay-{run_id}")
        except AttributeError:  # paho-mqtt < 2
            self.client = mqtt.Client(client_id=f"gridsetu-replay-{run_id}")
        self.client.connect(host, int(port or 1883), keepalive=30)
        self.client.loop_start()

    def publish(self, msgs: list[tuple[str, dict]]):
        for topic, payload in msgs:
            self.client.publish(f"{self.prefix}/{topic}", json.dumps(payload), qos=0)

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()
