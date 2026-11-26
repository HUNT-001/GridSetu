# How it works physically: which device switches what, and the rules for an island

Status: **design note, no code.** Written 25 Nov 2026. The simulator decides *what* to switch;
this says *with what*, *who installs it* and *what keeps it safe*. Anything marked
**to verify** needs a datasheet, a clause number or a DISCOM conversation before it goes in the
deck. No price here is sourced. Costs are either the repo's existing assumptions
(`config/city.yaml`, `economics:`) or slots for `docs/economics/cost_inputs.md`.

## 1. The problem in one paragraph

The simulator says "Tier 1 stays on, Tier 3 pauses, everyone else gets 200 W". On the wires,
the clinic, the school and about 360 homes share the same low-voltage circuit
(`outputs/matlab/f07_buses.csv`: the health sub-centre is on bus 4 of circuit A). So keeping
"only the clinic" alive during an outage needs something that **separates the clinic from
the homes** before the battery inverter energises it. Otherwise the inverter tries to supply
the whole circuit and collapses (the Simulink model shows the voltage falling to 0.55 pu in
the first 100 ms for exactly this reason). The same goes for every tier: each one needs
a named device with an owner.

## 2. The device for each action

| Action in the model | Device that does it | Where it sits | Who owns / installs | Assumed cost per home |
|---|---|---|---|---|
| **Rotation trip** (DISCOM sheds the feeder) | 11 kV feeder circuit breaker at the 33/11 kV substation, operated from SCADA/ADMS or by the substation operator | Substation | DISCOM, exists today | ₹0 (existing) |
| **Tier 1 island** (clinic, school, pump, street lights stay on) | (a) an **island breaker** (4-pole, motorised, with auxiliary contacts) between the transformer's LV busbar and a *dedicated* critical circuit, plus (b) a **grid-forming battery inverter** on the critical side and (c) a **synchronising check relay** for reconnection | Battery site next to the distribution transformer | Cooperative / O&M partner, installed by a licensed electrical contractor; DISCOM approves the protection scheme | Shared equipment ÷ 1,090 homes: **PENDING_SOURCE** (breaker, sync relay, protection panel) |
| **Tier 1, without a dedicated circuit** (today's LV layout) | Every home on the clinic's circuit disconnected by its **smart-meter relay** before the inverter starts | Each home | DISCOM (meters) | ₹0 extra, but **not recommended**: hundreds of relays must all confirm open, in seconds, before the inverter can form the island |
| **Lifeline** (every home capped at 200 W) | The **load-limit function and internal latching relay of the prepaid smart meter** (IS 16444), set by the DISCOM's head-end system | Each home's meter | DISCOM, installed under RDSS | ₹0 incremental if the meter comes from the RDSS rollout (**to verify**: who pays, and whether remote real-time changes of the limit are supported) |
| **Tier 3 pause, plug-in load** (two-wheeler charger, portable heater, cooler) | A **smart plug** (16 A, relay, 4G or Wi-Fi) | Socket | Cooperative, handed to the household | ₹1,500 installed, 5-year life (existing ASSUMPTION in `config/city.yaml`, `economics.tariff_method.smart_plug_inr_per_home`) |
| **Tier 3 pause, hard-wired load** (water heater/geyser on its own circuit, AC on a 16 A point) | A **relay or contactor module** on that circuit | Home distribution board | Licensed electrician (CEA Safety Regulations: work on consumer installations by licensed persons, **to verify** the exact clause) | **PENDING_SOURCE** (module + electrician visit); the model costs every home at the smart-plug price |
| **Tier 2 shift** (micro-enterprise motor, with prior consent) | A **remote relay in the control circuit** of the motor's existing starter (direct-on-line starters already have a contactor) | Workshop | Enterprise's electrician under a cooperative contract | **PENDING_SOURCE**, about 26 of 35 workshops |
| **Household override** ("I need the geyser now") | The same smart plug or relay, commanded from the phone page or a button on the plug | Home | Household | included above |

Notes:
- **Only about 41% of measured homes own an AC or water heater** (eMARC, 89 of 216, see
  `economics.py`). Fitting Tier-3 devices only in those homes would cut the plug cost by more
  than half. The model doesn't do this yet.
- **Connectivity:** low-income homes often have no Wi-Fi. A 4G plug or a plug that talks to the
  smart meter's home-area interface avoids that (**to verify**: whether RDSS meters expose a
  usable HAN port).
- **The smart-meter path belongs to the DISCOM.** GridSetu cannot write to meters directly; it
  sends a request to the DISCOM's head-end system or MDM, which sets the limit. Rationing every
  home to 200 W in a shortage would need the state regulator's approval (already noted in
  the README, line 750).

## 3. The intentional island: safety rules

An island is the battery inverter deliberately supplying the critical circuit while the grid
is off. Three things must hold: it never back-feeds the grid, its faults are still cleared,
and it rejoins the grid safely.

### 3.1 Never back-feed the DISCOM's network (anti-islanding)

- **CEA (Technical Standards for Connectivity of the Distributed Generation Resources)
  Regulations, 2013, as amended (2019):** distributed generation must not energise a grid
  that is de-energised, and must disconnect on loss of grid supply ("anti-islanding").
  **To verify:** the clause numbers, and whether the regulations or a DISCOM's own
  connectivity procedure allow an *intentional* island behind an isolating device.
- **IEEE 1547-2018:** unintentional islands must be detected and the resource must stop
  energising the area within 2 s. Intentional islands are allowed (clause 8.2) when they are
  planned and the island is separated from the area power system by an isolation device.
  **To verify:** clause numbers against the standard text.
- **Inverter certification:** anti-islanding performance tested to IEC 62116 (Indian
  equivalent IS 16169, **to verify**).
- **How the design meets it:**
  1. The island breaker opens **first**. The inverter switches to grid-forming only when the
     breaker's auxiliary contact says *open* **and** there is no voltage on the grid side
     (two independent signals).
  2. The breaker is interlocked so it cannot close while the inverter is forming the island
     unless the synchronising check relay allows it.
  3. A visible, lockable isolation point for DISCOM line crews at the battery site, so a
     crew working on a "dead" feeder can prove it cannot be back-fed (**to verify** against
     the CEA (Measures relating to Safety and Electric Supply) Regulations, 2023).

### 3.2 Clearing faults inside the island (low fault current)

- On the grid, a short circuit on the LV circuit draws several kA from the transformer, and
  fuses and MCCBs clear it in milliseconds.
- An inverter delivers only about 1.1–1.5 times its rated current (the Simulink model assumes
  1.1 times, `matlab/islanding/islanding_params.m`). For a 33–100 kW inverter that is roughly
  50–230 A per phase, too little to blow fuses or trip MCCBs sized for grid faults.
  **To verify** with an inverter datasheet.
- **What the design needs:**
  - Small, selective protection on the critical circuit, sized to trip on the inverter's
    fault current (low-rated MCBs per load, not one large fuse).
  - Residual-current devices for earth faults, which don't depend on fault current magnitude.
  - The inverter's own undervoltage and overcurrent trip as backup.
  - If the protection relay supports it, a second settings group for island mode.
- **Earthing.** Indian LV networks earth the neutral at the transformer. If the island breaker
  is 4-pole and opens the neutral, the island has no neutral-earth bond unless the
  inverter makes one when it forms the island. A 3-pole breaker keeps the transformer's
  bond. **To verify** with a protection engineer which one TN practice requires.

### 3.3 Starting the water pump

The 15 kW pump starts direct-on-line at about 5 times rated current. In the Simulink model the
island rides through it (0.965 pu, 49.84 Hz). On a 33 kW inverter (one third of the battery,
layout C in `TOPOLOGY.md`) the margin would be much smaller. Options: size that inverter
larger, add a soft starter or VFD to the pump (**PENDING_SOURCE**), or start the pump only
when the grid is up.

### 3.4 Rejoining the grid

- The Simulink model resynchronises and closes the tie 1.94 s after the grid returns. That
  matches the physics of a synchronising check (within 10° and 0.1 Hz).
- **But IEEE 1547-2018's default enter-service delay is 300 s** after the grid returns to
  normal (adjustable). A DISCOM may require the island to wait. **To verify:** whether the
  enter-service delay applies to an intentional island reconnecting through a sync-check
  relay, and what the DISCOM requires. The deck should not claim "back in 2 seconds" until
  this is settled.
- The clinic's equipment sees under 0.9 pu for 115 ms at the transfer (Simulink result). That
  is outside the ITIC/CBEMA curve for sensitive electronics, so the clinic needs a small UPS
  or a faster transfer (already in `matlab/README.md`).

## 4. Who does what, in practice

| Role | Owns | Does |
|---|---|---|
| DISCOM | 11 kV breaker, transformers, smart meters, head-end system | Sends relief requests, sets meter load limits, approves the island protection scheme, keeps crew-safety procedures |
| Resident cooperative | Battery, inverter, island breaker, plugs and relays | Holds the assets and the household agreements |
| O&M partner (licensed electrical contractor) | Installation and maintenance | Installs breaker, inverter, home relays; tests protection yearly (**to verify** the test interval required) |
| Household | Its plug and phone | Agrees to Tier-3 pauses, can override |

## 5. Open items for the team

1. Confirm with a DISCOM engineer (Schneider's DISCOM contacts?) that an intentional island
   behind an interlocked breaker is acceptable under the CEA connectivity regulations.
2. Get one battery-inverter datasheet with grid-forming mode, fault current and anti-islanding
   certificate. It fixes the 1.1× assumption and the pump question.
3. Decide the critical-circuit layout (`TOPOLOGY.md`, layout C puts the clinic and school on
   a dedicated circuit). Without it, the Tier-1 island is not physically credible.
4. Parthasarathy: prices for the island breaker + sync relay + protection panel, the home relay
   module + electrician visit, and the Tier-2 relay, into `cost_inputs.md`.
5. Check the 300 s enter-service delay against the Simulink reconnection story.
