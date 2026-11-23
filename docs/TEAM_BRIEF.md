# Team brief: explain every module without notes

One short "viva" explanation per module, so any of us can defend it at the finale. Add a
section whenever a significant module is added or changed.

## `numbers.py`: the numbers registry

**What it does.** After a run, it reads `outputs/results.json` and writes
`outputs/numbers.json`: every headline figure with its value, unit, the exact text we quote
(e.g. "529 kWh"), and the JSON path it came from. It also records the git commit, Python
and library versions. `python -m gridsetu numbers --check README.md` fails if a document
quotes a figure that no longer matches.

**Why it matters.** A judge can trace any number in under two minutes: number → `numbers.json`
→ `results.json` path → the code that computes it. On its first run it caught a real error
(the README said 2,315 kWh where the data says 2,314).

**Likely question.** *Could you just edit numbers.json?* It is regenerated on every run and CI
rebuilds it, so a hand edit is overwritten and the check fails.

## `calibration.py`: does the reserve keep its word?

**What it does.** Each evening GridSetu publishes a Reliability Reserve with a confidence
(T−24h, T−1h, T−15min). The study re-runs the whole simulation for 30 weather/load seeds,
2 weeks each (1,260 published forecasts), and checks each one against what happened.

**Three outcomes, scored separately.**
- `own_peak_held`: what the confidence actually models. Import stayed under the transformer
  limit through the evening window, with no overload trip (DISCOM calls excluded).
- `held`: the DISCOM's call was met as well (no trip for missing 95% of a request).
- `end_to_end`: `held`, and no trip from a lost protection (SPS) message.

**Result.** `own_peak_held` is 100% on all 1,260 forecasts, so the confidence is honest about
what it covers. On all 60 evenings with a DISCOM call, the request was 1.2 to 4.3 times the
published reserve, the call was not met, and the feeder was rotated off (Tier 1 islanded). The
confidence still said 100% because it never looks at the call. Planned fix: a second confidence
for the expected call, and calls bounded by the published reserve.

**Scores.** Brier score = mean of (stated probability − outcome)², 0 is perfect. With every
forecast at 100%, a reliability diagram collapses to one point, so the chart shows stated vs
observed by week type, and request vs offer on call evenings.

**Likely question.** *Isn't 100% confidence suspicious?* For the own peak it was earned: the
battery covers the shortfall above the import target with a wide margin. The honest gap is that
the number answers a narrower question than a control-room operator would assume.

## Reproducibility: `requirements-lock.txt` and `scripts/reproduce.sh`

`requirements.txt` gives version ranges, so a fresh install pulls the newest libraries and the
headline figures move by 1–3%. Within one environment the run is fully deterministic: two runs
give an identical `results.json`. `requirements-lock.txt` pins every library, the committed
`outputs/` were produced under it, and `scripts/reproduce.sh` re-runs the study and fails if any
committed value changes by more than one part in a billion (smaller differences are floating-point
noise between processors). CI runs it on every pull request.

## `matlab_export.py`: feeder F07 for the MATLAB model

**What it does.** The Python simulator treats the feeder as one point. The MATLAB model needs
the loads on a radial low-voltage network. `python -m gridsetu export-matlab` places the 420
homes (20 per bus), 35 micro-enterprises and the critical loads on 21 buses (3 circuits × 7
buses, 600 m each) and writes per-bus net load for every 15-minute step, plus the feeder-head
import, battery, community PV, energized state and ambient temperature.

**Why you can trust it.** A test checks that, at every energized step, the bus loads minus
community PV and the battery at the transformer bus add up to the import Python reports, and
that every bus is zero when the feeder is off. Paused Tier-3 load is removed from exactly the
homes the fairness ledger paused that step.

**Stated assumptions.** Bus positions, circuit length, the clinic on bus 4, the school on bus
11, the water pump at the tail of circuit C (bus 21), street lighting and rooftop PV spread
evenly. These go on the MATLAB slide as assumptions.

## The low-voltage model: `matlab/run_f07.m` and its Python twin `lvnetwork.py`

**What it does.** Places the exported bus loads on a radial 415 V network (3 circuits × 7
buses, 600 m of ACSR Rabbit each, a 315 kVA IS 1180 Level-2 transformer) and, for every
15-minute step, solves a backward/forward-sweep load flow: start every voltage at the source
value, compute each bus's current from its load, add the currents up the tree (backward), then
subtract each branch's voltage drop down the tree (forward), and repeat until nothing changes.
Then the IEC 60076-7 thermal model turns transformer loading into top-oil and hot-spot
temperature and an ageing rate V = 2^((θh − 98)/6).

**Why you can trust it.** The solver matches a hand-calculated case to 1e-9; the bus loads add
up to the Python simulator's import at every step; MATLAB and the independent Python twin agree
to 1e-8 at every step of every case.

**What it found.** GridSetu cuts the transformer's peak loading from 1.37 to 1.19 pu and its
hot-spot peak by about 9 °C. A battery at the transformer cannot reduce line losses or voltage
drop; splitting the same storage across the circuits cuts losses about 7% and lifts the worst
voltage from 0.79 to 0.83 pu. Voltage is outside ±6% on the assumed network in every case.

**Likely question.** *Your voltages look terrible. Is the model wrong?* Three 600 m circuits
each carry about 113 kW at the evening peak: roughly 166 A per phase, above Rabbit's 156 A
rating. Hand estimate of the drop: 166 A × 0.67 Ω/km × 0.3 km ≈ 33 V of 240 V, about 14%, plus
the transformer drop, minus the 433 V tap boost. The model agrees. The answer is the network,
and GridSetu's per-bus map shows where.

## Real data: `realdata.py` and `realstudy.py`

**What it does.** Loads two real datasets for the same calendar dates in 2025:
- NASA POWER hourly sunshine and temperature for Coimbatore (20 Jul to 21 Sep 2025);
- IEX day-ahead prices for 14–20 Sep 2025.

It maps the simulated 2026 week onto them. `python -m gridsetu real-data` then runs four checks:
- our price curve against IEX;
- our weather against NASA over 63 days;
- a forecast backtest (train on 6 weeks, test on the next, 3 times);
- the stress week re-run on real weather, and on real weather plus real prices.

**Why you can trust it.** Each file is checked against a total published by its source:
- the mean of each IEX day equals IEX's own daily average;
- the NASA rows match sums taken on the API response;
- turning hourly sunshine into 15-minute steps keeps every hour's energy exactly.

Tests re-check all of this. The synthetic case inside the study equals the headline stress week exactly.

**What it found.**
- **Prices:** real evening prices sat at the ₹10 ceiling on 6 of 7 days. Our curve stops at ₹9.8, and real midday prices were much lower than ours (₹1.17 vs ₹2.6/kWh). The real market favours storage more than our scenario does.
- **Sunshine:** real sunshine was about 20% lower than our synthetic weather and steadier.
- **Forecast:** on real weather it covered 79% of outcomes with its 80% range.
- **Stress week:** on the real week GridSetu cut evening unserved energy by half (808 → 408 kWh), because the real week had no deeply overcast day. We keep the harsher synthetic week for the headline.

**Likely question.** *Is your household load real?* No. Weather and prices are real; load is synthetic until we get smart-meter data. The data card lists every input with its label.

**Time zone trap.** NASA's "LST" is UTC+5, not IST. IST = LST + 30 min; we proved it by fitting solar geometry, and a test keeps it that way.
