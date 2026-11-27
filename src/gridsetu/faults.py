"""Fault study for pilot feeder F07: fault current in grid mode and in island mode, and whether
the protection sees it.

    python -m gridsetu fault-study      # writes outputs/faults/faults.json and a chart

Method: IEC 60909-0 style short-circuit calculation with an equivalent voltage source at the
fault (voltage factor c, maximum and minimum cases), on the same network as the low-voltage
study (matlab/f07_params.json): 11 kV source, 315 kVA Dyn11 transformer, three street circuits
and a dedicated critical-load circuit in LT aerial bunched cable.

* Grid mode: three-phase (maximum) and phase-to-neutral (minimum) fault current at every bus.
* Island mode: the grid-forming inverter is the only source and is current-limited, so the fault
  current is the inverter's limit wherever the fault is.
* Protection: electronic trip units with an adjustable short-time pickup (Schneider ComPacT NSX
  MicroLogic 2.2: Isd 1.5 to 10 x Ir, +/-15 %, non-trip 20 ms, maximum break 80 ms). A fault is
  "cleared fast" when the smallest fault current exceeds the highest possible pickup
  (Isd x 1.15); a load or motor start must stay below the lowest (Isd x 0.85).
* Fault location: the meters' voltage during a phase-to-neutral fault, with measurement noise,
  identifies the faulted segment.

Every input is tagged SOURCED (with its source) or ASSUMED.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PARAMS = ROOT / "matlab" / "f07_params.json"

INPUTS = {
    "source_fault_level_mva": {
        "value": 250.0, "tag": "ASSUMED",
        "note": "short-circuit level at the 11 kV side of the transformer; LV results move little "
                "with it because the transformer impedance dominates (sensitivity: 100 and 500 MVA)"},
    "source_x_over_r": {"value": 10.0, "tag": "ASSUMED", "note": "11 kV network X/R"},
    "c_max": {"value": 1.10, "tag": "SOURCED", "note": "IEC 60909-0 voltage factor, LV 230/400 V, maximum"},
    "c_min": {"value": 0.95, "tag": "SOURCED", "note": "IEC 60909-0 voltage factor, LV, minimum"},
    "temp_max_fault_c": {"value": 20.0, "tag": "SOURCED",
                         "note": "IEC 60909-0: conductor resistance at 20 C for maximum currents"},
    "temp_min_fault_c": {"value": 80.0, "tag": "ASSUMED",
                         "note": "conductor temperature at the end of the fault, for minimum currents"},
    "transformer_z0_over_z1": {"value": 1.0, "tag": "ASSUMED",
                               "note": "Dyn11 transformer: zero-sequence impedance about equal to positive"},
    "inverter_rating_kva": {"value": 100.0, "tag": "SOURCED", "note": "config/city.yaml battery inverter"},
    "inverter_current_limit_pu": {
        "value": 1.1, "tag": "ASSUMED",
        "note": "same short-term current limit as the islanding model (matlab/islanding/islanding_params.m)"},
    "street_breaker_ir_a": {
        "value": 200.0, "tag": "ASSUMED",
        "note": "long-time setting of each street circuit's breaker, above its evening peak current"},
    "trip_isd_range_x_ir": {
        "value": [1.5, 10.0], "tag": "SOURCED",
        "note": "Schneider ComPacT NSX MicroLogic 2.2 user guide: Isd adjustable 1.5 to 10 x Ir, "
                "precision +/-15 %, non-trip time 20 ms, maximum breaking time 80 ms",
        "url": "https://productinfo.se.com/compactnsxuserguide/doca0187-compact-nsx-user-guide/"},
    "trip_tolerance": {"value": 0.15, "tag": "SOURCED", "note": "same user guide, Isd precision"},
    "critical_leg_ir_a": {"value": 36.0, "tag": "ASSUMED",
                          "note": "40 A trip unit set to 0.9 x 40 A on each critical-circuit leg"},
    "critical_legs": {
        "value": {"health_subcentre": {"m": 342.9, "kw": 12.0, "pf": 0.95},
                  "school": {"m": 342.9, "kw": 8.0, "pf": 0.90},
                  "water_pumping": {"m": 600.0, "kw": 15.0, "pf": 0.85}},
        "tag": "ASSUMED",
        "note": "dedicated critical-load circuit from the battery yard, one leg per site, same cable; "
                "distances as the sites' street buses; loads from config/city.yaml (school at its daytime peak)"},
    "pump_dol_start_x_flc": {"value": 5.0, "tag": "ASSUMED",
                             "note": "direct-on-line start, as in the islanding model"},
    "pump_soft_start_x_flc": {"value": 2.5, "tag": "ASSUMED",
                              "note": "soft starter current limit (typical settings 2 to 4 x FLC)"},
    "meter_voltage_noise_pct": {"value": 1.0, "tag": "ASSUMED",
                                "note": "accuracy of the smart meter's voltage reading during a sag"},
}


def _v(k):
    return INPUTS[k]["value"]


def _network(p: dict):
    un = p["v_nominal_ll_v"]
    t = p["transformer"]
    ln = p["line"]
    # source referred to LV (IEC 60909: Z_Q = c U_n^2 / S''_kQ)
    zq = _v("c_max") * un ** 2 / (_v("source_fault_level_mva") * 1e6)
    rq = zq / math.sqrt(1 + _v("source_x_over_r") ** 2)
    ZQ = complex(rq, rq * _v("source_x_over_r"))
    # transformer, with the IEC 60909 correction factor K_T
    ur, sr = t["lv_open_circuit_v"], t["rating_kva"] * 1e3
    zt = t["impedance_pct"] / 100 * ur ** 2 / sr
    rt = t["load_loss_w"] * ur ** 2 / sr ** 2
    xt = math.sqrt(zt ** 2 - rt ** 2)
    kt = 0.95 * _v("c_max") / (1 + 0.6 * xt / (ur ** 2 / sr))
    ZT = kt * complex(rt, xt)
    return un, ZQ, ZT, ln


def _line_per_km(ln: dict, temp_c: float):
    a = ln["alpha_al"]
    zph = complex(ln["r_ohm_per_km_20c"] * (1 + a * (temp_c - 20)), ln["x_ohm_per_km"])
    rn = ln["neutral_messenger"]["r_ohm_per_km_20c"] * (1 + a * (temp_c - 20))
    zloop = complex(zph.real + rn, 2 * ln["x_ohm_per_km"])   # phase out, neutral back
    return zph, zloop


def fault_currents(p: dict, dist_m: float, s_mva: float | None = None) -> dict:
    """Grid-mode fault currents (A) at a point dist_m along a circuit."""
    un, ZQ, ZT, ln = _network(p)
    if s_mva is not None:
        ZQ = ZQ * _v("source_fault_level_mva") / s_mva
    km = dist_m / 1000
    zph20, zl20 = _line_per_km(ln, _v("temp_max_fault_c"))
    zphh, zlh = _line_per_km(ln, _v("temp_min_fault_c"))
    u0 = un / math.sqrt(3)
    z0t = _v("transformer_z0_over_z1")
    ik3_max = _v("c_max") * u0 / abs(ZQ + ZT + zph20 * km)
    # phase-to-neutral: I = 3 c U0 / |2 Z_Q + (2 + z0t) Z_T + 3 Z_loop|   (Dyn: Z_Q has no zero sequence)
    ik1_max = 3 * _v("c_max") * u0 / abs(2 * ZQ + (2 + z0t) * ZT + 3 * zl20 * km)
    ik1_min = 3 * _v("c_min") * u0 / abs(2 * ZQ + (2 + z0t) * ZT + 3 * zlh * km)
    ik3_min = _v("c_min") * u0 / abs(ZQ + ZT + zphh * km)
    return {"ik3_max": ik3_max, "ik3_min": ik3_min, "ik1_max": ik1_max, "ik1_min": ik1_min}


def _flc(kw: float, pf: float, un: float) -> float:
    return kw * 1e3 / (math.sqrt(3) * un * pf)


def locate_faults(p: dict, n_trials: int = 200, seed: int = 7) -> dict:
    """Phase-to-neutral fault at each bus of a street circuit; meters on every bus read their voltage
    during the fault (with noise). The fault is placed at the first bus beyond which the voltage stops
    falling. Returns the share of trials placed on the right bus."""
    un, ZQ, ZT, ln = _network(p)
    topo = p["topology"]
    n, seg_km = topo["buses_per_circuit"], topo["circuit_length_m"] / topo["buses_per_circuit"] / 1000
    _, zl = _line_per_km(ln, 50.0)
    u0 = un / math.sqrt(3)
    zsrc = (2 * ZQ + (2 + _v("transformer_z0_over_z1")) * ZT) / 3
    noise = _v("meter_voltage_noise_pct") / 100
    rng = np.random.default_rng(seed)
    right, total, worst_sag = 0, 0, []
    for k in range(1, n + 1):
        i_f = u0 / abs(zsrc + zl * seg_km * k)
        # voltage (pu) at bus j: drop from bus j to the fault; beyond the fault no fault current flows
        v = np.array([abs(i_f * zl * seg_km * max(k - j, 0)) / u0 for j in range(1, n + 1)])
        worst_sag.append(float(v.max()))
        for _ in range(n_trials):
            m = v + rng.normal(0, noise, n)
            # first bus whose reading is within 2 noise sigmas of the downstream readings' mean
            est = n
            for j in range(n):
                if m[j] - m[j:].mean() < 2 * noise * 1.0:
                    est = j + 1
                    break
            right += int(est == k)
            total += 1
    return {"buses": n, "trials": total, "located_on_right_bus_pct": round(100 * right / total, 1),
            "highest_meter_voltage_during_fault_pu": round(max(worst_sag), 3)}


def run_study(out_dir: str | Path = "outputs/faults", params_path: str | Path = PARAMS) -> dict:
    p = json.loads(Path(params_path).read_text(encoding="utf-8"))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    un = p["v_nominal_ll_v"]
    topo = p["topology"]
    n = topo["buses_per_circuit"]
    pos = [round((k + 1) * topo["circuit_length_m"] / n, 1) for k in range(n)]
    tol = _v("trip_tolerance")
    isd_lo = _v("trip_isd_range_x_ir")[0]

    # --- grid mode, street circuits --------------------------------------------------------
    street = [{"position_m": m, **{k: round(v) for k, v in fault_currents(p, m).items()}} for m in pos]
    ir = _v("street_breaker_ir_a")
    isd = isd_lo * ir
    tail_min = min(r["ik1_min"] for r in street)
    sens = {f"{s:.0f}_mva": round(fault_currents(p, pos[-1], s)["ik1_min"]) for s in (100, 500)}
    grid = {
        "street_buses": street,
        "transformer_terminals_ik3_max_a": round(fault_currents(p, 0)["ik3_max"]),
        "tail_ik1_min_a": round(tail_min),
        "tail_ik1_min_sensitivity_a": sens,
        "street_breaker": {"ir_a": ir, "isd_a": isd, "isd_highest_a": round(isd * (1 + tol)),
                           "clears_every_street_fault_fast": bool(tail_min > isd * (1 + tol)),
                           "tail_fault_over_10x_ir": round(tail_min / (10 * ir), 2)},
    }

    # --- island mode: current-limited inverter ----------------------------------------------
    i_rated = _v("inverter_rating_kva") * 1e3 / (math.sqrt(3) * un)
    i_island = _v("inverter_current_limit_pu") * i_rated
    legs = {}
    ir_c = _v("critical_leg_ir_a")
    for name, leg in _v("critical_legs").items():
        flc = _flc(leg["kw"], leg["pf"], un)
        start = flc * (_v("pump_dol_start_x_flc") if name == "water_pumping" else 1.0)
        soft = flc * (_v("pump_soft_start_x_flc") if name == "water_pumping" else 1.0)

        def setting(peak):
            """lowest Isd step (x Ir, 0.5 steps) whose lowest pickup stays above the peak load"""
            x = isd_lo
            while x * ir_c * (1 - tol) <= peak and x < 10:
                x += 0.5
            return x
        x_dol, x_soft = setting(start), setting(soft)
        grid_min = fault_currents(p, leg["m"])["ik1_min"]
        legs[name] = {
            "length_m": leg["m"], "full_load_a": round(flc, 1),
            "start_current_dol_a": round(start, 1), "start_current_soft_a": round(soft, 1),
            "grid_fault_min_a": round(grid_min),
            "isd_with_dol_start_a": round(x_dol * ir_c), "isd_with_soft_start_a": round(x_soft * ir_c),
            "island_fault_cleared_with_dol_start": bool(i_island > x_dol * ir_c * (1 + tol)),
            "island_fault_cleared_with_soft_start": bool(i_island > x_soft * ir_c * (1 + tol)),
            "grid_fault_cleared": bool(grid_min > x_soft * ir_c * (1 + tol)),
        }
    island = {
        "inverter_rated_current_a": round(i_rated, 1),
        "fault_current_a": round(i_island, 1),
        "fault_current_over_grid_tail_min": round(i_island / tail_min, 3),
        "street_breaker_sees_it": bool(i_island > isd * (1 - tol)),
        "critical_legs": legs,
    }
    res = {
        "about": {"label": "SIMULATION: IEC 60909-0 style fault calculation on the assumed F07 network "
                           "(matlab/f07_params.json); not a protection design.", "inputs": INPUTS},
        "grid_mode": grid,
        "island_mode": island,
        "fault_location": locate_faults(p),
    }
    (out / "faults.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    _chart(res, out / "fault_currents.png")
    return res


def _chart(res: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .plots import GREY, INK, TEAL, AMBER, SIM_LABEL
    g, isl = res["grid_mode"], res["island_mode"]
    xs = [0] + [r["position_m"] for r in g["street_buses"]]
    p = json.loads(PARAMS.read_text(encoding="utf-8"))
    mx = [fault_currents(p, x)["ik3_max"] for x in xs]
    mn = [fault_currents(p, x)["ik1_min"] for x in xs]
    fig, ax = plt.subplots(figsize=(10, 5.2), dpi=200)
    ax.plot(xs, np.array(mx) / 1e3, color=INK, lw=2.4, label="Grid mode, largest (three-phase, IEC 60909 c max)")
    ax.plot(xs, np.array(mn) / 1e3, color=GREY, lw=2.4, label="Grid mode, smallest (phase to neutral, c min, hot cable)")
    ax.axhline(isl["fault_current_a"] / 1e3, color=TEAL, lw=2.4,
               label=f"Island mode: inverter current limit, {isl['fault_current_a']:.0f} A anywhere")
    sb = g["street_breaker"]
    ax.axhline(sb["isd_highest_a"] / 1e3, color=AMBER, lw=1.6, ls="--",
               label=f"Street breaker short-time pickup, worst case {sb['isd_highest_a']} A")
    ax.set_yscale("log")
    ax.set_xlabel("Distance from the transformer along a street circuit (m)")
    ax.set_ylabel("Fault current (kA, log scale)")
    ax.set_title("Fault current on feeder F07: grid mode against island mode", loc="left", fontweight="bold")
    ax.grid(alpha=0.3, which="both")
    ax.legend(loc="upper right", fontsize=8.5, frameon=False)
    fig.text(0.99, 0.01, SIM_LABEL + " · IEC 60909-0 method, assumed network", ha="right", fontsize=7, color=GREY)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
