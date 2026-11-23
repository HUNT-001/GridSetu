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

- **Network:** the 315 kVA transformer (IS 1180 Level 2: 4.5 % impedance; losses 1,025 W at half load, 3,100 W at full load) feeds three radial circuits of 600 m, ACSR Rabbit, seven buses each, 20 homes per bus. The clinic is on bus 4, the school on bus 11, the water pump at the far end of circuit C.
- **Load flow:** `bfs_loadflow.m`, a backward/forward sweep, balanced, per unit on 315 kVA / 415 V. One solve per 15-minute step.
- **Transformer thermal model:** `dt_thermal.m`, the IEC 60076-7 difference equations with 1-minute sub-steps; relative ageing V = 2^((θh − 98)/6).
- **Scenarios** (`f07_params.json`): baseline; GridSetu with the battery and community PV at the transformer; GridSetu with the same storage split across the middle bus of each circuit.

## Checks

1. `test_bfs.m`: the solver matches an exact hand calculation to 1e-9.
2. `run_f07.m` stops if the bus loads minus storage do not add up to the Python simulator's feeder import (within 0.01 kW) at any step.
3. `run_f07.m` compares every step with the Python twin (`src/gridsetu/lvnetwork.py`); `tests/test_lvnetwork.py` does the same from Python.

The committed `results/` were produced by `run_f07.m` and checked against the Python twin.
