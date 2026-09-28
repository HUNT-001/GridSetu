<div align="center">

# GridSetu

**A neighbourhood reliability reserve for India's low-income feeders, built to plug into Schneider Electric's grid, not replace it.**

Schneider Electric Yuva Yodha Energy Tech Hackathon · Challenge 03: Grid reliability and renewable intermittency

[Live demo](https://claude.ai/artifact/212NufWD9xhznBwTKwGAYc) · [Run it locally](#run-it-locally) · [How it works](#how-it-works) · [Results](#results)

![Python](https://img.shields.io/badge/python-3.11-3776AB)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688)
![React](https://img.shields.io/badge/UI-React%2019-61DAFB)
![Tests](https://img.shields.io/badge/tests-15%20passing-2DD4BF)
![Data](https://img.shields.io/badge/data-synthetic%20simulation-F5A623)

![Power flowing through the simulated city from 13:00 to midnight on the stress day](docs/images/power-flow.gif)

<sub>Thursday of the stress week, 13:00 to midnight. Power flows from the plants along the 220 kV ring into three districts. At 18:00 coal unit G1B trips, prices hit the ₹10 ceiling, and the DISCOM starts shedding load (amber wash, dark windows). Railways and municipal water stay on.</sub>

</div>

> **Everything here is simulation on synthetic data, not field measurement.** Every input is an engineering assumption in [`config/city.yaml`](config/city.yaml) and can be changed there.

---

## Contents

- [The problem](#the-problem)
- [What GridSetu does](#what-gridsetu-does)
- [The dashboard](#the-dashboard)
- [How it works](#how-it-works)
- [Results](#results)
- [Run it locally](#run-it-locally)
- [Project structure](#project-structure)
- [Modelling assumptions](#modelling-assumptions)
- [Limitations](#limitations)
- [Roadmap](#roadmap)

---

## The problem

On a peri-urban feeder, rooftop solar fades just as the evening demand peak arrives (17:30 to 19:30). The distribution transformer overloads and trips. On a stressed grid day the DISCOM also sheds whole feeders in rotation. When that happens every home goes dark, including the health sub-centre, the school and the water pump.

![Pilot feeder demand against solar over one day, with the evening reliability gap shaded](docs/images/evening-ramp-gap.png)

Schneider's EcoStruxure ADMS/DERMS already dispatches DERs it has a metered, contracted relationship with. A cooperatively shared community battery serving 420 unrelated low-income households has no single customer of record, so it never becomes dispatchable. GridSetu is the missing origination layer: it turns that feeder's shared assets into one forecasted, confidence-scored **Reliability Reserve** and publishes it to the ADMS through its own interfaces.

## What GridSetu does

| | Baseline feeder | Feeder with GridSetu |
|---|---|---|
| Evening peak | Transformer overloads and trips | Battery shaves the peak under the rating |
| DISCOM asks for relief | Whole feeder tripped in rotation | Relief delivered from battery, then Tier-3, then consented Tier-2 loads |
| Relief not possible | Feeder dark | Feeder tripped, **critical loads islanded on the battery** |
| Who carries curtailment | Everyone, all at once | Rotated by a fairness ledger; no home twice in a row |
| What the control room sees | Nothing until it fails | A reserve with kW, duration, confidence and cost, updated at T−24h, T−1h, T−15min, real time and post-event |

**Load tiers on the pilot feeder**
- **Tier 1, critical:** health sub-centre, school, water pumping, street lighting. Never curtailed; islanded on the battery if the feeder trips.
- **Tier 2, important:** micro-enterprise motors. Shifted only with prior opt-in (26 of 35 workshops).
- **Tier 3, flexible:** AC boost, water heating, two-wheeler charging. Paused in 15-minute slots by the fairness ledger, and any household can override.

![Baseline and GridSetu feeders side by side through the Thursday evening](docs/images/feeder-rotation.gif)

<sub>The same 420 homes through Thursday evening. Left: the baseline feeder is tripped in rotation and every home goes dark. Right: GridSetu pauses Tier-3 appliances (teal outlines), rotating which homes carry it. When the DISCOM's request exceeds what the feeder can give, it is tripped too, but the clinic, school, pump and street lights stay on the battery.</sub>

---

## The dashboard

A React control room over a FastAPI service. Every page is driven by one shared playhead, so scrubbing the week moves the city animation, the feeder, every chart cursor and the live readouts together.

### Control room

![Control room at 18:00 on the stress day](docs/images/control-room.png)

- **City scene (canvas):** plants, the 220 kV ring with moving dots whose speed and direction follow the MW, and districts whose windows go dark in proportion to the load shed in that class. The sky follows the simulated hour and cloud cover.
- **Pilot feeder inset:** 420 homes side by side, baseline against GridSetu.
- **Month KPIs:** tween to their new values when a different run is selected.
- **Playback:** Space plays or pauses. Arrow keys step 15 minutes, and Shift+arrow steps an hour. Clicking any chart seeks there.

<details>
<summary><b>Light theme and phone layout</b></summary>

<br>

<img src="docs/images/control-room-light.png" alt="Control room in light theme" width="72%"> <img src="docs/images/mobile.png" alt="Control room at phone width" width="22%">

</details>

### City and market

![City dispatch, market prices, intertie loading, shedding by class and planning factors](docs/images/city-market.png)

Dispatch by source against net demand, day-ahead market clearing price per bid area, intertie loading, energy not served by consumer class, and the planning tables:
- **Load classes:** load, demand and diversity factors.
- **Plants:** capacity and plant use factors.
- **Isolated microgrid:** legacy against GridSetu dispatch for the off-grid hamlet.

### Pilot feeder and the Reliability Reserve

![Feeder import, unserved load, battery, forecast bands and the five-stage Reliability Reserve](docs/images/pilot-feeder.png)

The Reliability Reserve card shows what GridSetu tells the control room about each evening window at five stages. **Publish to ADMS** posts it to a mock EcoStruxure ADMS/DERMS ingest endpoint, shaped as an IEC 61968-5 DER group forecast, and shows the acknowledgement.

### Households and fairness

![Virtualised household table with per-home curtailment hours](docs/images/households.png)

All 420 homes and the complete curtailment log (about 6,000 rows) in virtualised, sortable, searchable tables. Clicking a home opens its week as a strip: supplied, Tier-3 paused, or dark, under both scenarios.

### Protection (WAMS)

![Frequency after the generator trip at PMU resolution](docs/images/protection-wams.png)

The first minute after the forced outage at 50 frames per second:
- **Case A, generator trip:** the national tie picks up the loss and the special protection scheme sheds load.
- **Case B, islanding:** the city is cut off from the national grid and under-frequency relays shed load in stages.

### Architecture and scenario lab

<img src="docs/images/architecture.png" alt="Five grid layers with live values at the playhead" width="49%"> <img src="docs/images/scenario-lab.png" alt="Scenario lab sliders and comparison table" width="49%">

- **Architecture:** the five grid layers, each showing what it is doing at the playhead.
- **Scenario lab:** change the battery, transformer rating, critical-load reserve, control-message loss, industrial DR, the forced outage or solar-hour irrigation. The simulator reruns in about 30 seconds with live progress, and the result can be opened on every page.

---

## How it works

### Grid architecture

```mermaid
flowchart TB
    ADMS["Schneider EcoStruxure ADMS / DERMS"]

    subgraph SLICE["Slice layer: communication slices"]
        direction LR
        U["URLLC<br/>protection, PMUs"] ~~~ M["mMTC<br/>420 smart meters"] ~~~ C2["2G/4G<br/>control, 3 retries"] ~~~ E["eMBB<br/>dashboards"]
    end

    subgraph MGMT["Management and monitoring layer"]
        direction LR
        FC["Quantile forecasts<br/>q10 · q50 · q90"] --> RES["Uncertainty engine<br/>+ Reliability Reserve"] ~~~ KPI["Planning factors<br/>and KPIs"]
    end

    subgraph CTRL["Control layer"]
        direction LR
        MKT["Day-ahead market<br/>+ real-time redispatch"] --> SHED["Priority load<br/>shedding"] --> EDGE["Feeder edge controller<br/>Tier 1 / 2 / 3"] ~~~ PROT["SPS · UFLS"]
    end

    subgraph INFRA["Infrastructure layer"]
        direction LR
        AMI["AMI meters"] ~~~ BAT["200 kWh / 100 kW<br/>battery"] ~~~ PV["Rooftop +<br/>community PV"] ~~~ PMU["PMUs, 50 fps"]
    end

    subgraph POWER["Power layer"]
        direction LR
        GEN["Plants +<br/>national import"] --> TX["220 kV ring"] --> DIST["33 / 11 kV<br/>substations"] --> LOAD["6 consumer<br/>classes"]
    end

    ADMS <-- "Reliability Reserve up · requests and prices down" --> SLICE
    SLICE <--> MGMT
    MGMT <--> CTRL
    CTRL <--> INFRA
    INFRA <--> POWER
```

### How power reaches a home

```mermaid
flowchart LR
    subgraph Generation
        G1["Coal G1A + G1B<br/>250 MW"]
        G2["Gas G2<br/>80 MW"]
        H1["Hydro H1<br/>30 MW"]
        S1["Solar park S1<br/>100 MW"]
        W1["Wind W1<br/>60 MW"]
        NAT["National grid tie<br/>≤ 90 MW"]
    end

    subgraph Transmission["220 kV ring"]
        R1(("R1<br/>North Industrial"))
        R2(("R2<br/>Central Urban"))
        R3(("R3<br/>South Peri-urban & Agri"))
    end

    G1 --> R1
    NAT --> R1
    G2 --> R2
    H1 --> R3
    S1 --> R3
    W1 --> R3
    R1 <-- "120 MW ATC" --> R2
    R2 <-- "50 MW ATC" --> R3
    R1 <-- "30 MW ATC" --> R3

    R1 --> C1["Industrial · traction · worker housing"]
    R2 --> C2["Commercial · domestic · traction · municipal"]
    R3 --> SUB["33/11 kV substation"]
    R3 --> C3["Irrigation · domestic · municipal"]
    SUB --> F07["Pilot feeder F07<br/>300 kW transformer"]
    F07 --> HH["420 households<br/>35 micro-enterprises"]
    F07 --> T1["Clinic · school · pump · street lights"]
    BAT["Community battery<br/>+ 60 kWp PV"] --> F07

    ISL["Kallar hamlet<br/>isolated: PV + battery + diesel"]
```

### One simulated week

```mermaid
flowchart TD
    CFG["config/city.yaml"] --> WX["Weather<br/>solar geometry · monsoon clouds · wind"]
    WX --> LD["Loads<br/>6 classes × 3 regions · 420 households"]
    LD --> HIST["8 synthetic history weeks"]
    HIST --> QR["LightGBM quantile regression<br/>+ conformal calibration"]

    LD --> DA["Day-ahead market<br/>96 blocks/day · Pyomo + HiGHS<br/>regional price = dual of power balance"]
    DA --> RT["Real-time redispatch<br/>forced outage the DA market did not see"]
    RT --> SHED["Priority load shedding<br/>irrigation → domestic → commercial → industrial<br/>traction and municipal never"]

    SHED --> SIG["Feeder signals<br/>price · curtailment request · rotation trip · SPS"]
    QR --> PLAN["Feeder day-ahead LP<br/>battery schedule on q50"]
    QR --> UNC["Uncertainty engine<br/>Monte Carlo shortfall risk → reserve buffer"]
    UNC --> PLAN

    SIG --> BASE["Baseline feeder<br/>no battery, tripped on request"]
    SIG --> EDGE["GridSetu edge controller<br/>every 15 minutes"]
    PLAN --> EDGE

    RT --> PF["AC power flow<br/>pandapower"]
    RT --> WAMS["Frequency event<br/>two-area model at PMU rate"]
    WX --> ISL["Isolated microgrid"]

    BASE --> OUT["Metrics · charts · API payloads"]
    EDGE --> OUT
    PF --> OUT
    WAMS --> OUT
    ISL --> OUT
```

### The edge controller, every 15 minutes

```mermaid
flowchart TD
    START(["New 15-minute interval"]) --> SPS{"SPS signal?"}
    SPS -- "yes, delivered on URLLC" --> RELIEF["Give fast relief:<br/>import cap = 0"]
    SPS -- "yes, message lost" --> TRIP
    SPS -- "no" --> REQ{"DISCOM curtailment<br/>request?"}

    REQ -- "no" --> PEAK["Follow day-ahead battery plan<br/>keep import under 97% of rating"]
    REQ -- "yes, lost after 3 retries" --> ROT{"Feeder in this<br/>rotation group?"}
    ROT -- "yes" --> TRIP
    ROT -- "no" --> PEAK
    REQ -- "yes, delivered" --> CAN{"Battery + Tier 3 + Tier 2<br/>≥ 95% of request?"}
    CAN -- "yes" --> CAP["Meet the cap"]
    CAN -- "no" --> ROT2{"Feeder in this<br/>rotation group?"}
    ROT2 -- "yes" --> TRIP["Feeder tripped"]
    ROT2 -- "no" --> CAP

    RELIEF --> ORDER
    CAP --> ORDER
    PEAK --> ORDER["Dispatch in order:<br/>1. battery above the Tier-1 island reserve<br/>2. Tier 3 via fairness ledger<br/>3. consented Tier 2"]
    ORDER --> LEDGER["Fairness ledger:<br/>least-curtailed homes first,<br/>never two intervals running,<br/>overrides honoured"]

    TRIP --> ISLAND["Island Tier 1 on the battery<br/>clinic · school · pump · lights"]
    LEDGER --> LOG(["Log state, update reserve, next interval"])
    ISLAND --> LOG
```

### Reliability Reserve lifecycle

```mermaid
sequenceDiagram
    autonumber
    participant F as Forecast engine
    participant U as Uncertainty engine
    participant O as Feeder planner
    participant C as Edge controller
    participant A as ADMS / DERMS

    F->>U: q10 / q50 / q90 of net load and PV
    U->>O: reserve buffer + shortfall risk
    O->>A: T−24h reserve (kW, duration, confidence, cost)
    C->>A: T−1h update from a persistence nowcast
    C->>A: T−15min dispatch-ready reserve
    A->>C: curtailment request during 17:30 to 19:30
    C->>C: battery → Tier 3 (ledger) → Tier 2
    C->>A: real-time delivered kW
    C->>A: post-event verified outcome + ledger update
```

### Front-end data flow

```mermaid
flowchart LR
    SIM["Simulator run"] --> PACK["Columnar payloads<br/>orjson + gzip, once"]
    PACK --> API["FastAPI<br/>immutable URLs · ETag · SSE progress"]
    API --> RQ["TanStack Query cache<br/>idle prefetch of every payload"]
    RQ --> SEL["Selectors"]
    ZS["Zustand UI store<br/>week · run · variant · playhead"] --> SEL
    SEL --> VIEW["Pages · charts · tables"]
    CLOCK["Single rAF clock"] --> ZS
    CLOCK -. "reads playhead, no re-render" .-> CANVAS["City + feeder canvases<br/>chart playheads"]
    VIEW -- "actions" --> ZS
```

Data flows one way. The server payloads are immutable, so each is fetched once and every week or page switch after that is served from the cache. The canvases and chart playheads read the clock outside React; React re-renders only when the playhead crosses a 15-minute step. Measured playback in headless Chromium held a steady 16.7 ms per frame.

---

## Results

Monthly composite of three normal weeks and one stress week (a forced 125 MW coal outage and two overcast monsoon days), averaged over three weather and load seeds.

![Baseline against GridSetu on four metrics](docs/images/results-baseline-vs-gridsetu.png)

| Metric, per month | Baseline | GridSetu | Change | + city DR |
|---|--:|--:|--:|--:|
| Unserved energy, 17:30 to 19:30 | 2,713 kWh | 546 kWh | −80% | 403 kWh |
| Unserved energy, all hours (net of rebound) | 3,825 kWh | 811 kWh | −79% | 572 kWh |
| Critical-load outage | 13.6 h | 0.0 h | −100% | 0.0 h |
| Whole-feeder outage | 13.6 h | 2.9 h | −79% | 2.0 h |
| Transformer overload trips | 10 | 0 | −100% | 0 |
| Peak drawn from the grid | 340 kW | 291 kW | −14% | 291 kW |
| Battery cycles | – | 17.6 | | 17.6 |

*+ city DR* adds city-level solar-hour irrigation and 15 MW of industrial demand response. Seed ranges: baseline evening unserved energy 2,315 to 3,389 kWh; GridSetu 452 to 617 kWh.

**Other studies (stress week)**
- **Fairness:** all 420 homes shared Tier-3 curtailment, at most 4.0 hours each. Gini of paused hours 0.04, with 654 user overrides honoured.
- **Forecast:** the q10 to q90 band covered the actual 83% of the time (nominal 80%), with a median error of 3.9%.
- **City:** energy not served fell from 723 MWh to 494 MWh with solar-hour irrigation and industrial DR. Traction, municipal, commercial and industrial loads were never shed.
- **Protection:** in Case A the frequency nadir was 49.70 Hz and GridSetu's fast response cut special-protection shedding from 62 to 57 MW. In Case B (islanding) the nadir was 49.16 Hz, with two under-frequency stages operating.
- **Isolated microgrid:** unserved energy fell from 613 to 114 kWh per week, diesel run hours from 139 to 116, and wasted solar from 441 to 22 kWh.
- **AC power flow:** the most-loaded 220 kV line peaked at 110% of its thermal rating in 8 samples during the outage. Feeder voltages stayed within 0.99 to 1.03 pu.
- **Planning factors:** city peak 474 MW, load factor 0.70, reserve margin at peak 1.9%.

**Where the model disagrees with earlier estimates**
- **Solar utilisation:** the earlier figure of 61% to 84% is not supported. Daytime load on this feeder always exceeds its 150 kWp of solar, so both scenarios already use about 100% of it.
- **Stress events:** during a 30-hour, 125 MW shortfall a 200 kWh battery cannot supply all the relief requested. The feeder is still tripped for part of the event, but its critical loads stay on.
- **Frequency support:** about 6 MW of fast response from a quarter of the peri-urban feeders is real but small at city scale. Fairness and critical-load protection are the stronger results.

---

## Run it locally

**Requirements:** Python 3.11, Node 20 or newer. About 2 GB of RAM; no GPU needed.

```bash
git clone https://github.com/HUNT-001/gridsetu.git
cd gridsetu
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# build the dashboard once
cd web && npm install && npm run build && cd ..

# start the API and the dashboard
python -m gridsetu serve                              # http://127.0.0.1:8000
```

The first start simulates the reference scenario (3 seeds, about 90 seconds) and caches it in `.cache/runs/`. Later starts are instant.

| Command | What it does |
|---|---|
| `python -m gridsetu serve` | API plus built dashboard on port 8000 |
| `python -m gridsetu run --seeds 3` | Batch study: charts, CSVs and `outputs/summary.txt` |
| `pytest -q` | 15 invariants covering power balance, intertie limits, shedding priority, Tier-1 protection, battery limits, fairness and protection |
| `cd web && npm run dev` | Dashboard with hot reload on port 5173, with the API proxied |
| `cd web && npm run build:demo` | One self-contained HTML file with a data snapshot, for sharing without a server |

**API**

| Route | Returns |
|---|---|
| `GET /api/v1/runs` | Runs and their status |
| `POST /api/v1/runs` | Starts a scenario-lab run from `{"knobs": {...}}` |
| `GET /api/v1/runs/{id}/progress` | Live progress as Server-Sent Events |
| `GET /api/v1/runs/{id}/{resource}?week=stress` | `meta`, `summary`, `city`, `feeder`, `households`, `wams`, `island` or `network` |
| `POST /api/v1/adms/ingest` | Mock ADMS/DERMS ingest of a Reliability Reserve |

---

## Project structure

```
gridsetu/
├── config/city.yaml          every assumption: regions, plants, classes, feeder, comms, protection
├── src/gridsetu/
│   ├── weather.py            solar geometry, monsoon cloud cover, wind, day-ahead weather forecast
│   ├── profiles.py           class load curves, 420-household feeder, synthetic history
│   ├── forecast.py           LightGBM quantile regression with conformal calibration
│   ├── market.py             day-ahead market splitting and real-time redispatch (Pyomo + HiGHS)
│   ├── feeder.py             feeder planner LP, edge controller, islanding, Reliability Reserve
│   ├── reserve.py            uncertainty engine and the reserve object
│   ├── fairness.py           rotation ledger
│   ├── comms.py              communication slices
│   ├── network.py            220/33/11 kV AC power flow (pandapower)
│   ├── wams.py               two-area frequency dynamics, SPS and UFLS
│   ├── island.py             isolated solar, battery and diesel microgrid
│   ├── metrics.py            load, diversity, demand, capacity and plant use factors
│   ├── runner.py, plots.py   batch study and deck charts
│   └── api/                  FastAPI service and payload packing
├── web/                      React 19, Vite, Tailwind v4, Radix/shadcn-style components
│   └── src/
│       ├── components/city/  canvas city scene, feeder inset, playback
│       ├── components/       uPlot charts, virtualised table, UI primitives
│       ├── lib/              API client, query hooks, UI store and clock
│       └── pages/            control room, city, feeder, households, protection, architecture, lab
├── tests/test_invariants.py
└── docs/images/              screenshots and animations used in this README
```

**Stack**

| Area | Tools |
|---|---|
| Simulation | Pyomo with HiGHS, pandapower, LightGBM, NumPy, pandas |
| Service | FastAPI, orjson, Server-Sent Events |
| Interface | React 19, Vite, Tailwind v4, Radix primitives (shadcn-style), TanStack Query and Virtual, Zustand, uPlot, GSAP, Lenis |
| Type and icons | Inter, Instrument Serif and Source Code Pro (self-hosted); one inline SVG sprite of Lucide icons |

---

## Modelling assumptions

All values live in [`config/city.yaml`](config/city.yaml).

- **Pilot feeder:**
  - 420 households, 35 micro-enterprises, 340 kW peak.
  - A 300 kW transformer, so the evening peak overloads it. This is the overloaded-transformer case RDSS targets.
  - Community battery 200 kWh / 100 kW, with 2 hours of Tier-1 energy held back for islanding.
- **Protection trips:** probabilistic above the transformer rating, with one hour to restore.
- **DISCOM relief:**
  - Requests equal the regional domestic shed fraction times the feeder's load.
  - GridSetu must deliver at least 95% of a request, or it is rotation-tripped like any other feeder. This stops it from free-riding on its neighbours.
- **Shedding order:** revenue-driven, as at a cash-strapped DISCOM. Irrigation and domestic loads go first; traction and municipal are never shed.
- **Market:** ATC-based market splitting with a ₹10/kWh exchange ceiling. Thermal units stay within ±5 MW of their day-ahead schedule in real time.
- **Communications:** 15% packet loss on the 2G/4G control slice, with 3 retries.
- **Forecasts:** trained on 8 synthetic history weeks.

## Limitations

- All data is synthetic. No live DISCOM telemetry or feeder measurement was used.
- The cooperative ownership model has not had legal review.
- The market is a single-period-per-block LP without unit commitment. Real time assumes perfect foresight for fast units within each day.
- The frequency model is a two-area aggregate, not a full dynamic network model.
- The forecasts have not been backtested on real feeder data.

## Roadmap

- [x] **Phase 1:** multi-layer simulator, market, feeder controller, protection studies, tests
- [x] **Phase 3:** control-room dashboard, API, mock ADMS ingest, scenario lab
- [ ] **Phase 2:** city-wide GridSetu fleet, PyPSA unit commitment, OpenStreetMap city geometry
- [ ] **Phase 4:** operator copilot on the Claude API with tool calls into the simulator (Ollama fallback), plus MQTT/TimescaleDB live replay

---

<div align="center">
<sub>Built by Vakkalagadda Tanush Pavan (<a href="https://github.com/HUNT-001">@HUNT-001</a>) · Amrita Vishwa Vidyapeetham, Coimbatore</sub>
</div>
