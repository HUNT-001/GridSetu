# Two things the brief names that we haven't shown yet

Status: **list only, nothing built.** 25 Nov 2026. Effort is for one person with Claude helping,
including tests.

## (a) "Identify voltage violations" on the DISCOM dashboard

**What exists:** per-step voltages at all 21 LV buses for six cases
(`matlab/results/f07_<week>_<scenario>_steps.csv`, columns `v_bus_01`..`v_bus_21`, `v_min_pu`,
`n_bus_under`, `n_bus_over`), weekly summaries in `matlab/results/summary.json`, and a Python
twin (`src/gridsetu/lvnetwork.py`) that reproduces them to 1e-8. The 11 kV power flow
(`network.py`) also records `feeder_min_v_pu` and `feeder_tail_v_pu` per step. Nothing on the
dashboard reads any of this.

**Read `TOPOLOGY.md` first.** On today's LV layout, voltage is out of ±6% in 94–99% of
steps in every scenario, and GridSetu doesn't change that (1,869 → 1,896 bus-hours on the
stress week). A card built on that layout would show a wall of red with no GridSetu effect,
which invites the question "is your network wrong?". Build the card after the layout
decision, or label it clearly as "assumed network, layout under review".

| Step | Files | Effort |
|---|---|---|
| Ship the per-bus voltage table in a run: pack the MATLAB step CSVs (or run the Python twin) into a new `lv` payload, per week and scenario | `src/gridsetu/api/engine.py` (new `lv_payload`), `src/gridsetu/api/app.py` (`RESOURCES`), `web/src/lib/types.ts`, `web/src/lib/queries.ts` | 1.5 h |
| Feeder-stress card on `/feeder`: bus × time heat strip of voltage, buses outside the limit outlined, worst bus and its hours, loss kWh, peak transformer loading | `web/src/components/charts/` (new heat-strip component), `web/src/pages/feeder.tsx` | 3 h |
| Limits from config, not hard-coded: ±6% today, +6/−10% if the TNERC clause is confirmed | `matlab/f07_params.json` `v_limit_pu`, read by the payload | 0.5 h |
| "Recommend demand response" link: show which buses improve when Tier 3 is paused (needs a run with and without the pause on the bus loads) | `lvnetwork.py` (a what-if function), payload | 2 h, optional |
| Register the figures shown on the card in `numbers.json` (already done for the weekly summaries: `lv.*` keys) | `src/gridsetu/numbers.py` | 0 |
| Static snapshot for the hosted fallback | `npm run build:demo` | 0.25 h |

**Total: about 5 h, plus 2 h for the optional what-if.** It depends on the topology decision,
and on Priyadharshan rerunning MATLAB if the layout changes.

## (b) Peer-to-peer or cooperative pooling

**Correction to our own description.** The 20-feeder fleet study does **not** pool anything
between feeders. `src/gridsetu/fleet.py` says so explicitly: "Feeders do not interact:
DISCOM requests are a share of each feeder's own load (no feeder can push its burden onto a
neighbour)". Calling it pooling would be wrong.

**What we already have, and can honestly call cooperative pooling,** is pooling *within* the
feeder:
- **Shared community storage:** one 200 kWh battery owned by the resident cooperative and
  used for all 1,090 homes, with a fixed priority order (Tier 1 reserve first).
- **Pooled flexibility with fair access:** the fairness ledger (`src/gridsetu/fairness.py`)
  rotates Tier-3 pauses across homes. On the stress week 829 homes shared the curtailment,
  at most 5.5 h each, Gini 0.21, with 1,471 overrides honoured (`outputs/results.json`,
  `fairness_stress_week`).
- **One aggregated offer to the DISCOM:** the Reliability Reserve turns many small loads into
  one forecast, confidence-scored product.

That covers the brief's "shared storage with fair access and dispatch rules" and "cooperative
pooling". **Peer-to-peer trading is not in the model** and shouldn't be claimed.

| Option | What it takes | Files | Effort |
|---|---|---|---|
| **1. Name what exists** (recommended for 5 Dec) | One README section and one deck line: "cooperative pooling within the feeder", with the fairness figures from `numbers.json`; fix the fleet text so nobody calls it cross-feeder pooling | `README.md`, deck, `docs/QA_BANK.md` | 0.5 h |
| **2. Cross-feeder pooling of relief** | When the DISCOM asks R3 for X MW, allocate it across GridSetu feeders by their published call capacity instead of a fixed share of each feeder's load, so a feeder with a full battery covers a neighbour's shortfall. The energy itself is netted at the 33/11 kV substation; no new wires. Report rotation hours avoided on the neighbours. | `src/gridsetu/fleet.py` (allocation step before `simulate_feeder`), `src/gridsetu/feeder.py` (accept an allocated request instead of `shed_frac`), `tests/test_phase2.py`, fleet page text | 1–1.5 days; changes the fleet results |
| **3. Peer-to-peer settlement** | A ledger crediting households whose paused load freed capacity used by others (in ₹ or kWh credits); payout rules; no physical change | new `src/gridsetu/settlement.py`, households page | 1 day for a simple version; needs a regulatory note (P2P trading isn't permitted for most Indian consumers, **to verify**) |
