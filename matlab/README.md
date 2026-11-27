# MATLAB low-voltage model of pilot feeder F07

Technical losses, voltage along the wires and transformer ageing: what the one-point Python
simulator cannot see. Base MATLAB only (R2019b or newer), no toolboxes. The same files also
run in GNU Octave 7+.

## Run it (about 1 minute)

```matlab
cd matlab
test_bfs          % load-flow solver vs a hand-calculated case: must print PASS
run_f07           % all weeks and scenarios -> results/
make_figures      % deck graphs -> results/figures/
```

`run_f07` prints one line per case and ends with `MATLAB vs Python twin: largest difference ...`.
That number should be around 1e-8 or smaller. If the Python twin's results are missing, run
`python -m gridsetu lv-study` first.

## What goes in, what comes out

| File | What it is |
|---|---|
| `f07_params.json` | Every network and transformer parameter, each with its source or marked ASSUMPTION |
| `../outputs/matlab/f07_loads_<week>_<variant>.csv` | Net load per bus per 15 minutes, from `python -m gridsetu export-matlab` |
| `../outputs/matlab/f07_feeder_<week>_<variant>.csv` | Feeder import, battery, community PV, energized state, ambient temperature |
| `results/f07_<week>_<scenario>_steps.csv` | Per step: voltages at all 21 buses, losses, transformer loading, oil and hot-spot temperature, ageing rate |
| `results/summary.json` | One summary per case (losses, violation bus-hours, peak loading, hot-spot, ageing) |
| `results/figures/*.png` | Graphs 3-8 for the deck |

## The model

- **Network:** the 315 kVA transformer (IS 1180 Level 2: 4.5 % impedance; losses 1,025 W at half load, 3,100 W at full load) feeds three radial circuits of 600 m of 3×95 mm² LT aerial bunched cable (MSEDCL specification, IS 14255), seven buses each, with the 1,090 homes spread evenly (about 52 per bus). The clinic is on bus 4, the school on bus 11, the water pump at the far end of circuit C.
- **Load flow:** `bfs_loadflow.m`, a backward/forward sweep, balanced, per unit on 315 kVA / 415 V. One solve per 15-minute step.
- **Transformer thermal model:** `dt_thermal.m`, the IEC 60076-7 difference equations with 1-minute sub-steps; relative ageing V = 2^((θh − 98)/6).
- **Scenarios** (`f07_params.json`): baseline; GridSetu with the battery and community PV at the transformer; GridSetu with the same storage split across the middle bus of each circuit.

## Checks

1. `test_bfs.m`: the solver matches an exact hand calculation to 1e-9.
2. `run_f07.m` stops if the bus loads minus storage do not add up to the Python simulator's feeder import (within 0.01 kW) at any step.
3. `run_f07.m` compares every step with the Python twin (`src/gridsetu/lvnetwork.py`); `tests/test_lvnetwork.py` does the same from Python.

The committed `results/` were produced by `run_f07.m` and checked against the Python twin.

## Simulink: the critical bus islanding (milliseconds to seconds)

The load-flow model above works in 15-minute steps. `islanding/` shows the moment that matters
most at a resolution of 0.1 ms: the feeder trips at 18:45, and the battery inverter must keep the
clinic, school, water pump and street lights alive.

```matlab
cd matlab/islanding
run_islanding        % builds gridsetu_islanding.slx, runs GridSetu and the baseline in Simulink
```

Needs Simulink (R2020b or newer); without Simulink, or in Octave, `run_islanding(false)` runs
the same model as a plain loop. It prints the key numbers and writes
`results/islanding_summary.json` and `results/islanding_waveforms.png`.

**The sequence (compressed outage, 9 s):**

Three variants: 0 baseline (no battery), 1 GridSetu with an inverter that follows the grid and an
ordinary island switch, 2 GridSetu with an inverter that is always grid-forming and a static
transfer switch (recommended).

| Time | Event | Variant 1 | Variant 2 (recommended) | Baseline |
|---|---|---|---|---|
| 1.00 s | Feeder breaker opens | Voltage collapses to 0.55 pu | Inverter holds 0.34 pu at its current limit | Critical bus dark |
| | Island formed | after 100 ms (40 ms detect + 60 ms switch) | after 4 ms (static switch, ABB published sense + transfer < 4 ms) | |
| | Below 0.7 pu / below 0.9 pu | 100 ms / 115 ms | 12 ms / 23 ms | |
| | ITIC ride-through for sensitive electronics | outside | **within** | |
| 2.5 s | Water pump starts (direct-on-line, 5× current) | Voltage dips to 0.965 pu, frequency to 49.84 Hz, secondary control restores 50 Hz | same | |
| 5.0 s | Grid returns, 115° out of phase | Island speeds up 0.3 Hz to catch the grid's phase | same | Critical bus back on |
| 6.94 s | Within 10° and 0.1 Hz for 0.2 s | Tie closes in phase; battery ramps back to its 90 kW dispatch | same | |

The recommended design needs a grid-forming inverter and a static transfer switch, whose extra
cost is still to be quoted.

**How it is built.** `build_islanding_model.m` generates the Simulink model as code: a Digital
Clock, a MATLAB Function block (`GridSetu critical bus`) that calls `islanding_step.m`, a Unit
Delay holding the 16 states, a To Workspace block and four scopes (frequency, voltage, inverter
power, battery current). `islanding_reference.m` runs the same step function as a plain loop;
`run_islanding` checks that Simulink reproduces it and prints the largest difference (0 in MATLAB R2025a). Open the diagram with `open_system('gridsetu_islanding')`.

**What it is, and is not.** An average-value (RMS) model: the inverter is a controlled voltage
source behind its control loops (1 % frequency droop, 5 % voltage droop, secondary frequency
restoration, 1.1× current limit), loads are constant impedance (ITIC is the CBEMA curve for IT
equipment, used as a guide), and the pump start is a decaying
inrush current. It does not model switching ripple or individual phases. Detection, switch and
control settings are assumptions in `islanding_params.m`, each marked, to be confirmed with an
inverter vendor and against the DISCOM's protection settings.
