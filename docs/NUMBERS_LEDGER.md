# Numbers ledger: every headline figure, where it comes from, what it replaces

Written 25 Nov 2026 on branch `round2-foundation`. **All results are SIMULATION** (synthetic data, not field
measurement). The rule: a figure goes in the README, deck, form or video only if it has a row
here and a key in `outputs/numbers.json` or `matlab/results/summary.json`.

## How to read the status column

| Status | Meaning |
|---|---|
| **CHECKED** | In `outputs/numbers.json` with `check: true`. `python -m gridsetu numbers --check README.md` fails if the README quotes it differently. |
| **REGISTERED** | In `numbers.json` with `check: false`, either because the README doesn't quote it yet (the checker needs every checked figure to appear in each checked file) or because the text is too short to search for safely (bare integers). |
| **PROVISIONAL** | The code that produces it is committed, but the committed `outputs/` were made before it existed. The value shown comes from a run on Windows; the committed value must come from Linux (see the end of this file). It registers itself in `numbers.json` once the outputs are regenerated. |
| **PENDING_SOURCE** | Needs a sourced input that we don't have yet. Not computed. |
| **NOT REGISTERED** | No committed output behind it yet. Must not be quoted until it has one. |

The registry went from 138 figures (62 checked) to **163 figures (87 checked)** on the committed
outputs. It reaches more when the provisional outputs are committed.

## 1. Pilot feeder, per month (3 normal weeks + 1 stress week, mean of 3 seeds)

Baseline, in one sentence: **today's rotational load-shedding by the DISCOM, with no storage and
no demand response on the feeder** (`results.json:about.baseline_definition`, once regenerated).

| Figure | Baseline | GridSetu | Change | Source (key in `numbers.json`) | Status | Round 1 value it replaces |
|---|--:|--:|--:|---|---|---|
| Unserved energy, evening ramp 17:30–19:30 | 2,223 kWh | 577 kWh | −74% | `pilot.{baseline,gridsetu}.evening_unserved_kwh` ← `results.json:pilot_feeder_monthly.*.evening_window_unserved_kwh.mean` | CHECKED | **−35%** "unmet evening-ramp demand" (older model) |
| Unserved energy, all hours | 4,913 kWh | 914 kWh | −81% | `pilot.*.all_hours_unserved_kwh` | CHECKED | (−35%, same claim) |
| Energy not supplied (ENS) | = all-hours unserved | | | same key; ENS isn't a second number | CHECKED | none |
| Critical-load (Tier-1) outage | 16.7 h | 0.0 h | −100% | `pilot.*.critical_outage_h` | CHECKED | **−88%** critical-load outage time |
| Whole-feeder outage | 16.7 h | 2.2 h | −86% | `pilot.*.feeder_outage_h` | CHECKED | none |
| Homes fully without supply | 18,167 home-h | 2,484 home-h | −86% | `pilot.*.dark_home_hours` | CHECKED | none |
| Homes on the 200 W lifeline | – | 1,017 home-h | | `pilot.gridsetu.lifeline_home_hours` | CHECKED | none (lifeline is new) |
| Transformer overload trips | 13 | 0 | −100% | `pilot.*.overload_trips` | REGISTERED (bare integer) | none |
| Feeder peak import | 340 kW | 291 kW | −14% | `pilot.*.peak_import_kw` | CHECKED | **−15%** feeder peak |
| Solar utilisation | 99.3% | 100.0% | +1 pt | `results.json:pilot_feeder_monthly.*.solar_utilisation_pct` | NOT REGISTERED (don't quote) | **+23 pts** renewable utilisation. Superseded: daytime load always exceeds the 150 kWp of solar, so both cases use about all of it (README, "Where the model disagrees") |
| Battery cycles | – | 22.9 | | `pilot.gridsetu.battery_cycles` | CHECKED | none |
| "+ city DR" column | | 483 kWh / 625 kWh / 1.2 h / 1,389 / 1,185 home-h / 22.8 | | `pilot.coordinated.*` | CHECKED | none |
| Seed ranges, evening unserved | 1,124–3,062 kWh | 442–652 kWh | | `pilot.*.evening_unserved_seed_range` | CHECKED | none |

**Important context for every row.** In the baseline, 13 of the outages a month are transformer overload trips. They exist because the feeder's
aggregate rating (300 kW) is below its 340 kW evening peak. See `docs/TOPOLOGY.md`: with
more transformer capacity, part of GridSetu's improvement would go away. The team is deciding the layout.

## 2. Reliability in the DISCOM's terms (new, item 3)

Definitions in `src/gridsetu/reliability.py`. Customers are the 1,090 households. Interrupted = fully
dark; homes on the 200 W lifeline count as supplied, and their hours are shown next to SAIDI. Every
interruption is at least one 15-minute step, so all count as sustained (IEEE 1366 uses more than 5 minutes).

| Figure | Baseline | GridSetu | + city DR | Key | Status |
|---|--:|--:|--:|---|---|
| SAIDI, h per household per month | 16.7 | 2.3 | 1.2 | `reliability.{baseline,gridsetu,coordinated}.saidi_h` ← `pilot_feeder_monthly.*.saidi_h.mean` | REGISTERED |
| SAIDI, h per household per year (if the simulated month repeats all year) | 200 | 27 | | `reliability.*.saidi_h_per_year` | REGISTERED |
| SAIFI, interruptions per household per month | 23.7 | 7.6 | 4.7 | `reliability.*.saifi` | REGISTERED |
| CAIDI, h per interruption | 0.66 | 0.30 | 0.26 | `reliability.*.caidi_h` | REGISTERED |
| Evening supply availability, 17:00–23:00 | 91.1% | 98.6% | 99.3% | `reliability.*.evening_availability_pct` | REGISTERED |
| Lifeline home-hours (supplied, but capped) | 0 | 1,015 | 1,184 | `pilot.*.lifeline_home_hours` | CHECKED (committed: 1,017 / 1,185) |

Notes:
- Baseline SAIDI equals the whole-feeder outage hours (16.7 h), because a rotation or overload trip darkens every home. That's a useful cross-check.
- SAIFI is high (about 24 a month) because a rotation evening is a series of short 15-minute blocks, each counted. If the DISCOM counts one "shedding event" per evening, the ratio stays similar but the absolute numbers fall. Worth saying in Q&A.

## 3. Technical losses (new, item 7)

Reported as they are. **GridSetu with the battery at the transformer does not reduce technical
losses in either model.** Only the split battery (one third mid-way along each LV circuit) cuts them.

| Figure, stress week | Baseline | GridSetu (battery at the transformer / 11 kV node 3) | GridSetu, battery split across the 3 LV circuits | Key | Status |
|---|--:|--:|--:|---|---|
| MATLAB LV model: lines + transformer, kWh | 4,411 | 4,480 (+1.6%) | 4,203 (−4.7%) | `lv.stress.{baseline,gridsetu,gridsetu_distributed}.technical_loss_kwh` ← `matlab/results/summary.json` | CHECKED |
| MATLAB LV model: % of energy | 10.40% | 10.33% | 9.75% | `lv.stress.*.technical_loss_pct` | REGISTERED |
| MATLAB LV model, representative week, kWh (%) | 4,282 (10.01%) | 4,432 (10.03%) | 4,074 (9.29%) | `lv.representative.*` | REGISTERED |
| Python power flow: pilot's 11 kV line sections, kWh | 129 | 132 | not modelled | `losses.python_11kv.{baseline,gridsetu}.kwh` ← `results.json:power_flow_stress.feeder_11kv_losses.*.loss_kwh` | REGISTERED |
| Python power flow: % of energy into the feeder | 0.34% | 0.34% | not modelled | `losses.python_11kv.*.pct` | REGISTERED |

**Do the two models agree?** On the direction, yes. Both say a battery at the head of the network
doesn't cut losses. Losses rise slightly in kWh because GridSetu supplies energy that the baseline
didn't, and stay flat as a percentage. On size, they differ about 30-fold, and they should:
they cover **different parts of the network**. The Python model covers only the 11 kV line, where the current is
about 26 times lower than at 415 V for the same power. MATLAB covers the 415 V circuits and the
transformer. Total technical losses would be roughly the sum. The 10% LV figure is mostly a result of the
assumed layout (three 600 m circuits for 1,090 homes). `docs/TOPOLOGY.md` estimates 3–5% at the
evening peak for realistic layouts, so treat it as an upper bound, not a property of the area.

Peak reduction does cut I²R at the peak itself. But GridSetu moves energy to other hours and supplies more of it, so
the weekly total doesn't fall. A deck must not say "GridSetu reduces technical losses" on these results.
It can say "placing the storage along the LV circuits cuts losses about 5%" (MATLAB, split battery).

## 4. Economics (item 4)

Headline method: the battery priced as a service at the 2025 Indian benchmark tariff (IEEFA–JMK).
All inputs are in `config/city.yaml` under `economics:`, each sourced or marked ASSUMPTION.

| Figure | Value | Key | Status | Round 1 value it replaces |
|---|--:|---|---|---|
| Total cost per year | ₹9.0 lakh | `economics.total_cost_lakh` | CHECKED | **~₹42 lakh capex + ₹3.4 lakh/yr** (unsourced; dropped) |
| Battery / smart plugs / controller, per year | 5.52 / 3.27 / 0.25 lakh | `economics.cost_{battery,smart_plugs,controller_comms}_lakh` | CHECKED | (part of the ₹42 lakh) |
| Extra energy bought at IEX prices | 2.29 lakh | `economics.extra_energy_cost_lakh` | CHECKED | none |
| Cost per home per month | ₹69 | `economics.cost_per_home_month` | CHECKED | **~₹10,000 per household** (one-off capex, 420 homes) |
| Break-even value of an avoided outage kWh | ₹21.8 | `economics.breakeven_inr_per_kwh` | CHECKED | none |
| Outage avoided per year | 51,988 kWh | `economics.unserved_avoided_kwh` | CHECKED | none |
| Cost per household-hour of outage avoided | ₹5.5 | `economics.cost_per_avoided_home_outage_hour` | REGISTERED | **~₹11,300 per avoided outage-hour** (feeder-hour, assuming 30 h a year; different unit and an assumed outage count) |
| Household outage-hours avoided per year | 203,886 | `economics.home_outage_hours_avoided` | REGISTERED | none |
| What a kWh from the battery costs at the tariff | ₹10.9 | `economics.battery_cost_per_kwh_delivered` | REGISTERED | **~₹4.8 per kWh of reserve delivered** |
| Build cost + running cost method (₹/kWh at 1 cycle/day and at the model's cycling, ₹/home/month, ₹/avoided home-outage-hour) | not computed | `economics.json:capex_method` | **PENDING_SOURCE** (8 inputs in `config/city.yaml`, `economics.capex_method`) | the hand calculation in the 25 Nov brief (₹17 and ₹30 per kWh, ₹150 per home per month, ₹14 per home-outage-hour). Not reproduced: it used 420 homes and the Phase 1 capex |
| Value of the transformer upgrade deferred | not computed | `economics.json:deferral` | **PENDING_SOURCE** | none |
| Reserve price quoted to the DISCOM | ₹3.5/kWh (degradation 1.5 + adder 2.0) | `config/city.yaml:pilot_feeder.reserve_price` | ASSUMPTION, build-up slots PENDING_SOURCE | none |

What this says, in one line: **each kWh the battery delivers costs about ₹10.9 at the benchmark tariff,
above the ₹10 IEX ceiling, so the battery doesn't pay for itself by trading. Its value is the
outages it avoids** (break-even ₹21.8 per avoided kWh, below diesel backup at about ₹33).

## 5. City, protection, isolated microgrid, power flow, planning (results.json)

All registered and checked against the README as of this branch (they were only checked by eye before).

| Figure | Value | Key | Status | Note |
|---|--:|---|---|---|
| City energy not served, stress week | 723 → 494 MWh | `city.{baseline,coordinated}.ens_mwh` | CHECKED | |
| WAMS case A nadir | 49.70 Hz | `wams.A_baseline.nadir_hz` | CHECKED | |
| WAMS case B nadir | 49.16 Hz | `wams.B_baseline.nadir_hz` | CHECKED | |
| Special-protection shedding, case A | 62 → 57 MW | `wams.A.sps_shed_mw` | CHECKED | |
| Isolated microgrid: unserved / diesel hours / wasted solar | 613 → 114 kWh, 139 → 116 h, 441 → 22 kWh | `island.*_change` | CHECKED | |
| Most-loaded 220 kV line | 110%, in 8 samples | `power_flow.max_220kv_line_loading_pct`, `.samples_over_100pct` | CHECKED | |
| "Feeder voltages stayed within 0.99 to 1.03 pu" | 0.99–1.03 pu | `power_flow.v_33kv_range_pu` | CHECKED | **Text is wrong:** the figure is the range at the 33 kV buses, not the feeder. The 11 kV feeder minimum is 0.986 pu. Fix the README sentence. |
| City peak, load factor, reserve margin | 474 MW, 0.70, 1.9% | `planning.*` | CHECKED | |
| Fairness: 829 homes, 5.5 h max, Gini 0.21, 1,471 overrides | | `fairness.*` | CHECKED (already) | |
| Forecast coverage, median error | 72%, 4.7% | `forecast.*` | CHECKED (already) | |

## 6. Fleet and unit commitment (new committed source, `python -m gridsetu phase2`)

Before this branch these existed only in the API run cache. `src/gridsetu/phase2.py` now writes
them to `outputs/phase2/phase2.json` (seed 42, same as the reference run), regenerated on Linux by the
Regenerate outputs workflow. "Before" is what the README said until that file was committed.

| Figure (stress week) | Committed | README before | Key | Status |
|---|--:|--:|---|---|
| Transformers overloaded at the evening peak | 18 of 20 | 18 of 20 | `fleet.feeders_overloaded` | CHECKED |
| Critical-site hours dark, 0/5/10/15/20 feeders | 310 / 194 / 104 / 46 / 0 h | 311 / 195 / 105 / 46 / 0 | `fleet.stress.N.critical_site_hours` | CHECKED (not the 0 h row, which would match anywhere). Raw 310.5 / 194.5 / 104.5 / 46.25: the README now uses the registry's rounding (half to even) |
| Home-hours dark | 116,088 … 65,554 | same | `fleet.stress.N.home_hours_dark` | CHECKED |
| Unserved energy | 26,861 / 23,346 / 20,259 / 18,836 / 17,170 kWh | 26,861 / 23,349 / 20,268 / 18,845 / 17,182 kWh | `fleet.stress.N.unserved_kwh` | CHECKED; README updated (moves under 0.1%) |
| Home-hours dark, change at full adoption | −44% | "falls by 44%" | `fleet.stress.home_hours_dark_change` | CHECKED; README wording updated |
| Normal week, home-hours dark at 0% | 45,424 | 45,424 | `fleet.representative.0.home_hours_dark` | CHECKED |
| Gas starts / hours on (UC vs linear) | 8 / 48 h vs 57 h | 8 / 49 vs 57 | `uc.gas_starts`, `uc.gas_hours_*` | CHECKED; 48.5 h, rounded half to even |
| Shedding, UC vs linear market | 356 vs 337 MWh | 363 vs 337 MWh | `uc.shed_uc_mwh`, `uc.shed_lp_mwh` | 356 REGISTERED (unchecked), 337 CHECKED; README updated |
| Extra cost of UC | ₹12 lakh (0.7%) | ₹11 lakh (0.6%) | `uc.extra_cost_lakh`, `uc.extra_cost_pct` | CHECKED; README updated |

**Why UC differs:** until this branch, `uc.py` solved with `mip_rel_gap: 0.005` and a 60 s `time_limit`,
so the schedule could depend on machine speed and land anywhere inside the 0.5% gap. The README's
363 MWh / ₹11 lakh came from such a run. The time limit is now removed and HiGHS runs with a fixed seed on one
thread, so the schedule depends only on the inputs (one UC run takes about 15 s). The README now quotes the
committed file.

**Gap sensitivity (26 Nov, same seed, 1 thread, stress week):**

| `mip_rel_gap` | Gas starts | Gas hours (UC vs linear 56.75) | Shed, UC vs linear 337.27 MWh | Extra cost | Run time |
|---|--:|--:|--:|--:|--:|
| 0.5% (committed) | 8 | 48.5 | 356.5 | ₹11.96 lakh (0.66%) | 13 s |
| 0.1% | 7 | 50.0 | 353.9 | ₹9.89 lakh (0.54%) | 12 s |
| 0.01% | 7 | 50.0 | 356.0 | ₹9.62 lakh (0.53%) | 13 s |

The direction holds at every gap (UC sheds more and costs more than the linear market), but the
figures do not: a tighter gap gives one start fewer and about ₹2 lakh less. So the README no
longer says "a tighter solver gap does not change this". These are my Windows runs, not
registered. `phase2` is still not part of
`scripts/reproduce.sh`; adding it would cost about 6 minutes of CI per run.

## 7. Not registered: don't quote until there's a file behind them

| Figure | Where it lives today | What's needed |
|---|---|---|
| Simulink islanding: 0.55 pu, 40 ms, 100 ms, 0.99 pu, 0.965 pu, 49.84 Hz, 115°, 0.3 Hz, 6.94 s, 90 kW, 115 ms | `matlab/README.md` and `README.md` prose | Commit `matlab/islanding/results/islanding_summary.json` (written by `run_islanding`) and register it |
| "Measured playback held 16.7 ms per frame" | README line 416 | A script or output that measures it, or remove the sentence |
| Solar utilisation 99.3 → 100% | `results.json` | Deliberately unregistered: not a GridSetu effect |
| Voltage violations under +6/−10% (847 bus-hours stress baseline) | a recount from `matlab/results/*_steps.csv` in `docs/TOPOLOGY.md` | Only if the team adopts the TNERC limit: change `v_limit_pu` and rerun MATLAB |

## 8. The brief's four goals: which figure or feature answers each

| Goal (Challenge 03) | Our answer | Figures (status) | Weak spot to be ready for |
|---|---|---|---|
| **1. Bridge intermittency gaps**: reliable supply when renewable output falls below demand | Quantile forecast → day-ahead Reliability Reserve → battery, fair Tier-3 pauses and lifeline in the evening ramp | Evening unserved −74%, critical outage 16.7 → 0.0 h (CHECKED); SAIDI 16.7 → 2.3 h per home per month, evening availability 91.1% → 98.6% (REGISTERED) | Part of the baseline's outages are transformer overloads that a bigger transformer would also remove (TOPOLOGY.md) |
| **2. Stay local and manageable**: neighbourhood level, minimal grid intervention | One edge controller and one community battery per feeder; the DISCOM sees one Reliability Reserve object; no feeder pushes its burden onto a neighbour | Critical outage stays 0.0 h with 60% message loss (`comms_60pct_loss.critical_outage_h`, REGISTERED); fleet: 18 of 20 overloaded feeders served without new wires (CHECKED) | The island needs an interlocked breaker and a dedicated critical circuit (HOW_IT_WORKS_PHYSICALLY.md) |
| **3. Be genuinely affordable** for low-income communities | Battery as a service at the benchmark tariff, owned by a resident cooperative; homes pay through the DISCOM, not up front | ₹69 per home per month, break-even ₹21.8 per avoided kWh vs diesel about ₹33 (CHECKED); ₹5.5 per household-hour of outage avoided (REGISTERED) | A battery kWh costs about ₹10.9, above the ₹10 IEX ceiling: the value is reliability, not trading. The capex method and the transformer deferral are PENDING_SOURCE |
| **4. Support the DISCOM**: data, forecasts, demand-response signals; manage feeder loads **and reduce technical losses** | Calibrated day-ahead reserve with a call capacity and confidence, published to the ADMS; per-bus LV model | Peak 340 → 291 kW, overload trips 13 → 0 (CHECKED); transformer peak loading 1.37 → 1.20 pu, hot-spot 89.0 → 83.4 °C (`lv.stress.*`, CHECKED) | **Losses are not reduced** with the battery at the transformer (LV 4,411 → 4,480 kWh; 11 kV 0.34% both). Only the split battery cuts them (−4.7%). Voltage violations are computed but not on the dashboard (BRIEF_GAPS.md (a)) |
| Required: **measurable reliability improvement against a defined baseline** | Baseline sentence in section 1; SAIDI, SAIFI, ENS, evening availability | Section 2 | Report the seed range with each headline |

## 9. Known issues with the numbers themselves

1. **Platform drift.** The committed outputs were made on Linux (CI). On Windows, the GridSetu
   side of the same code and lock file comes out slightly different: evening unserved 576.5 vs 577.1 kWh,
   GridSetu seed minimum 442 vs 446 kWh (+0.85%), Tier-3 curtailed −1.6%. Baseline values are
   identical. I checked that this is the platform and not this branch: unmodified `origin/main` on
   Windows gives exactly the same values as this branch. **Regenerate committed outputs on Linux only.**
2. **The checker tests whether the text appears, not where.** A figure passes if its text appears anywhere in the
   README (for example "0.0 h" appears several times). It catches drift, not a figure quoted in the wrong place.
3. **The README "0.99 to 1.03 pu" sentence** describes the 33 kV buses as feeder voltages (section 5).
4. **Stale loss figures** in `docs/QA_BANK.md` ("about 7%, to 2,047 kWh") and `docs/TEAM_BRIEF.md`
   (7%, 0.83 pu). `summary.json` says −4.7% against the baseline (−6.2% against GridSetu at the transformer) and 0.81 pu.

## To finish this ledger (needs Linux, Python 3.13, `requirements-lock.txt`)

The **Regenerate outputs** workflow (`.github/workflows/regenerate-outputs.yml`) runs on every PR to main and from Actions tab →
Run workflow; commit the `outputs/` artifact it uploads. It runs:

```bash
pip install -r requirements-lock.txt
python -m gridsetu run --seeds 3 --out outputs           # ~3 min
python -m gridsetu real-data --out outputs/real_data     # ~1 min; real_data.json stores every feeder metric
python -m gridsetu economics --out outputs/economics     # ~5 min
python -m gridsetu ownership --out outputs/economics     # seconds; reads economics.json
python -m gridsetu phase2 --out outputs/phase2           # ~6 min
python -m gridsetu numbers --check README.md             # fix each MISMATCH in the README
```
After committing, CI's `reproduce` job must print REPRODUCED four times. The outputs committed on
26 Nov come from this workflow, and every figure that was PROVISIONAL now carries its committed value.
The workflow runs on PRs to main only when `src/`, `config/`, `data/` or `requirements-lock.txt`
change, and from Actions → Run workflow on demand.
