"""AC power flow of the city network (pandapower) for each dispatch step.

Topology
  National grid (slack, via the tie) -> 220 kV ring R1-R2-R3 -> 220/33 kV substation per
  region (class loads at 33 kV) -> R3 33/11 kV substation -> the pilot 11 kV feeder
  (5 sections; battery + community PV at node 3, health centre and school at the tail).
The market used ATC limits; this module checks the physical AC result (line loading,
voltages, losses), which is what a control-room security assessment does."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pandapower as pp

from .config import CLASSES, Scenario

PF = {"domestic": 0.95, "commercial": 0.92, "industrial": 0.88, "irrigation": 0.82,
      "traction": 0.92, "municipal": 0.90}
FEEDER_SECTIONS = 5
# share of the pilot feeder's non-critical load at each 11 kV node
NODE_SHARE = np.array([0.15, 0.25, 0.25, 0.20, 0.15])


def build_network(sc: Scenario) -> tuple[pp.pandapowerNet, dict]:
    net = pp.create_empty_network(name="Setu Nagar")
    ids: dict = {"hv": {}, "mv": {}, "loads": {}, "gens": {}, "lines": {}}
    for r in sc.regions:
        ids["hv"][r] = pp.create_bus(net, 220, name=f"{r} 220kV")
        ids["mv"][r] = pp.create_bus(net, 33, name=f"{r} 33kV")
        peak = sum(sc.regions[r]["peak_mw"].values())
        pp.create_transformer_from_parameters(
            net, ids["hv"][r], ids["mv"][r], sn_mva=max(60, 1.3 * peak), vn_hv_kv=220, vn_lv_kv=33,
            vkr_percent=0.4, vk_percent=12, pfe_kw=30, i0_percent=0.05, tap_side="hv",
            tap_neutral=0, tap_min=-9, tap_max=9, tap_step_percent=1.25, tap_pos=-2,
            name=f"{r} 220/33")
        for c in CLASSES:
            ids["loads"][(r, c)] = pp.create_load(net, ids["mv"][r], 0.0, 0.0, name=f"{r} {c}")
    nat = pp.create_bus(net, 220, name="National tie 220kV")
    pp.create_ext_grid(net, nat, vm_pu=1.0, name="National grid")
    # tie to the national grid enters at R1
    ids["lines"]["NAT-R1"] = pp.create_line_from_parameters(
        net, nat, ids["hv"]["R1"], 40, 0.05, 0.40, 9.0, max_i_ka=0.40, name="NAT-R1")
    for tie in sc.raw["interties"]:
        # thermal rating = ATC plus a 25 % N-1 security margin
        i_ka = 1.25 * tie["mw"] / (np.sqrt(3) * 220 * 0.95)
        ids["lines"][f"{tie['from']}-{tie['to']}"] = pp.create_line_from_parameters(
            net, ids["hv"][tie["from"]], ids["hv"][tie["to"]], tie.get("km", 40), 0.05, 0.40, 9.0,
            max_i_ka=i_ka, name=f"{tie['from']}-{tie['to']}")
    ids["pv_gens"] = {}
    for gid, g in sc.generators.items():
        if g["kind"] == "import":
            continue
        if g["kind"] in ("thermal", "gas", "hydro"):   # synchronous machines regulate voltage
            ids["pv_gens"][gid] = pp.create_gen(net, ids["hv"][g["region"]], 0.0, vm_pu=1.02,
                                                name=gid, max_q_mvar=0.6 * g["pmax_mw"],
                                                min_q_mvar=-0.3 * g["pmax_mw"])
        else:
            ids["gens"][gid] = pp.create_sgen(net, ids["hv"][g["region"]], 0.0, name=gid)
    for r in sc.regions:   # 33 kV capacitor banks (standard DISCOM practice)
        peak = sum(sc.regions[r]["peak_mw"].values())
        pp.create_shunt(net, ids["mv"][r], q_mvar=-0.25 * peak, p_mw=0.0, name=f"{r} cap bank")
    for r, reg in sc.regions.items():
        ids["gens"][f"rooftop_{r}"] = pp.create_sgen(net, ids["mv"][r], 0.0, name=f"rooftop {r}")

    # pilot 11 kV feeder under R3
    b11 = pp.create_bus(net, 11, name="R3 11kV substation")
    pp.create_transformer_from_parameters(
        net, ids["mv"]["R3"], b11, sn_mva=10, vn_hv_kv=33, vn_lv_kv=11, vkr_percent=0.8,
        vk_percent=8, pfe_kw=8, i0_percent=0.1, name="R3 33/11")
    nodes = [b11]
    for k in range(FEEDER_SECTIONS):
        nb = pp.create_bus(net, 11, name=f"F07 node {k + 1}")
        # ACSR "Rabbit"-class overhead conductor, 1.2 km sections
        pp.create_line_from_parameters(net, nodes[-1], nb, 1.2, 0.54, 0.35, 10.0, max_i_ka=0.19,
                                       name=f"F07 section {k + 1}")
        nodes.append(nb)
    ids["feeder_nodes"] = nodes[1:]
    ids["feeder_loads"] = [pp.create_load(net, nb, 0.0, 0.0, name=f"F07 load {k + 1}")
                           for k, nb in enumerate(nodes[1:])]
    ids["critical_load"] = pp.create_load(net, nodes[-1], 0.0, 0.0, name="F07 Tier-1")
    ids["feeder_battery"] = pp.create_sgen(net, nodes[3], 0.0, name="F07 battery")
    ids["feeder_pv"] = pp.create_sgen(net, nodes[3], 0.0, name="F07 community PV")
    ids["feeder_rooftop"] = pp.create_sgen(net, nodes[2], 0.0, name="F07 rooftop PV")
    return net, ids


def run_power_flow(sc: Scenario, inp, rt, feeder_res, every: int = 1) -> pd.DataFrame:
    """Quasi-static AC power flow over the week. Returns a per-step security table."""
    net, ids = build_network(sc)
    ts = feeder_res.ts
    rows = []
    q = lambda p, pf: p * np.tan(np.arccos(pf))
    for t in range(0, sc.n_steps, every):
        for (r, c), li in ids["loads"].items():
            p = max(inp.loads[r][c].values[t] - rt.shed[r][c].values[t], 0.0)
            if r == "R3" and c == "domestic":
                p = max(p - ts["gross"].values[t] / 1000, 0.0)   # pilot modelled explicitly
            net.load.at[li, "p_mw"] = p
            net.load.at[li, "q_mvar"] = q(p, PF[c])
        if "R1" in sc.regions and rt.dr is not None:
            li = ids["loads"][("R1", "industrial")]
            net.load.at[li, "p_mw"] = max(net.load.at[li, "p_mw"] - rt.dr.values[t], 0.0)
        for gid, gi in ids["pv_gens"].items():
            p = rt.gen[gid].values[t]
            net.gen.at[gi, "p_mw"] = p
            net.gen.at[gi, "in_service"] = bool(p > 0.1 or not inp.outage[gid][t])
        for gid, si in ids["gens"].items():
            if gid.startswith("rooftop_"):
                net.sgen.at[si, "p_mw"] = inp.rooftop[gid.split("_")[1]][t]
            else:
                net.sgen.at[si, "p_mw"] = rt.gen[gid].values[t]
        tripped = "trip" in str(ts["state"].values[t])
        served_t1 = (ts["tier1"].values[t] - ts["tier1_unserved"].values[t]) / 1000
        other = max(ts["gross"].values[t] - ts["unserved"].values[t] - ts["tier1"].values[t]
                    + ts["tier1_unserved"].values[t], 0) / 1000
        if tripped:  # feeder breaker open: islanded Tier-1 is not visible to the grid
            other, served_t1 = 0.0, 0.0
        for k, li in enumerate(ids["feeder_loads"]):
            net.load.at[li, "p_mw"] = other * NODE_SHARE[k]
            net.load.at[li, "q_mvar"] = q(other * NODE_SHARE[k], 0.95)
        net.load.at[ids["critical_load"], "p_mw"] = served_t1
        net.load.at[ids["critical_load"], "q_mvar"] = q(served_t1, 0.9)
        on = 0.0 if tripped else 1.0
        net.sgen.at[ids["feeder_battery"], "p_mw"] = on * ts["battery_kw"].values[t] / 1000
        pv_used = ts["solar_used"].values[t] / 1000 * on
        net.sgen.at[ids["feeder_pv"], "p_mw"] = pv_used * 0.4
        net.sgen.at[ids["feeder_rooftop"], "p_mw"] = pv_used * 0.6
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                pp.runpp(net, numba=False, init="results" if t else "auto", max_iteration=20)
            except pp.LoadflowNotConverged:
                pp.runpp(net, numba=False, init="flat", max_iteration=40)
        fv = net.res_bus.loc[ids["feeder_nodes"], "vm_pu"].values
        lines = net.res_line
        rows.append({
            "timestamp": sc.index[t],
            "national_import_mw": float(net.res_ext_grid.p_mw.iloc[0]),
            "losses_mw": float(lines.pl_mw.sum() + net.res_trafo.pl_mw.sum()),
            "max_tie_loading_pct": float(lines.loc[[v for k, v in ids["lines"].items()], "loading_percent"].max()),
            **{f"loading_{k}_pct": float(lines.loading_percent.at[v]) for k, v in ids["lines"].items()},
            **{f"v_{r}_33kV_pu": float(net.res_bus.vm_pu.at[ids["mv"][r]]) for r in sc.regions},
            "feeder_tail_v_pu": float(fv[-1]) if not tripped else np.nan,
            "feeder_min_v_pu": float(fv.min()) if not tripped else np.nan,
            "feeder_head_mw": float(lines.p_from_mw.at[net.line.index[net.line.name == "F07 section 1"][0]]),
        })
    return pd.DataFrame(rows).set_index("timestamp")
