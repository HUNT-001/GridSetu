# GridSetu: Phase 1 smart-grid simulator

A runnable, multi-layer model of a synthetic peri-urban Indian city ("Setu Nagar", modelled on the Coimbatore periphery). It follows electricity from generating stations through a three-region transmission grid and its market to one 11 kV feeder where GridSetu operates. Every run compares a **baseline** against **GridSetu**, using the same physics and the same random draws.

> **Everything here is SIMULATION on synthetic data, not field measurement.** Every input is an engineering assumption in `config/city.yaml`.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m gridsetu run --seeds 3 --out outputs          # ~90 s on a laptop, faster with numba
pytest -q                                               # 15 physics / safety / fairness invariants
```

Or install it as a package with `pip install -e .[dev]` and run `gridsetu run`.

**Outputs**

| Path | Contents |
|---|---|
| `outputs/summary.txt` | Headline table |
| `outputs/results.json` | Every metric |
| `outputs/reliability_reserve_stress_week.json` | The object GridSetu publishes to ADMS/DERMS |
| `outputs/charts/*.png` | Deck-ready charts; `slide2_24h_profile.png` and `slide8_baseline_vs_proposed.png` drop straight into the deck |
| `outputs/tables/*.csv` | Time series and factor tables |

## What is modelled, by grid layer

| Layer | What it does | Module |
|---|---|---|
| **Power** | 3 bid areas (R1 industrial, R2 urban, R3 peri-urban/agri), 220 kV ring plus national tie. Coal ×2, gas, small hydro, 100 MW solar park, 60 MW wind, rooftop PV. 220/33/11 kV AC power flow with security check. An isolated solar + battery + diesel hamlet | `market.py`, `network.py`, `island.py` |
| **Infrastructure** | Household-level AMI (420 meters) for the pilot feeder, a 200 kWh / 100 kW community battery, rooftop and community PV, PMU-rate (50 fps) frequency data | `profiles.py`, `feeder.py`, `wams.py` |
| **Management & monitoring** | Load, diversity, demand, capacity, plant-use and utilisation factors, reserve margin. Market statistics. Probabilistic forecasts. The Reliability Reserve published at T−24h, T−1h, T−15min, real time and post-event | `metrics.py`, `forecast.py`, `reserve.py` |
| **Control** | Day-ahead market splitting and real-time redispatch. Priority load shedding. Feeder battery LP. Edge controller with Tier 1/2/3 loads, fairness ledger, Tier-1 islanding. SPS and UFLS protection. Demand response | `market.py`, `feeder.py`, `fairness.py`, `wams.py` |
| **Slice** | URLLC (protection), mMTC (AMI), 2G/4G control, eMBB (dashboard) slices with loss, latency and retries. Edge fail-safe on message loss, plus a comms-degraded sensitivity run | `comms.py` |

### Flow of one simulated week
1. **Weather**: solar geometry, a monsoon clear-sky index and Tamil Nadu monsoon wind.
2. **Load**: six consumer classes per region: domestic, commercial, industrial, municipal, irrigation and traction.
3. **Market**: the day-ahead market clears 96 blocks per day (IEX-style). It gives a regional market clearing price from the dual of each area's power balance.
4. **Real time**: re-dispatch on actual values, including a forced outage the day-ahead market did not see.
5. **Shedding**: in revenue-priority order. Traction and municipal are never shed; irrigation and domestic go first, as at a cash-strapped DISCOM.
6. **Pilot feeder**: receives the resulting price, curtailment requests, rotational trips and SPS signals.
7. **Comparison**: the baseline feeder is simply tripped. GridSetu plans on quantile forecasts, holds an uncertainty-sized reserve, peak-shaves under the transformer rating, meets curtailment requests from battery → Tier 3 → Tier 2, and islands Tier 1 when the feeder is tripped anyway.

## Headline results (3 seeds; month = 3 normal weeks + 1 stress week)

| Metric | Baseline | GridSetu | Change |
|---|--:|--:|--:|
| Unserved energy, evening ramp 17:30–19:30 (kWh/month) | 2,713 | 546 | −80% |
| Unserved energy, all hours (kWh/month) | 3,825 | 811 | −79% |
| Critical-load (Tier-1) outage (h/month) | 13.6 | 0.0 | −100% |
| Whole-feeder outage (h/month) | 13.6 | 2.9 | −79% |
| Feeder peak import (kW) | 340 | 291 | −14% |
| Battery cycles per month | — | 17.6 | |

City-level coordination (solar-hour irrigation plus industrial DR) on top brings evening unserved energy to 403 kWh/month. Full numbers, seed ranges and the other studies are in `outputs/summary.txt`:
- forecast calibration
- fairness Gini
- SPS/UFLS event study
- isolated microgrid
- power-flow security
- comms-degraded run

### Where the model disagrees with the current deck, and why
- **Solar utilisation, "61% → 84%": not supported.** On this feeder, midday load always exceeds 150 kWp of solar, so there is never reverse power flow to waste. Both scenarios use ~100% of the solar. Drop this metric or re-scope it (for example, a feeder with more solar than daytime load).
- **Unserved energy is larger than the deck's 148 kWh/week.** That figure had no model behind it. Here, baseline outages come from three mechanisms: transformer overload trips on the evening ramp (6–17 per month across seeds), rotational shedding during a 30-hour generation shortfall, and one SPS operation.
- **Stress weeks are where GridSetu is weakest.** During a 30-hour, 125 MW shortfall, a 200 kWh battery cannot supply ~1,200 kWh of requested relief. The DISCOM still trips the feeder for part of the event (3.8 h in the stress week), but Tier-1 loads stay on through islanding.
- **Frequency support is honest but small.** GridSetu fast response from 25% of R3 feeders (~6 MW) trims SPS shedding by ~5 MW and barely moves the islanding nadir. The fairness and islanding story is stronger than the frequency story.

## Key assumptions (all in `config/city.yaml`)
- **Feeder:** 420 households, 35 micro-enterprises, 340 kW peak, **300 kW transformer rating**. This is the overloaded-DT case RDSS targets.
- **Tier-1 reserve:** 2 h of Tier-1 energy is held in the battery and never used for anything but islanding.
- **Protection trips:** probabilistic above the rating, 1 h to restore.
- **DISCOM relief:** requests are the regional domestic shed fraction times the feeder's load. GridSetu must deliver at least 95% of a request or it is rotation-tripped like any other feeder. This stops it free-riding on neighbouring feeders.
- **Market:** ATC-based market splitting. Real time assumes perfect intraday foresight for fast units, which is slightly optimistic. Thermal units stay within ±5 MW of their day-ahead schedule.
- **Forecasts:** trained on 8 synthetic history weeks, with conformal calibration so the q10–q90 band hits its nominal 80%.

## Control-room dashboard (Phase 3)

```bash
pip install -r requirements.txt            # adds fastapi, uvicorn, orjson
cd web && npm install && npm run build && cd ..
gridsetu serve                             # or: python -m gridsetu serve   ->  http://127.0.0.1:8000
```

The first start simulates the reference scenario (3 seeds, about 90 s) and caches it under `.cache/runs/`. Every later start is instant.

For front-end work, run `gridsetu serve` in one terminal and `cd web && npm run dev` in another (http://localhost:5173, with the API proxied). `npm run build:demo` writes a single self-contained HTML file with a bundled data snapshot to `web/dist-demo/`, for sharing without a server.

**Pages**
- **Control room:** the animated city, the pilot feeder, and live KPIs.
- **City and market:** dispatch, clearing prices, interties, shedding by class, planning factors, and the isolated microgrid.
- **Pilot feeder:** import, unserved load, battery, forecast bands, and the Reliability Reserve with a *Publish to ADMS* action.
- **Households:** a virtualised table of all 420 homes plus the curtailment log.
- **Protection:** the PMU-rate frequency event.
- **Architecture:** the five layers, live at the playhead.
- **Scenario lab:** change battery, transformer, comms and demand-response settings and rerun.

**How it stays smooth**

*Data*
- Data flows one way. TanStack Query holds server data and a small Zustand store holds UI state. Components read through selectors and change state only through store actions.
- Each run is keyed by a content hash, so every payload URL is immutable. Payloads are serialised once with orjson and gzipped once, then served with `Cache-Control: immutable` and a strong ETag.
- The browser prefetches every payload of the active run while idle. Page and week switches therefore make no network calls.
- A whole week of animation (every household's state at every step) arrives in one ~35 kB request.

*Animation and rendering*
- One `requestAnimationFrame` clock drives the city canvas, the feeder canvas and the chart playheads. They read the playhead without triggering React renders; React only re-renders when the 15-minute step changes. Measured playback in headless Chromium runs at a steady 16.7 ms per frame.
- Charts are canvas (uPlot) with synchronised cursors and click-to-seek.
- The household table is virtualised, and search input is deferred with `useDeferredValue`.
- Lenis smooth scrolling runs on the GSAP ticker. GSAP also handles number tweens and the feeder intro.
- Micro-interactions last 100–150 ms, and `prefers-reduced-motion` is respected.

*Assets*
- Icons are one inline SVG sprite (59 Lucide icons), with no icon font.
- Fonts (Inter, Instrument Serif, Source Code Pro) are self-hosted via Fontsource, so nothing is fetched from third parties.
- UI components are shadcn-style (Radix primitives with Tailwind v4 tokens), in `web/src/components/ui`.

## Next phases
- **Phase 2:** multi-feeder fleet at the city level, PyPSA for unit commitment, and an OSMnx city map.
- **Phase 3 (done):** FastAPI + React control room, mock ADMS ingest, scenario lab. Still to do: a TimescaleDB/MQTT live replay.
- **Phase 4:** operator copilot using the Claude API with tool calls into this simulator (Ollama fallback), plus 3D city visualisation.
