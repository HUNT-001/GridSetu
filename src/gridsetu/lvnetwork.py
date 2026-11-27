"""Low-voltage network study of pilot feeder F07: technical losses, voltage, transformer ageing.

The main simulator treats the feeder as one point. This module places the exported per-bus
loads (``python -m gridsetu export-matlab``) on a radial 415 V network and, for every
15-minute step, solves a balanced backward/forward-sweep load flow. It then runs the
IEC 60076-7 thermal model of the distribution transformer.

It is the Python twin of ``matlab/run_f07.m``. Both read ``matlab/f07_params.json`` and the
same input files, and must agree (see ``tests/test_lvnetwork.py``). MATLAB is the reference
for the submission; this twin lets the results be checked and tested without MATLAB.

    python -m gridsetu lv-study            # writes outputs/lv/
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PARAMS = ROOT / "matlab" / "f07_params.json"
WEEKS = ("stress", "representative")


def load_params(path: str | Path = PARAMS) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def network(p: dict) -> dict:
    """Per-unit radial network. Node 0 is the transformer LV busbar, fed from the 11 kV
    source through the transformer impedance; nodes 1..21 are the load buses."""
    base_kva, vn = p["base_kva"], p["v_nominal_ll_v"]
    zbase = (vn / 1000) ** 2 / (base_kva / 1000)                    # ohm
    tr = p["transformer"]
    r_pct = tr["load_loss_w"] / (tr["rating_kva"] * 1000) * 100
    x_pct = np.sqrt(tr["impedance_pct"] ** 2 - r_pct ** 2)
    scale = (tr["lv_open_circuit_v"] / vn) ** 2 * (base_kva / tr["rating_kva"])   # to 415 V / base kVA
    z_dt = complex(r_pct, x_pct) / 100 * scale
    topo, ln = p["topology"], p["line"]
    seg_km = topo["circuit_length_m"] / topo["buses_per_circuit"] / 1000
    z_seg = complex(ln["r_ohm_per_km"], ln["x_ohm_per_km"]) * seg_km / zbase
    n_bus = topo["circuits"] * topo["buses_per_circuit"]
    parent = np.zeros(n_bus + 1, dtype=int)
    parent[0] = -1
    for b in range(1, n_bus + 1):
        k = (b - 1) % topo["buses_per_circuit"]
        parent[b] = 0 if k == 0 else b - 1
    z = np.full(n_bus + 1, z_seg, dtype=complex)
    z[0] = z_dt
    v_src = tr["lv_open_circuit_v"] / vn
    return {"parent": parent, "z": z, "v_src": v_src, "n_bus": n_bus, "base_kva": base_kva,
            "zbase_ohm": zbase, "z_dt_pu": z_dt, "z_seg_pu": z_seg}


def bfs(net: dict, s_node: np.ndarray, tol: float = 1e-9, max_iter: int = 100):
    """Backward/forward sweep. s_node: complex load (pu, consumption positive) per node.
    Returns node voltages, branch currents (branch k feeds node k), iterations."""
    parent, z, n = net["parent"], net["z"], len(s_node)
    v = np.full(n, complex(net["v_src"]))
    for it in range(1, max_iter + 1):
        i_node = np.conj(s_node / v)
        i_br = i_node.copy()
        for k in range(n - 1, 0, -1):                 # children have higher indices
            i_br[parent[k]] += i_br[k]
        v_new = np.empty(n, dtype=complex)
        v_new[0] = net["v_src"] - z[0] * i_br[0]
        for k in range(1, n):
            v_new[k] = v_new[parent[k]] - z[k] * i_br[k]
        if np.max(np.abs(v_new - v)) < tol:
            return v_new, i_br, it
        v = v_new
    raise RuntimeError("backward/forward sweep did not converge")


def dt_thermal(K: np.ndarray, ambient: np.ndarray, on: np.ndarray, p: dict, step_min: float = 15.0):
    """IEC 60076-7 difference equations, sub-stepped. Returns top-oil and hot-spot
    temperature at the end of each step and the mean relative ageing rate over the step."""
    tr, th = p["transformer"], p["transformer"]["thermal"]
    R = tr["load_loss_w"] / tr["no_load_loss_w"]
    d_or, d_hr = tr["top_oil_rise_k"], th["hotspot_gradient_k"]
    x, y, k11, k21, k22 = th["x"], th["y"], th["k11"], th["k21"], th["k22"]
    tau_o, tau_w = th["tau_o_min"], th["tau_w_min"]
    dt = p["solver"]["thermal_substep_min"]
    nsub = int(round(step_min / dt))
    n = len(K)
    theta_o = np.empty(n)
    theta_h = np.empty(n)
    age = np.empty(n)
    k0 = K[0] if on[0] else 0.0
    to = ambient[0] + d_or * ((1 + R * k0 ** 2) / (1 + R)) ** x       # start in steady state
    h1, h2 = k21 * d_hr * k0 ** y, (k21 - 1) * d_hr * k0 ** y
    for t in range(n):
        k = K[t] if on[t] else 0.0
        # steady-state top-oil rise for this load; a de-energized transformer has no losses
        oil_ss = d_or * ((1 + R * k ** 2) / (1 + R)) ** x if on[t] else 0.0
        a = 0.0
        for _ in range(nsub):
            to += dt / (k11 * tau_o) * (oil_ss - (to - ambient[t]))
            h1 += dt / (k22 * tau_w) * (k21 * d_hr * k ** y - h1)
            h2 += dt / ((1 / k22) * tau_o) * ((k21 - 1) * d_hr * k ** y - h2)
            a += 2 ** ((to + h1 - h2 - th["ageing_reference_c"]) / th["ageing_doubling_k"])
        theta_o[t], theta_h[t], age[t] = to, to + h1 - h2, a / nsub
    return theta_o, theta_h, age


def run_case(loads: pd.DataFrame, feeder: pd.DataFrame, p: dict, storage_buses: list[int]) -> pd.DataFrame:
    net = network(p)
    base = net["base_kva"]
    n_bus = net["n_bus"]
    tanphi = np.tan(np.arccos(p["load_power_factor"]))
    lo, hi = p["v_limit_pu"]
    P = loads.to_numpy(dtype=float)                                   # (T, n_bus) kW
    inj = (feeder["battery_kw"] + feeder["community_pv_kw"]).to_numpy(dtype=float)
    on = feeder["energized"].to_numpy() == 1
    T = len(P)
    vbus = np.full((T, n_bus), np.nan)
    out = {k: np.full(T, np.nan) for k in (
        "v_min_pu", "v_max_pu", "v_min_bus", "n_bus_under", "n_bus_over", "load_kw", "line_loss_kw",
        "dt_cu_loss_kw", "dt_nl_loss_kw", "p_dt_kw", "K", "iters")}
    for t in range(T):
        if not on[t]:
            for k in ("n_bus_under", "n_bus_over", "load_kw", "line_loss_kw", "dt_cu_loss_kw",
                      "dt_nl_loss_kw", "p_dt_kw", "K"):
                out[k][t] = 0.0
            continue
        s = np.zeros(n_bus + 1, dtype=complex)
        s[1:] = (P[t] + 1j * tanphi * np.maximum(P[t], 0)) / base
        for b in storage_buses:
            s[b] -= inj[t] / len(storage_buses) / base
        v, i_br, it = bfs(net, s, p["solver"]["tol_pu"], p["solver"]["max_iter"])
        vm = np.abs(v[1:])
        vbus[t] = vm
        out["v_min_pu"][t], out["v_max_pu"][t] = vm.min(), vm.max()
        out["v_min_bus"][t] = int(np.argmin(vm)) + 1
        out["n_bus_under"][t], out["n_bus_over"][t] = (vm < lo).sum(), (vm > hi).sum()
        out["load_kw"][t] = P[t].sum()
        out["line_loss_kw"][t] = float(np.sum(np.abs(i_br[1:]) ** 2 * net["z"][1:].real)) * base
        out["dt_cu_loss_kw"][t] = float(abs(i_br[0]) ** 2 * net["z"][0].real) * base
        out["dt_nl_loss_kw"][t] = p["transformer"]["no_load_loss_w"] / 1000
        s_src = net["v_src"] * np.conj(i_br[0])
        out["p_dt_kw"][t] = s_src.real * base + out["dt_nl_loss_kw"][t]
        out["K"][t] = abs(s_src) * base / p["transformer"]["rating_kva"]
        out["iters"][t] = it
    out["energized"] = on.astype(float)
    cols = ["v_min_pu", "v_max_pu", "v_min_bus", "n_bus_under", "n_bus_over", "load_kw", "line_loss_kw",
            "dt_cu_loss_kw", "dt_nl_loss_kw", "p_dt_kw", "K", "iters", "energized"]
    df = pd.DataFrame({k: out[k] for k in cols}, index=loads.index)
    th_o, th_h, age = dt_thermal(df["K"].to_numpy(), feeder["ambient_c"].to_numpy(dtype=float), on, p)
    df["theta_oil_c"], df["theta_hotspot_c"], df["ageing_rate"] = th_o, th_h, age
    df["python_import_kw"] = feeder["import_kw"].to_numpy(dtype=float)
    for b in range(n_bus):
        df[f"v_bus_{b + 1:02d}"] = vbus[:, b]
    return df


def summarise(df: pd.DataFrame) -> dict:
    h = 0.25
    on = df["energized"] == 1
    loss_line = float(df["line_loss_kw"].sum() * h)
    loss_dt = float((df["dt_cu_loss_kw"] + df["dt_nl_loss_kw"]).sum() * h)
    e_in = float(df.loc[on, "p_dt_kw"].clip(lower=0).sum() * h)
    viol = float((df["n_bus_under"] + df["n_bus_over"]).sum() * h)
    ev = df.index.indexer_between_time("17:30", "19:15")
    return {
        "energized_hours": float(on.sum() * h),
        "energy_from_transformer_kwh": round(e_in, 2),
        "line_loss_kwh": round(loss_line, 2),
        "transformer_loss_kwh": round(loss_dt, 2),
        "technical_loss_kwh": round(loss_line + loss_dt, 2),
        "technical_loss_pct": round(100 * (loss_line + loss_dt) / e_in, 3) if e_in > 0 else None,
        "voltage_violation_bus_hours": round(viol, 2),
        "steps_with_violation_pct": round(100 * float(((df["n_bus_under"] + df["n_bus_over"]) > 0)[on].mean()), 2),
        "min_voltage_pu": round(float(df["v_min_pu"].min()), 4),
        "evening_min_voltage_pu_mean": round(float(df["v_min_pu"].iloc[ev].mean()), 4),
        "peak_transformer_loading_pu": round(float(df["K"].max()), 4),
        "max_hotspot_c": round(float(df["theta_hotspot_c"].max()), 2),
        "ageing_equivalent_hours": round(float((df["ageing_rate"] * h).sum()), 3),
        "elapsed_hours": float(len(df) * h),
    }


def run_study(in_dir: str | Path = "outputs/matlab", out_dir: str | Path = "outputs/lv",
              params_path: str | Path = PARAMS) -> dict:
    p = load_params(params_path)
    ind, out = Path(in_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for week in WEEKS:
        for name, sc in p["scenarios"].items():
            loads = pd.read_csv(ind / f"f07_loads_{week}_{sc['variant']}.csv", index_col=0, parse_dates=True)
            feeder = pd.read_csv(ind / f"f07_feeder_{week}_{sc['variant']}.csv", index_col=0, parse_dates=True)
            df = run_case(loads, feeder, p, sc["storage_buses"])
            df.to_csv(out / f"f07_{week}_{name}_steps.csv")
            summary[f"{week}/{name}"] = summarise(df)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if "line_bare_acsr_rabbit" in p:          # sensitivity: the earlier bare-conductor layout
        pb = {**p, "line": p["line_bare_acsr_rabbit"]}
        sens = {}
        for week in WEEKS:
            for name, sc in p["scenarios"].items():
                loads = pd.read_csv(ind / f"f07_loads_{week}_{sc['variant']}.csv", index_col=0, parse_dates=True)
                feeder = pd.read_csv(ind / f"f07_feeder_{week}_{sc['variant']}.csv", index_col=0, parse_dates=True)
                sens[f"{week}/{name}"] = summarise(run_case(loads, feeder, pb, sc["storage_buses"]))
        (out / "sensitivity_bare_rabbit.json").write_text(json.dumps(sens, indent=2), encoding="utf-8")
    return summary
