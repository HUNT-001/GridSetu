# Changelog

## Unreleased: households against real Indian data (November 2026)

### Added
- `data/real/emarc_mainline_summary.json`: a summary of Prayas eMARC smart-meter data (116 homes, 2018–20, CC0), from 6.1 million readings, with checks.
- `python -m gridsetu household-check [--sensitivity]`: our homes against measured homes and the Tamil Nadu average; the same feeder demand over 420, 720 and 1,030 homes. Chart, README section, data card, Q&A; 2 tests (71).

### Found
- Our synthetic homes use 8.6 kWh a day (measured 4.6; TN average 3.5) and are far too coincident (0.85 vs 0.35). Feeder-level results hold with more, lighter homes; lifeline helps less.

## Unreleased: business case (November 2026)

### Added
- `python -m gridsetu economics`: a year of the pilot feeder priced with real IEX prices. Costs come from the 2025 Indian battery benchmark tariff (×2 for small scale), smart plugs, and controller and comms. It reports the break-even value of an avoided kWh of outage (₹21.8) and a sensitivity on four assumptions. Results and 2 charts in `outputs/economics/`; README section "What it costs, and when it pays"; figures in `numbers.json`; checked by `reproduce.sh`.
- Data card: business-case inputs with sources. Q&A: money questions.
- 2 tests (69 in total).

### Fixed
- README test counts (badge said 59, table 63).

## Unreleased: lifeline mode and the second confidence (November 2026)

### Added
- **Lifeline mode** (`pilot_feeder.lifeline`, on): when a DISCOM request exceeds battery and flexible load, every home's smart meter is capped at a common limit (at least 200 W) instead of the feeder being switched off. New metrics: dark and lifeline home-hours.
- The Reliability Reserve publishes a firm **call capacity** and a **call confidence**; `calibrate` scores it. `calibrate --bounded-calls` runs the ADMS dispatch case where calls are bounded by the day-ahead offer (`outputs/calibration_bounded/`).
- Dashboard: lifeline state and dimly lit lifeline homes.
- 4 tests (67 in total).

### Changed (headline figures)
- GridSetu evening unserved energy 529 → 484 kWh/month (−82%); whole-feeder outage 2.8 → 0.5 h/month; home-hours without supply 5,740 (baseline) → 291.
- DISCOM call evenings met: 0 → 20 of 60 (calls as today); 58 of 60 with calls bounded by the offer.
- 20-feeder fleet, stress week, full adoption: home-hours dark −75% (was −26%).
- MATLAB low-voltage results re-run on the new loads (GridSetu losses 2,215 → 2,226 kWh; agreement with the Python twin 5e-9).

### Fixed
- An accepted DISCOM cap outside the rotation group could be missed with no consequence; lifeline now meets it or the shortfall is visible.
- Missed calls are recorded at their full size.
- The README results chart is now the generated one (`outputs/charts/slide8_baseline_vs_proposed.png`), not a static copy.

## Unreleased: real weather and prices (November 2026)

### Added
- `data/real/`: NASA POWER hourly weather for Coimbatore (20 Jul to 21 Sep 2025) and IEX day-ahead 15-minute prices (14–20 Sep 2025), each checked against totals published by its source.
- `docs/DATA_CARD.md`: every input labelled REAL, DERIVED, SOURCED or SYNTHETIC, with sources and checks.
- `simulation.weather_source: nasa_power` and `exchange_price.source: iex` in `config/city.yaml` (defaults unchanged: synthetic).
- `python -m gridsetu real-data`: price check, weather check, forecast backtest on real weather and the stress week on real inputs. Results and 3 charts in `outputs/real_data/`; figures in `numbers.json`; README section "Checked against real weather and real prices".
- 4 tests (63 in total). `scripts/reproduce.sh` now also checks `outputs/real_data/real_data.json`.

### Found
- Real evening prices reached the ₹10/kWh ceiling on 6 of 7 days; our curve stops at ₹9.8. Real midday prices averaged ₹1.17/kWh against our ₹2.6.
- Real monsoon sunshine averaged 4.13 kWh/m²/day over 63 days against 5.15 in our synthetic weather.
- Forecast coverage on real weather is 79.2% (84.8% on synthetic weather).
- On the real stress week GridSetu's evening unserved energy is 408 kWh (617 kWh on the synthetic week, which is harsher).

## Unreleased: MATLAB low-voltage model (November 2026)

### Added
- `matlab/`: low-voltage model of feeder F07 (`run_f07.m`, `bfs_loadflow.m`, `dt_thermal.m`, `make_figures.m`, `test_bfs.m`), with all parameters and their sources in `f07_params.json`. Results in `matlab/results/`.
- `python -m gridsetu lv-study`: the Python twin (`lvnetwork.py`) and the six deck charts (`outputs/lv/charts/`).
- Low-voltage figures in `numbers.json` and a README results section.
- 5 tests: hand-calculated load flow, thermal steady state, energy balance, voltage profile, and step-by-step agreement with the MATLAB results (59 in total).

### Found
- A battery at the transformer bus cuts the transformer's peak loading (1.37 → 1.19 pu) but not line losses or voltage drop; splitting the storage across the circuits cuts technical losses about 7%. Voltage is outside ±6% on the assumed network in every case.

## Unreleased: trust, calibration and the MATLAB bridge (November 2026)

### Added
- `outputs/numbers.json`, generated by `python -m gridsetu numbers`: every headline figure with its value, unit, quoted text and source path, plus the run's git commit and library versions. `--check FILE...` fails if a document quotes a figure that no longer matches.
- `python -m gridsetu calibrate --seeds 30`: checks all 1,260 published reserve confidences (30 seeds × 2 weeks × 3 stages) against what happened, scoring own peak, DISCOM call and end to end separately, with Brier scores. Writes `outputs/calibration/`. README section "Does the Reliability Reserve keep its word?".
- `python -m gridsetu export-matlab`: per-bus load profiles of feeder F07 (21 buses, 3 circuits) for the MATLAB low-voltage model, with a balance test. Files in `outputs/matlab/`.
- `requirements-lock.txt` (exact versions) and `scripts/reproduce.sh`, which re-runs the full study and fails if any committed value changes.
- GitHub Actions CI: tests, README figure check and full reproduction on every push and pull request.
- `AI_USAGE.md`, `docs/TEAM_BRIEF.md`, `docs/QA_BANK.md`.
- 9 tests for the registry, calibration scoring and the MATLAB export (54 in total).

### Changed
- `outputs/` regenerated under the pinned versions. Absolute figures moved slightly (GridSetu evening unserved energy 546 → 529 kWh; baseline critical-load outage 13.6 → 13.7 h; GridSetu whole-feeder outage 2.9 → 2.8 h). Every percentage change is unchanged.

### Fixed
- README: a baseline seed-range typo, now checked automatically.
- README: "no home twice in a row" now states the exception the code already logs (4 intervals in the stress week).

### Found
- The published confidence covers only the feeder's own evening peak, which held on all 1,260 forecasts. On all 60 evenings with a DISCOM call, the request was 1.2 to 4.3 times the published reserve and was not met. Stated in the README results and limitations.
- `feeder.py`: outside the rotation group a feeder accepts any DISCOM cap, even one it can't meet, and the unmet part has no consequence. To be fixed with the two-confidence reserve.
