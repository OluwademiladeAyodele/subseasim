"""Snapshot section for the three-phase (black-oil) model.

Everything here is derived from the same simulation state the network and
transport model use - no independent values."""

from __future__ import annotations

import numpy as np

from app.simulation.fluid_properties.black_oil import P_SC, T_SC

S_PER_DAY = 86_400.0


def std_rates(fluid, w: float, gor: float, wc: float) -> dict:
    """Standard-condition phase rates for a production mass flow [kg/s]."""
    q_liq = w / float(fluid.mass_per_liquid_sc(gor, wc))
    oil = (1.0 - wc) * q_liq
    water = wc * q_liq
    gas = gor * oil
    xo, xg, xw = fluid.component_mass_fractions(gor, wc)
    return {
        "oil_sm3_d": oil * S_PER_DAY, "gas_sm3_d": gas * S_PER_DAY, "water_sm3_d": water * S_PER_DAY,
        "liquid_sm3_d": q_liq * S_PER_DAY, "gor_sm3_sm3": gor, "water_cut": wc,
        "mass_kg_s": w, "oil_mass_kg_s": w * xo, "gas_mass_kg_s": w * xg, "water_mass_kg_s": w * xw,
    }


def build_report(engine) -> dict:
    bo, rr = engine.bo, engine.rho_ref
    topo = engine.topology
    nodes = topo.node_order
    temps = engine._node_temperatures()
    dyn = engine.dyn
    gor0, wc0 = engine.mp_gor, engine.mp_wc
    if dyn is not None:
        mp, net = dyn.mp, dyn.net
        gor_n, wc_n = mp.node_composition()
        comp = {}
        flows = {}
        for nid in nodes:
            hid = dyn.layout.node_index[nid]
            k = mp.pos.get(hid)
            comp[nid] = (float(gor_n[k]), float(wc_n[k])) if k is not None else (gor0, wc0)
            li = dyn.prod_out_link.get(nid)
            flows[nid] = rr * float(net.Q[li]) if li is not None else 0.0
        pres = {nid: dyn.node_pressure(nid) for nid in nodes}
        w_in = rr * float(net.Q[dyn.layout.element_link[topo.path[0].id]])
        w_out = flows[nodes[-2]]
        pipes = mp.pipe_report()
        balance = mp.mass_balance()
        arrival_comp = comp[nodes[-1]]
    else:
        h = engine.hyd
        q = h.q if h.ok else 0.0
        comp = {nid: (gor0, wc0) for nid in nodes}
        flows = {nid: rr * q for nid in nodes}
        pres = {nid: (h.node_pressure.get(nid) if h.ok else None) for nid in nodes}
        w_in = w_out = rr * q
        r = engine.mp_steady
        pipes = [] if r is None else [{
            "element": p.element, "node": p.node, "distance_m": p.distance_m, "pattern": p.pattern, "holdup": p.holdup,
            "lambda_l": p.lambda_l, "v_sl": p.v_sl, "v_sg": p.v_sg, "rho_s": p.rho_s, "rho_ns": p.rho_ns, "p_pa": p.p, "t_k": p.t,
        } for p in r.profile]
        balance = None
        arrival_comp = (gor0, wc0)
    node_rows = []
    ps = [p for p in pres.values() if p]
    for nid in nodes:
        p = pres[nid]
        if not p:
            continue
        g_, w_ = comp[nid]
        s = bo.state(p, temps[nid], g_, w_)
        w = max(flows[nid], 0.0)
        q_liq = w / float(bo.mass_per_liquid_sc(g_, w_))
        node_rows.append({
            "node": nid, "name": topo.nodes[nid].name, "p_pa": p, "t_k": float(temps[nid]), "gor_sm3_sm3": g_, "water_cut": w_,
            "rs_sm3_sm3": float(s.rs[0]), "bubble_point_pa": float(s.pb[0]), "bo": float(s.bo[0]), "bg": float(s.bg[0]),
            "bw": float(s.bw[0]), "z": float(s.z[0]), "rho_oil": float(s.rho_o[0]), "rho_gas": float(s.rho_g[0]),
            "rho_water": float(s.rho_w[0]), "mu_oil_pas": float(s.mu_o[0]), "mu_gas_pas": float(s.mu_g[0]),
            "mu_water_pas": float(s.mu_w[0]), "gvf": float(s.gvf[0]), "rho_mix_ns": float(s.rho_ns[0]),
            "free_gas_mass_fraction": float(s.free_gas_mass_fraction[0]),
            "q_oil_m3s": q_liq * float(s.vol_o[0]), "q_gas_m3s": q_liq * float(s.vol_g[0]), "q_water_m3s": q_liq * float(s.vol_w[0]),
            "mass_flow_kg_s": flows[nid],
        })
    t_all = list(temps.values())
    return {
        "fluid_model": "black_oil",
        "correlation": engine.mp_correlation,
        "dynamic_formulation": "homogeneous-equivalent mass-based network with quasi-steady Beggs & Brill holdup and friction, "
                               "Sachdeva choke flow, transported component composition" if dyn is not None else
                               "steady marching solution (Beggs & Brill / no-slip, Sachdeva choke, Vogel below the bubble point)",
        "standard_conditions": {"p_pa": P_SC, "t_k": T_SC, "note": "Standard volumes at 15 degC and 1.01325 bar (ISO 13443)."},
        "reference_density_kg_m3": rr,
        "params": {
            "name": bo.params.name, "oil_api": bo.params.api, "gas_specific_gravity": bo.params.gas_sg,
            "producing_gor_sm3_sm3": gor0, "water_cut": wc0, "water_salinity_wt_pct": bo.params.water_salinity_wt_pct,
            "oil_density_sc_kg_m3": bo.params.rho_oil_sc, "gas_density_sc_kg_m3": bo.params.rho_gas_sc,
            "water_density_sc_kg_m3": bo.params.rho_water_sc,
            "bubble_point_reservoir_pa": float(bo.state(engine.ipr.p_res, engine.ipr.t_res, gor0, wc0).pb[0]),
        },
        "rates_reservoir": std_rates(bo, w_in, gor0, wc0),
        "rates_arrival": std_rates(bo, w_out, *arrival_comp),
        "nodes": node_rows,
        "pipes": pipes,
        "mass_balance": balance,
        "validity": bo.validity(min(ps) if ps else 1e5, max(ps) if ps else 1e7, min(t_all), max(t_all)),
        "steady_reference": None if engine.mp_steady is None else {
            "ok": engine.mp_steady.ok, "message": engine.mp_steady.message, "critical_choke": engine.mp_steady.critical_choke,
            "rates": std_rates(bo, engine.mp_steady.w, gor0, wc0) if engine.mp_steady.ok else None,
        },
        "limitations": [
            "Generic black-oil correlations - not fitted to a laboratory PVT report.",
            "Phase behaviour and holdup are quasi-steady: slugging, terrain slugging and phase-slip transients are NOT simulated.",
            "Gas solubility in water and oil-water emulsion viscosity are neglected.",
            "The dynamic radial reservoir model is single-phase: inflow below the bubble point is flagged.",
        ],
    }


__all__ = ["build_report", "std_rates", "np"]
