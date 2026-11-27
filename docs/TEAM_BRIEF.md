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
what it covers. In the first version, on all 60 evenings with a DISCOM call the request was
far above the published reserve and the call was not met. That led to lifeline mode and the
second (call) confidence, scored by `call_met`: see "Lifeline mode and the second confidence"
below. With the fitted homes, 0 of 60 calls are met in full as the DISCOM calls today, and
53 of 60 when calls are bounded by our offer.

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
the loads on a radial low-voltage network. `python -m gridsetu export-matlab` places the 1,090
homes (spread evenly, about 52 per bus), 35 micro-enterprises and the critical loads on 21 buses (3 circuits × 7
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
buses, 600 m of 3×95 mm² aerial bunched cable each, a 315 kVA IS 1180 Level-2 transformer) and, for every
15-minute step, solves a backward/forward-sweep load flow: start every voltage at the source
value, compute each bus's current from its load, add the currents up the tree (backward), then
subtract each branch's voltage drop down the tree (forward), and repeat until nothing changes.
Then the IEC 60076-7 thermal model turns transformer loading into top-oil and hot-spot
temperature and an ageing rate V = 2^((θh − 98)/6).

**Why you can trust it.** The solver matches a hand-calculated case to 1e-9; the bus loads add
up to the Python simulator's import at every step; MATLAB and the independent Python twin agree
to 1e-8 at every step of every case.

**What it found.** GridSetu cuts the transformer's peak loading from 1.26 to 1.10 pu and its
hot-spot peak by about 5 °C. A battery at the transformer cannot reduce line losses or voltage
drop; splitting the same storage across the circuits cuts losses about 4%, voltage violations
42%, and lifts the worst voltage from 0.906 to 0.914 pu. Losses are about 6% of energy.

**Likely question.** *Why aerial bunched cable, and did you change it to get better numbers?*
Our first layout used bare ACSR Rabbit; it put voltage outside limits in 93% to over 99% of
steps, which no working feeder shows, because 166 A per phase at the peak is above Rabbit's
156 A rating. The CEA guidelines recommend aerial bunched cable for congested, theft-prone lanes
like this one, so the feeder is modelled reconductored. The bare-conductor case is still run as a
sensitivity, and the conclusions on storage placement and the transformer are the same.

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
- **Forecast:** on real weather it covered 79.2% of outcomes with its 80% range (78.0% on synthetic weather).
- **Stress week:** on the real week GridSetu cut evening unserved energy by about 40% (800 → 465 kWh), because the real week had no deeply overcast day. We keep the harsher synthetic week for the headline.

**Likely question.** *Is your household load real?* No. Weather and prices are real; load is synthetic until we get smart-meter data. The data card lists every input with its label.

**Time zone trap.** NASA's "LST" is UTC+5, not IST. IST = LST + 30 min; we proved it by fitting solar geometry, and a test keeps it that way.

## Lifeline mode and the second confidence (`feeder.py`, `calibration.py`)

**What it does.** When a DISCOM request is larger than the battery, Tier 3 and Tier 2 can give,
the controller finds the highest common load limit L (at least 200 W) such that capping every
home at L frees enough power. `_lifeline` does this by bisection. Homes above L are cut back to
it; 5% of them exceed it and their meter disconnects them. If even 200 W per home isn't
enough, the feeder is switched off as before, with the critical loads islanded on the battery.

**The second confidence.** Each published reserve also carries:
- **call capacity:** the battery's energy spread over the whole evening, plus Tier 2, plus
  what lifeline could free (from each home's load at the same time yesterday, so no peeking
  at the future), taken at the q10;
- **call confidence:** the chance that capacity is really there, about 90%.

The calibration scores it on calls inside the offer.

**What it found.**
- Monthly home-hours without supply fall from 18,167 to 2,483, and whole-feeder outage from 16.7 h to 2.3 h (fitted homes).
- With calls bounded by the day-ahead offer, 53 of 60 call evenings are met, and the 90% call confidence held 90.8% of the time: well calibrated.
- With calls as the DISCOM makes them today (median 2.15 times our offer), 0 of 60 are met in full.
- Across 20 feeders, home-hours without supply in the stress week fall 44% at full adoption (75% with the first, heavier homes; 26% before lifeline).

**Bugs it exposed and fixed.**
- An accepted DISCOM cap outside the rotation group could be missed with no consequence.
- A missed call was recorded at size zero.
- The first call offer counted Tier 3 twice; the calibration caught it, because stated 90% came out at 48%.

**Likely question.** *Why not always use lifeline instead of the battery?* Lifeline limits
every home; the battery limits nobody. So the battery goes first, then Tier 3 and Tier 2, and
lifeline only when those run out.

## Business case: `economics.py`

**What it does.** Runs the stress and normal weeks for 3 seeds and prices every 15 minutes with
the real IEX prices. It annualises (13 stress + 39 normal weeks), adds up the costs, and reports
the **break-even value**: what an avoided kWh of outage must be worth for the costs to be
covered.

**Costs:**
- **Battery:** the 2025 Indian benchmark tariff for 2-hour storage (₹2.3 lakh/MW/month), which already includes capital, maintenance and return, × 2 for small scale.
- **Smart plugs:** ₹1,500 per home over 5 years. Every home in the model has some Tier-3 load, so every home is costed one; eMARC suggests only 41% own an AC or water heater.
- **Controller and comms:** ₹25,000 a year.

**Result.** ₹9.0 lakh a year (₹69 per home per month); break-even ₹21.7 per kWh; benefit ÷ cost
0.46 at the IEX ceiling and 1.53 at diesel-backup cost. The sensitivity chart shows the battery price matters
most.

**Likely question.** *Why not just assume a value of lost load?* There's no solid Indian
figure for this kind of community. A break-even lets the DISCOM or a funder put in their own
number and see the answer at once.

## Household check: `householdcheck.py`

**What it does.** Compares our synthetic homes with 116 measured Indian homes (Prayas eMARC,
CC0). The 368 MB file was processed in the browser and only a summary was kept
(`data/real/emarc_mainline_summary.json`). It checks both the fitted model (now used) and the
first model; with `--sensitivity` it re-runs the month under both.

**The fitted model** (`household_model` in `config/city.yaml`, `_emarc_households` in
`profiles.py`): each home = the measured average day, shifted in time by a random amount
(standard deviation 45 minutes), × a lognormal size (σ 0.85), with a quarter of its energy moved into random appliance bursts (about 0.8 kW for
about 5 steps). The feeder's 340 kW is anchored at the evening peak (`target_peak_window:
evening`), which needs 1,090 homes.

**What it found.**
- First model: 8.6 kWh a day, coincidence 0.85, 64% of evening load above 200 W.
- Fitted model: 4.9 kWh a day, coincidence 0.30, 44% above 200 W.
- Measured: 4.6 kWh a day (TN average 3.5), coincidence 0.35, 37% above 200 W.
- Results on fitted homes: −74% evening unserved energy (−82% before), critical loads always on, no overload trips. Lifeline frees less power, so home-hours dark fall 86% instead of 95%.

**Likely question.** *Did you tune the model to make GridSetu look good?* No: the parameters
were fitted only to the measured per-home statistics, and the results got less flattering. We
publish both.
