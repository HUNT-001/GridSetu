# What "the feeder" physically is: two views and one proposal

Status: **for the team call, nothing changed in the model yet.** Written 25 Nov 2026 against
`origin/main` at `410274e`. Everything marked *to verify* still needs a source.

## 1. The short version

- The repo has **four** pictures of pilot feeder F07. They disagree on the voltage level, on
  how many transformers there are, on where the battery is and on where the clinic is.
- The MATLAB low-voltage (LV) model puts all 1,090 homes on **one 315 kVA transformer with
  three 600 m circuits**. At the evening peak each circuit carries about 113 kW, so the far
  end falls to about 0.8 pu. That is why voltage is out of limits in 94–99% of steps in
  every scenario. It is a property of the assumed wiring, not of the neighbourhood.
- A Tamil Nadu DISCOM would not wire 1,090 homes that way. With 3–4 smaller transformers and
  circuits of 300–350 m, the same peak load gives 0.97–0.99 pu at the far end and about a
  third of the losses (section 5).
- **The transformer rating drives the headline result.** In the baseline, the feeder trips on
  transformer overload 13 times a month (`outputs/results.json`, `pilot_feeder_monthly.baseline.overload_trips`).
  These trips exist because the aggregate rating (300 kW) is below the 340 kW evening peak.
  If the team picks a layout with more transformer capacity, most of those trips, and the
  share of GridSetu's improvement that comes from avoiding them, go away.
- My recommendation is layout **C**: three 100 kVA transformers that are overloaded as found,
  with a battery split across the three. It keeps the "overloaded transformer" case that RDSS
  targets and keeps the Python results close to today's. Section 6 gives the cost of each choice.

## 2. The four pictures in the repo today

| | Python feeder simulator | Python power flow (pandapower) | MATLAB LV model + Python twin | Simulink islanding |
|---|---|---|---|---|
| Files | `feeder.py`, `config/city.yaml` `pilot_feeder` | `network.py` | `matlab/f07_params.json`, `f07_network.m`, `run_f07.m`, `lvnetwork.py`, `matlab_export.py` | `matlab/islanding/` |
| Voltage level | none (one point) | 11 kV | 415 V | 415 V, one bus |
| What "the feeder" is | one import, one 300 kW limit, one battery | a 6 km 11 kV feeder, 5 sections of 1.2 km ACSR Rabbit, under the R3 33/11 kV substation | one 315 kVA 11/0.433 kV transformer, 3 radial circuits × 600 m × 7 buses | the "critical bus" plus 280 kW of "rest of feeder" |
| Transformers | one aggregate limit (`capacity_kw: 300`, comment: "aggregate DT thermal rating") | none (loads sit directly on 11 kV) | one, 315 kVA | none (inverter + grid source) |
| Battery + community PV | at the feeder | 11 kV node 3 | bus 0 (LV busbar); `gridsetu_distributed`: buses 4, 11, 18 | on the critical bus |
| Clinic | Tier-1 load, no location | tail node 5, all Tier-1 together | bus 4 (circuit A) | critical bus |
| School | Tier-1, no location | tail node 5 | bus 11 (circuit B) | critical bus |
| Water pump | Tier-1, no location | tail node 5 | bus 21 (end of circuit C) | critical bus |
| Rotation trip | upstream switch, all homes dark | breaker open, feeder dropped from the power flow | `energized = 0`, zero flow | "feeder breaker opens" |

Contradictions that need fixing whatever the team decides:

1. **The critical loads are in three places.** The Simulink model keeps the clinic, school,
   pump and street lights on one bus fed by the battery. The LV model puts them on three
   different circuits, each shared with about 360 homes. The power flow puts them together at
   the 11 kV tail. An island of "only the critical loads" needs them on one switchable
   section (see `HOW_IT_WORKS_PHYSICALLY.md`).
2. **The battery is in three places**: 11 kV node 3, the LV busbar, or split mid-circuit.
3. **Python limits the load, MATLAB adds the losses.** Python's 300 kW limit applies to
   customer load. MATLAB draws that load *plus* the line losses through the transformer (up
   to about 55 kW at the 18:30 peak, section 5), so its transformer loading (1.37 pu) is
   higher than the 340 kW / 315 kVA ratio suggests.
4. **300 kW vs 315 kVA.** 315 kVA × 0.95 = 299 kW, so these are consistent, but the config
   calls it kW and the MATLAB model kVA.
5. **The voltage limit.** `f07_params.json` uses ±6% (0.94–1.06 pu), marked "pending the
   Tamil Nadu clause". The TNERC Distribution Standards of Performance Regulations (Reg. 14,
   added by the 2013 amendment) appear to set **+6% / −10%** for 240 V and 415 V supply,
   *to verify against the gazette text*. With a 0.90 pu lower limit, the stress-week
   baseline has 847 violation bus-hours (71% of steps) instead of 1,869 (99.8%). Recount
   from `matlab/results/f07_stress_*_steps.csv`; not yet a committed output.
6. **Stale loss figures in the docs.** `docs/QA_BANK.md` says the split battery "cuts
   technical losses about 7%, to 2,047 kWh". `docs/TEAM_BRIEF.md` says 7% and 0.83 pu.
   `matlab/results/summary.json` says 4,480 → 4,203 kWh (−6%, or −4.7% against the
   baseline's 4,411 kWh) and 0.79 → 0.81 pu. The README agrees with `summary.json`.

### Every place that assumes a view

**One point / 11 kV view**
- `config/city.yaml`: `pilot_feeder.capacity_kw` (aggregate DT rating), `export_limit_kw` (DT reverse-power limit), `target_peak_window`
- `src/gridsetu/feeder.py`: `FEEDER_ID = "TN-CBE-PERI-11KV-F07"`; a single `cap_kw`, battery and import in `plan_day` and `simulate_feeder`
- `src/gridsetu/network.py`: `FEEDER_SECTIONS = 5`, `NODE_SHARE`, 1.2 km ACSR sections, battery and community PV at node 3, rooftop PV at node 2, Tier-1 at node 5
- `src/gridsetu/fleet.py`: "each group here is one 11 kV feeder with its own … transformer rating"
- `src/gridsetu/copilot/agent.py:40` ("300 kW transformer"), `copilot/tools.py:243,329` (`capacity_kw` = "distribution transformer rating")
- `src/gridsetu/api/engine.py:136,372` (`capacity_kw` in payloads)
- `README.md:44, 265–267` ("Pilot feeder F07, 300 kW transformer"), `README.md:727`
- `web/src/pages/architecture.tsx:70` ("220/33/11 kV substations")

**LV (one transformer, 3 × 600 m) view**
- `matlab/f07_params.json` (`topology`, `transformer`, `scenarios.storage_buses`), `matlab/f07_network.m`, `run_f07.m`, `make_figures.m`
- `src/gridsetu/lvnetwork.py`, `src/gridsetu/lvfigures.py`
- `src/gridsetu/matlab_export.py:28–29` (`N_CIRCUITS, BUSES_PER_CIRCUIT, CIRCUIT_LENGTH_M = 3, 7, 600`; `CRITICAL_BUS`), `outputs/matlab/f07_buses.csv`
- `tests/test_lvnetwork.py`
- `README.md:490–510`, `matlab/README.md`, `docs/TEAM_BRIEF.md:59–100`, `docs/QA_BANK.md:48–60`, `docs/DATA_CARD.md:91`

**Critical bus view**
- `matlab/islanding/islanding_params.m` (all Tier-1 loads on one bus, `p_feeder_rest = 280`), `README.md:512–516`

**Superseded:** my unmerged `export-matlab` branch (bus 0 = LV busbar, 420 homes). Not on main.

## 3. What a Tamil Nadu DISCOM would build for 1,090 homes

The inputs come from the repo: 1,090 homes, a 340 kW diversified evening peak (about 0.31 kW per
home at the transformer), 41 kW of Tier-1 load, a peri-urban overhead LT network.

| Design rule | Value | Source |
|---|---|---|
| Standard distribution transformer ratings | 25, 63, 100, 160, 200, 250, 315, 400, 500, 630 kVA (11/0.433 kV, IS 1180) | BIS; ratings used by TNPDCL (formerly TANGEDCO) *to verify*: the search found 100/160/250/500 kVA specs at KSEB and 25–500 kVA at CSPDCL, none from TNPDCL |
| LT voltage limit at the consumer | +6% / −10% of 240/415 V | TNERC Standards of Performance Regulations, Reg. 14 (2013 amendment), *to verify* |
| Transformer impedance | 4.5% | IS 1180, already used in `f07_params.json` |
| LT circuit length | short enough to keep the far-end drop within the limit at peak, usually a few hundred metres in built-up areas | *to verify*: no CEA or TNPDCL norm found yet |
| Loading at planning | about 80% of rating at forecast peak; RDSS counts above 100% as "overloaded" | *to verify* |

A quick drop budget: on ACSR Rabbit at 415 V and 0.95 power factor, the drop is about 0.41% per
kW·km. Evenly loaded circuits see roughly half of that at the far end. With about 4% left for the
line after the transformer drop, one circuit can carry roughly P × L ≈ 20 kW·km. A
110 kW circuit can therefore be about 180 m long; a 600 m circuit can carry about 33 kW.
Today's circuits carry 113 kW over 600 m, more than six times over budget.

## 4. Five candidate layouts

All five carry the same 340 kW at the stress-week evening peak.

| | Layout | Homes per transformer | Matches the Python 300 kW limit? |
|---|---|--:|---|
| **A** | today: 1 × 315 kVA, 3 circuits × 600 m | 1,090 | yes |
| **B** | 1 × 315 kVA, 6 circuits × 350 m | 1,090 | yes |
| **C** | 3 × 100 kVA, 3 circuits × 350 m each | about 363 | almost (3 × 100 kVA × 0.95 = 285 kW) |
| **D** | 4 × 100 kVA, 3 circuits × 300 m each | about 273 | no (380 kW: not overloaded) |
| **E** | 2 × 250 kVA, 4 circuits × 400 m each | 545 | no (475 kW: not overloaded) |

## 5. What each layout means for voltage and losses

A snapshot at the **stress-week baseline evening peak (15 Sep 18:30, 340 kW)**. The figures come from the
repo's own solver (`lvnetwork.network` and `lvnetwork.bfs`), with the load spread evenly over the
buses and every other parameter taken from `f07_params.json`. For the 100 and 250 kVA units, the
copper loss is an ASSUMPTION (1.5% and 1.1% of rating, *to verify against IS 1180 Level 2
tables*). This is a **one-step hand study, not a committed model result**. The script is in
my scratchpad and is not in the repo. As a check, layout A with the actual per-bus loads
gives 0.811 pu, close to MATLAB's stress-week minimum of 0.787 pu.

| Layout | Lowest voltage (pu) | Transformer loading (pu) | Line loss (kW) | Transformer copper loss (kW) | Loss as % of load |
|---|--:|--:|--:|--:|--:|
| A today | 0.824 | 1.31 | 50.1 | 5.1 | 16.2% |
| B | 0.962 | 1.18 | 13.1 | 4.1 | 5.1% |
| **C** | **0.971** | **1.22** | **8.6** | **7.3** | **4.7%** |
| D | 0.994 | 0.91 | 5.3 | 5.2 | 3.1% |
| E | 0.980 | 0.74 | 10.9 | 3.1 | 4.1% |

What follows for our results:

1. **Voltage violations are mostly an artefact of layout A.** In every other layout the far
   end stays above 0.96 pu at the worst step of the stress week, well inside both ±6% and
   +6/−10%. A "voltage violations" card on the dashboard built on layout A would show 99%
   red with no GridSetu effect. On B–E it would show few violations, and the only lever
   left would be the battery's reactive power and placement.
2. **Technical losses at about 10% of energy are mostly layout A too.** With short circuits
   the peak-step loss falls from 16% to 3–5%, so the weekly figure would be well below
   today's 10.4%. Whatever GridSetu does to losses will be a smaller number in absolute
   terms.
3. **Transformer overload is what C keeps and D or E remove.** C is overloaded at peak
   (1.22 pu), like today, so overload trips and the transformer-ageing results stay. D and
   E aren't overloaded, so the baseline loses most of its 13 overload trips a month and only
   the DISCOM's rotation would remain as a cause of outages. GridSetu's measured improvement
   would shrink accordingly. The Python simulator would need a rerun to say by how much.
4. **Battery placement means different things.** With several transformers, a battery on
   one transformer's LV busbar can relieve only that transformer and can island only that
   transformer's critical loads. One battery for all homes would need its own 11 kV
   connection (a step-up transformer) and could not relieve any LV transformer.

## 6. Proposal: layout C

**One 11 kV spur from the R3 33/11 kV substation, with three 100 kVA 11/0.433 kV transformers
(DT-1, DT-2, DT-3), each feeding about 363 homes over three LT circuits of about 350 m.**

| Item | Where | Why |
|---|---|---|
| Battery | Three units of about 67 kWh / 33 kW, one on each transformer's LV busbar (the same 200 kWh / 100 kW in total) | Each unit relieves its own transformer, which is the constraint that trips. This matches the `gridsetu_distributed` scenario, the only one that cut losses. |
| Community PV (60 kWp) | 20 kWp next to each battery | Same total, charges the local battery without loading the LT circuits |
| Health sub-centre (12 kW) and school (8 kW evening, 4 kW at 18:45) | Together on DT-1, on a short dedicated LT circuit from the busbar | Both can then be islanded with DT-1's battery behind one breaker, without disconnecting homes one by one |
| Water pump (15 kW, direct-on-line) | DT-3 busbar, dedicated circuit | Its starting current (5× rated) needs the inverter on the same transformer. A 33 kW unit is marginal for a 15 kW direct-on-line start (*to check with the Simulink model*), so DT-3's unit may need to be larger, or the pump needs a soft starter. |
| Street lights (6 kW) | Spread over the three transformers, switched from each busbar | Standard practice: they're already on separate street-light circuits *(to verify for TN)* |
| 11 kV | The three transformers spread along the spur (one at about 1.2 km, two near the far end), replacing the 5 equal loads in `network.py` | Keeps the existing pandapower feeder; only the load points change |

**Pros**
- It is a real Indian design: 100 kVA is a standard rating, and three overloaded transformers on a growing peri-urban
  spur is exactly the RDSS "overloaded DT" case.
- Aggregate capacity stays at about 285–300 kW, so the Python headline results stay close to
  today's (the 285 vs 300 kW question is a team decision: either keep `capacity_kw: 300` and
  call the transformers about 105 kVA each, or use 285 and rerun).
- It makes the economic case concrete: the transformer upgrade GridSetu defers is a fourth
  100 kVA unit (layout D). Its cost is a slot for Parthasarathy.
- Islanding becomes physically credible: one breaker on DT-1's critical circuit and one inverter.
- Voltage and losses become realistic, so the MATLAB results will survive a judge's
  question ("your voltages look terrible") without the team saying "the network is wrong".

**Cons**
- **Model work.** The Python simulator needs one capacity limit per transformer, not one
  aggregate limit, so it can see that DT-2 can overload while DT-1 has headroom. That is
  the larger change: `feeder.py` and the LP in `plan_day`. A first step could keep one
  aggregate limit and split the load in proportion, which is only exact if the three
  transformers peak together.
- MATLAB needs three transformers in `f07_network.m` and `run_f07.m`, and a new bus table
  (`matlab_export.py`, `f07_buses.csv`). Priyadharshan's graphs 3–8 would be redrawn.
- Three smaller inverters cost more per kW than one 100 kW unit (*cost slot*).
- A 33 kW inverter for the clinic island is enough (Tier-1 on DT-1 is about 16–20 kW) but
  leaves little margin for DT-1's own peak shaving during an outage.

**If the team wants the smallest change:** layout B keeps one 315 kVA transformer and only shortens and doubles the
LT circuits. It fixes the voltage and most of the losses, needs no Python change, and needs
only `topology` in `f07_params.json` plus the bus table. It keeps today's numbers exactly. Its weakness is that a
single 315 kVA unit for 1,090 homes is on the large side for peri-urban TN (*to verify*),
and it does not fix the critical-load placement unless the clinic and school also move to a
dedicated circuit.

## 7. Decisions for the team call

1. Layout: **C** (recommended), B (smallest change), or D/E (no overload, smaller headline).
2. Under C, `capacity_kw` stays 300 (three units of about 105 kVA, not a standard rating) or becomes 285 (rerun, numbers move).
3. Voltage limit: adopt +6% / −10% once someone has read the TNERC gazette clause.
4. Whether Priyadharshan reruns MATLAB on the new layout before the 27 Nov graphs, or the graphs ship on layout A with a caveat.
5. Who fixes the stale figures in `QA_BANK.md` and `TEAM_BRIEF.md` (section 2, item 6).

## Sources

- BIS, transformer standards and standard ratings: https://www.bis.gov.in/wp-content/uploads/2022/04/Transformers-_compressed.pdf
- KSEB, 11 kV/433 V distribution transformer specification (100, 160, 250, 500 kVA): https://kseb.in/uploads/Downloadtemsuppy/Distribution%20Transformer%2011kV-433V,%20100,160,250%20_500kVA-1698389318851302889.pdf
- CSPDCL, schedule of rates, 25 to 500 kVA distribution transformers: https://cspdcl.co.in/CSEB/(S(pbgv42pr3pc4gayif2g1degn))/Files/SOR/SoR%20for%20FY%202024-25/25%20to%20500%20KVA%20Distn.Transformer.pdf
- TNERC, 2013 amendment to the Distribution Standards of Performance Regulations (voltage limits, Reg. 14), Tamil Nadu Government Gazette: https://www.stationeryprinting.tn.gov.in/gazette/2013/41-VI-2.pdf (*to verify: read the clause itself*)
