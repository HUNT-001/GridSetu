<div align="center">

# GridSetu

**A neighbourhood reliability reserve for India's low-income feeders, built to plug into Schneider Electric's grid, not replace it.**

Schneider Electric Yuva Yodha Energy Tech Hackathon · Challenge 03: Grid reliability and renewable intermittency

[Live demo](https://claude.ai/artifact/212NufWD9xhznBwTKwGAYc) · [Run it locally](#run-it-locally) · [How it works](#how-it-works) · [Results](#results) · [City-wide fleet](#city-map-and-fleet)

![Python](https://img.shields.io/badge/python-3.11-3776AB)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688)
![React](https://img.shields.io/badge/UI-React%2019-61DAFB)
![Tests](https://img.shields.io/badge/tests-45%20passing-2DD4BF)
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
- **Unit commitment:** which plants run, not just how hard (below).

![Unit commitment: on/off schedule per plant, week cost and R3 price against the linear market](docs/images/unit-commitment.png)

The unit-commitment card solves the day-ahead schedule as a mixed-integer problem with PyPSA and HiGHS. Plants can be switched off, but a start costs money and a started plant must stay on for its minimum time. The card compares that schedule with the linear market used everywhere else.

### City map and fleet

![Thursday evening on the city map with GridSetu on half of the R3 feeders](docs/images/fleet-map.gif)

<sub>Thursday of the stress week from 16:00, with GridSetu on 10 of the 20 R3 feeders (teal rings). When coal unit G1B trips at 18:00 the DISCOM starts rotating feeders off. Feeders without GridSetu go dark with their clinic or school (red cross); GridSetu feeders either meet the request or island their critical loads (teal cross).</sub>

The pilot is one of 20 domestic feeders in R3. This page runs GridSetu on none of them, some, or all:
- **Adoption level:** 0, 25, 50, 75 or 100%. The rollout starts with overloaded transformers, then feeders with a clinic or school.
- **Map:** plants, the 220 kV lines with power flowing, R1 and R2 load zones that dim with shedding, and each R3 feeder's village. Every village shows its state at the playhead. Hover for details; click to open the feeder's week.
- **What each step buys:** critical-site hours, dark home-hours, unserved energy and overload trips at every adoption level.
- **All 20 feeders:** homes, transformer loading, critical sites, and outcomes under both controllers.

<img src="docs/images/fleet-map.png" alt="City map page with KPIs, map and feeder detail" width="62%"> <img src="docs/images/fleet-curves.png" alt="Adoption curves" width="36%">

Streets are generated by default. `python -m gridsetu fetch-osm` downloads the real streets of Coimbatore's south-eastern periphery from OpenStreetMap on a machine with internet access, and the next server start draws them instead.

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
- **Scenario lab:** change the battery, transformer rating, critical-load reserve, control-message loss, industrial DR, the forced outage or solar-hour irrigation. The simulator reruns in about 30 seconds with live progress, and the result can be opened on every page. Lab runs use one seed, so they are compared against a one-seed reference with the same weather and loads.

### Operator copilot

![Copilot answering a what-if about a larger battery](docs/images/copilot.png)

Press **Ctrl K** (or **/**) to open a chat panel docked beside the dashboard. It answers from the simulation through tools and moves the dashboard to what it is describing. Ask it:
- **What happened at a time:** "What happened at Fri 18:30?"
- **Why a price moved:** marginal unit, scarcity at the ceiling, or congestion between regions.
- **About one household:** "How was HH-042 treated?"
- **To test a change:** "What if the battery were 400 kWh?" runs the simulator and compares the result against the reference.
- **For a written note:** "Draft a note for the DISCOM about Thursday evening."

It works with four interchangeable backends, tried in this order:

| Backend | When it is used | What you need |
|---|---|---|
| **Claude** (Anthropic Messages API, tool use, streaming, prompt caching) | `ANTHROPIC_API_KEY` is set | An API key. Model via `GRIDSETU_MODEL` (default `claude-sonnet-5`) |
| **OpenAI-compatible** (any chat API with tool calling) | `GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY` or `OPENAI_API_KEY` is set, or `GRIDSETU_LLM_BASE_URL` points at a server such as vLLM or LM Studio | A key; Groq, Gemini and OpenRouter have free tiers. Model via `GRIDSETU_LLM_MODEL` |
| **Ollama** (local model with tool calling) | No key, and Ollama is running | `ollama pull qwen2.5:7b-instruct`. Model via `GRIDSETU_OLLAMA_MODEL` |
| **Offline** (rule-based, no model) | None of the above | Nothing. It understands a fixed set of questions |

Put keys in a `.env` file in the project folder; [`.env.example`](.env.example) lists every setting. Force a backend with `GRIDSETU_COPILOT=claude|openai|ollama|offline`. Whichever backend runs, every figure in an answer comes from a tool call. The model never computes or estimates numbers itself.

### Live telemetry replay

![Live replay ticker](docs/images/live-ticker.png)

**Live** in the playback bar makes the server replay the run as the messages a control room would receive, and the server drives the playhead. Each 15-minute interval carries:
- F07 SCADA: state, import, battery power and state of charge.
- Smart-meter reads, after mMTC packet loss.
- City state: demand, shedding, prices.
- Reliability Reserve publications.

Set `GRIDSETU_MQTT=host:1883` and the same messages are also published to an MQTT broker. Or publish without the dashboard:

```bash
python -m gridsetu replay --broker 127.0.0.1:1883 --start "Thu 17:00" --speed 4
# topics: gridsetu/<run>/city/state, gridsetu/<run>/feeder/F07/{scada,ami,reserve}
```

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

### A copilot turn

```mermaid
sequenceDiagram
    autonumber
    participant O as Operator
    participant P as Copilot panel
    participant A as FastAPI /copilot/chat
    participant M as Claude / Ollama / offline
    participant T as Tools
    participant S as Run cache + simulator

    O->>P: "Why is the price so high at Thu 19:00?"
    P->>A: question + context (run, week, playhead, page)
    A->>M: system prompt, context, tool schemas
    M->>A: tool call explain_price(time="Thu 19:00")
    A->>T: run tool
    T->>S: read city payload at step 364
    S-->>T: prices, units, interties, shedding
    T-->>A: result + dashboard action (seek to Thu 19:00)
    A-->>P: tool_start, ui:seek, tool_end (SSE)
    P->>P: store action moves the playhead
    A->>M: tool result
    M-->>A: answer text, streamed
    A-->>P: text deltas (SSE), then done
```

### The fleet study

```mermaid
flowchart LR
    CITY["City week<br/>market, shedding, SPS"] --> SIG["Per-feeder signals<br/>curtailment share · rotation group · SPS block"]
    CFG["20 R3 feeders<br/>homes · transformer · solar<br/>clinic / school / pump"] --> SIM
    SIG --> SIM["Each feeder simulated twice<br/>baseline and GridSetu"]
    SIM --> RANK["Rollout order<br/>overloaded transformers first,<br/>then clinics and schools"]
    RANK --> CURVE["Adoption 0 / 25 / 50 / 75 / 100 %<br/>top-k feeders use their GridSetu run"]
    CURVE --> OUT["Critical-site hours · dark home-hours<br/>unserved energy · overload trips · battery kWh"]
    SIM --> MAP["City map<br/>state of every feeder at every step"]
```

A DISCOM request is always a share of a feeder's own load, and a GridSetu feeder that cannot meet it is tripped like any other. No feeder can push its burden onto a neighbour, so each feeder's two runs can be combined freely into any adoption level.

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

### City-wide fleet (Phase 2)

All 20 R3 domestic feeders (about 8,700 homes; 18 of 20 transformers overloaded at the evening peak), totals for the stress week:

| GridSetu on | Critical-site hours dark | Home-hours dark | Unserved energy | Overload trips | Batteries |
|---|--:|--:|--:|--:|--:|
| 0 of 20 feeders | 278 | 41,041 | 27,012 kWh | 13 | – |
| 5 (25%) | 184 | 38,079 | 25,008 kWh | 8 | 1,040 kWh |
| 10 (50%) | 102 | 34,465 | 22,546 kWh | 2 | 2,020 kWh |
| 15 (75%) | 44 | 32,422 | 21,338 kWh | 0 | 3,020 kWh |
| 20 (100%) | 0 | 30,394 | 20,205 kWh | 0 | 4,080 kWh |

- **Critical loads:** the first quarter of the rollout removes a third of the critical-site outage hours, because it targets the most overloaded feeders with clinics first. Full adoption removes all of them.
- **Homes dark:** falls by only 26% at full adoption in the stress week. The 30-hour generation shortfall is larger than feeder batteries can cover, so most feeders are still rotated off for part of it.
- **Normal week:** at 75% adoption no home is dark at all (19,315 home-hours at 0%), because transformer overload trips, the main cause of outages in a normal week, disappear.

### Unit commitment study

A day-ahead mixed-integer schedule (PyPSA with HiGHS) against the linear market, stress week:
- **Coal stays on all week.** Stopping a coal unit overnight saves less than its ₹9 lakh restart.
- **Gas is started 8 times** for evening peaks and runs 49 hours, against 57 in the linear market.
- **Peaks cost more than the linear market assumes.** A ₹60,000 start and a 20 MW minimum load make the gas unit too expensive for short spikes, so the schedule sheds 26 MWh more (363 against 337 MWh) and costs ₹11 lakh (0.6%) more. A tighter solver gap does not change this. Flexible demand, such as a GridSetu reserve, is worth more than the linear market suggests.

Feeder results use the linear market so they stay comparable with Phase 1.

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

# optional: copilot keys (Claude, or a free Groq / Gemini / OpenRouter key)
cp .env.example .env                                  # then edit .env

# start the API and the dashboard
python -m gridsetu serve                              # http://127.0.0.1:8000
```

The first start simulates the reference scenario (3 seeds, plus the 20-feeder fleet and unit-commitment studies, about 4 minutes) and caches it in `.cache/runs/`. Later starts are instant.

| Command | What it does |
|---|---|
| `python -m gridsetu serve` | API plus built dashboard on port 8000 |
| `python -m gridsetu run --seeds 3` | Batch study: charts, CSVs and `outputs/summary.txt` |
| `pytest -q` | 45 tests: physics and safety invariants, unit commitment, the fleet and the map, copilot tools, the Claude and OpenAI-compatible tool loops, offline answers and replay |
| `python -m gridsetu fetch-osm` | Download real OpenStreetMap streets for the city map (`--bbox south,west,north,east` to choose the area) |
| `python -m gridsetu replay --broker host:1883` | Publish a run as live telemetry to MQTT |
| `cd web && npm run dev` | Dashboard with hot reload on port 5173, with the API proxied |
| `cd web && npm run build:demo` | One self-contained HTML file with a data snapshot, for sharing without a server |

**API**

| Route | Returns |
|---|---|
| `GET /api/v1/runs` | Runs and their status |
| `POST /api/v1/runs` | Starts a scenario-lab run from `{"knobs": {...}}` |
| `GET /api/v1/runs/{id}/progress` | Live progress as Server-Sent Events |
| `GET /api/v1/runs/{id}/{resource}?week=stress` | `meta`, `summary`, `city`, `feeder`, `households`, `wams`, `island`, `network`, and on runs with the city-wide studies `fleet`, `uc` and `map` |
| `POST /api/v1/adms/ingest` | Mock ADMS/DERMS ingest of a Reliability Reserve |
| `GET /api/v1/copilot/status` | Which copilot backend is active |
| `POST /api/v1/copilot/chat` | Copilot turn as Server-Sent Events: text deltas, tool calls, dashboard actions |
| `GET /api/v1/live/stream?week=&start=&speed=` | Live telemetry replay as Server-Sent Events |

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
│   ├── fleet.py              the 20 R3 feeders under both controllers, adoption curve
│   ├── uc.py                 day-ahead unit commitment (PyPSA MILP) against the linear market
│   ├── citymap.py            city map geometry: generated streets or OpenStreetMap (fetch-osm)
│   ├── envfile.py            .env loader
│   ├── runner.py, plots.py   batch study and deck charts
│   ├── api/                  FastAPI service and payload packing
│   └── copilot/              copilot tools, Claude / OpenAI-compatible / Ollama / offline providers, live replay, MQTT
├── web/                      React 19, Vite, Tailwind v4, Radix/shadcn-style components
│   └── src/
│       ├── components/city/  canvas city scene, feeder inset, playback
│       ├── components/fleet/ canvas city map for the 20-feeder fleet
│       ├── components/       uPlot charts, virtualised table, UI primitives
│       ├── components/copilot/  chat panel and safe Markdown renderer
│       ├── lib/              API client, query hooks, UI store and clock, copilot and live stores
│       └── pages/            control room, city, feeder, city map, households, protection, architecture, lab
├── tests/                    invariants, Phase 2 studies, copilot
├── .env.example              copilot keys and settings
└── docs/images/              screenshots and animations used in this README
```

**Stack**

| Area | Tools |
|---|---|
| Simulation | Pyomo and PyPSA with HiGHS, pandapower, LightGBM, NumPy, pandas |
| Service | FastAPI, orjson, Server-Sent Events |
| Copilot | Anthropic Messages API (tool use), OpenAI-compatible chat APIs, Ollama, paho-mqtt |
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
- Feeder results use the linear market. Unit commitment is a separate study, and its schedule leaves ramp limits out. Real time assumes perfect foresight for fast units within each day.
- In the fleet study, feeders respond to the city but the city does not respond to them: the fleet's reserve is not yet offered back into the market.
- The frequency model is a two-area aggregate, not a full dynamic network model.
- The forecasts have not been backtested on real feeder data.

## Roadmap

- [x] **Phase 1:** multi-layer simulator, market, feeder controller, protection studies, tests
- [x] **Phase 2:** city-wide GridSetu fleet, PyPSA unit commitment, city map with OpenStreetMap streets
- [x] **Phase 3:** control-room dashboard, API, mock ADMS ingest, scenario lab
- [x] **Phase 4:** operator copilot (Claude, Ollama or offline) with tool calls into the simulator; live telemetry replay with an MQTT bridge
- [ ] Next: offer the fleet's aggregated Reliability Reserve into the market, so the city schedules around it
- [ ] Later: TimescaleDB history for the replay stream

---

<div align="center">
<sub>Built by Vakkalagadda Tanush Pavan (<a href="https://github.com/HUNT-001">@HUNT-001</a>) · Amrita Vishwa Vidyapeetham, Coimbatore</sub>
</div>
