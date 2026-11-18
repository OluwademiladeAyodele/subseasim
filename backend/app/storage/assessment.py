"""Build a simulation record from the live engine state.

The record separates INPUTS (what was configured or measured), RESULTS (what
the models calculated), PROVENANCE (how each input group / result was
obtained: measured, imported, estimated, simulated, configured,
illustrative), METHODS (model registry), ASSUMPTIONS, UNCERTAINTY and
VALIDATION status. Everything is taken from the engine snapshot, so a record
shows exactly what the workstation showed.
"""

from __future__ import annotations

from app.core.model_registry import APP_VERSION, STATUS_LADDER, models
from app.storage.records import SCHEMA_VERSION


def _sand_provenance(engine, snap: dict) -> dict:
    sc = snap.get("sand_choke") or {}
    si = snap.get("sand_choke_inputs") or {}
    origin = getattr(engine, "sand_inputs_origin", "scenario preset")
    sand = si.get("sand") or {}
    mh = sc.get("measured_history") or {}
    inputs_class = {"illustrative example": "illustrative (not field data)",
                    "edited illustrative example": "illustrative, partly edited (verify every value)",
                    "user-entered": "configured (entered site data)"}.get(origin, "configured (scenario preset)")
    if sand.get("mode") == "measured":
        if mh.get("drives_model"):
            recs = sand.get("measurements") or []
            imported = any(r.get("source") == "csv_import" for r in recs)
            rate = "measured (imported CSV history, latest record)" if imported else "measured (entered history, latest record)"
        else:
            rate = "measured (entered value)" if sand.get("measured_value") is not None else "unavailable (no measured value)"
    else:
        rate = "estimated (sanding model prediction)"
    erosion = "estimated (erosion model)"
    n_cal = sum(1 for c in (sc.get("calibration") or {}).get("points") or [] if c.get("used"))
    if n_cal:
        erosion += f", calibrated with {n_cal} inspection record(s)"
    return {"sand_and_choke_inputs": inputs_class, "sand_inputs_origin": origin, "sand_rate": rate,
            "sand_measurement_history": "imported / entered measurements" if mh.get("count") else "none",
            "choke_wear": erosion, "cavitation": "estimated (screening correlation)",
            "erosional_velocity": "estimated (screening correlation)"}


def build_record(engine, session_id: str | None = None) -> dict:
    snap = engine.snapshot(False)
    si = engine.sand_inputs
    snap["sand_choke_inputs"] = si.model_dump(mode="json") if si is not None else None
    sc = snap.get("sand_choke") or {}
    mp = snap.get("multiphase") or {}
    m = snap.get("mpfm") or {}
    three_phase = snap.get("fluid_model") == "black_oil"

    valves = [{"tag": e["tag"], "kind": e["kind"], "position_pct": e.get("position_pct"), "commanded_pct": e.get("commanded_pct"),
               "state": e.get("state"), "available": e.get("available")}
              for e in snap["elements"] if e.get("tag") and e.get("kind") in ("valve", "choke")]
    chems = [{"id": c.get("id"), "name": c.get("name"), "status": c.get("status"),
              "injection_m3s": c.get("total_injection_m3s", c.get("injection_flow_m3s"))} for c in snap.get("chemicals") or []]
    instruments = [{"tag": i["tag"], "type": i["type"], "description": i["description"], "value_si": i["value_si"],
                    "unit_si": i["unit_si"], "status": i["status"]} for i in snap["instruments"]]

    inputs = {
        "boundary": snap.get("boundary"),
        "fluid_model": snap.get("fluid_model"),
        "black_oil": mp.get("params") if three_phase else None,
        "single_phase_fluid": None if three_phase else snap.get("fluid"),
        "valves": valves,
        "chemicals": chems,
        "control_hydraulics": {"supplies": [{k: s.get(k) for k in ("id", "tag", "available", "pressure_pa")}
                                            for s in (snap.get("control_hydraulics") or {}).get("supplies", [])]},
        "sand_choke": snap.get("sand_choke_inputs"),
    }
    results = {
        "instruments": instruments,
        "rates_arrival": mp.get("rates_arrival"),
        "rates_reservoir": mp.get("rates_reservoir"),
        "mass_balance": mp.get("mass_balance"),
        "mpfm": {k: m.get(k) for k in ("tag", "quality", "flags", "measured", "true", "difference", "uncertainty_pct")} if m else None,
        "sand": sc.get("sand"),
        "detector": sc.get("detector"),
        "measured_sand_history": {k: (sc.get("measured_history") or {}).get(k) for k in ("count", "abnormal", "drives_model", "driving_record")}
        if sc.get("measured_history") else None,
        "velocities": sc.get("velocities"),
        "wear_criteria": [{k: c.get(k) for k in ("key", "label", "unit", "used", "allowance", "consumed", "rate_per_year", "life_days")}
                          for c in sc.get("criteria") or []],
        "governing_criterion": sc.get("governing"),
        "first_limit": sc.get("first_limit"),
        "service_days": sc.get("service_days"),
        "cumulative": sc.get("cumulative"),
        "choke_health": sc.get("health"),
        "recommendation": sc.get("recommendation"),
        "confidence": sc.get("confidence"),
        "cv_tracking": sc.get("cv_tracking"),
        "cavitation": sc.get("cavitation"),
        "erosional_velocity": sc.get("erosional_velocity"),
    }
    provenance = {
        "boundary_conditions": "configured (scenario / operator entry)",
        "fluid_properties": "configured inputs to correlations (estimated properties)" if three_phase else "configured (single-phase fluid)",
        "valve_states": "simulated (operator commands applied by the model)",
        "process_measurements": "simulated (model-calculated transmitter readings)",
        "phase_rates": "simulated",
        "mpfm_reading": "simulated measurement (virtual meter with uncertainty)",
    } | (_sand_provenance(engine, snap) if sc.get("available") else {})

    used = ["dynamic_hydraulics"] if snap.get("mode") == "dynamic" else []
    if three_phase:
        used += ["black_oil_pvt", "multiphase_flow", "mpfm"]
    if sc.get("available"):
        used += ["sanding", "sand_transport", "sand_detector", "choke_erosion", "choke_maintenance", "cavitation", "api14e"]
        if (sc.get("measured_history") or {}).get("count"):
            used.append("measured_sand_history")
    methods = models(*used) if used else {}

    assumptions: list[str] = []
    assumptions += [f"Multiphase: {x}" for x in mp.get("limitations") or []]
    assumptions += [f"Sand / erosion: {x}" for x in sc.get("limitations") or []]
    cav = sc.get("cavitation") or {}
    assumptions += [f"Cavitation: ASSUMED {x}" for x in cav.get("assumed") or []]
    sand = sc.get("sand") or {}
    assumptions += [f"Sanding: ASSUMED {x}" for x in sand.get("assumed") or []]

    uncertainty = {
        "mpfm_uncertainty_pct": m.get("uncertainty_pct") if m else None,
        "erosion_uncertainty_components_sigma_ln": sc.get("uncertainty_components"),
        "remaining_life_days": {c["key"]: c.get("life_days") for c in sc.get("criteria") or [] if c.get("life_days")},
        "detector_uncertainty_pct": (sc.get("detector") or {}).get("uncertainty_pct"),
        "cavitation_bubble_point_band": cav.get("sensitivity"),
    }
    conf = (sc.get("confidence") or {}).get("category")
    statuses = [methods[k]["status"] for k in methods]
    highest = max(statuses, key=STATUS_LADDER.index) if statuses else None
    lowest = min(statuses, key=STATUS_LADDER.index) if statuses else None
    overall = "Verified models, not field-validated"
    if conf and conf.startswith("calibrated"):
        overall = "Field-calibrated erosion (inspection records); other models verified, not field-validated"
    validation = {
        "overall": overall,
        "model_status_range": None if not statuses else f"{lowest} to {highest}",
        "erosion_confidence": conf,
        "data_classification": snap["scenario"].get("data_classification"),
        "statement": ("Training and decision-support simulator. Results are as good as the entered data; no model is validated "
                      "against field data for this equipment unless stated as calibrated."),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "header": {"scenario_id": snap["scenario"]["id"], "scenario_name": snap["scenario"]["name"],
                   "data_classification": snap["scenario"].get("data_classification"), "session_id": session_id,
                   "sim_time_s": snap["time_s"], "mode": snap["mode"], "fluid_model": snap.get("fluid_model"),
                   "status": snap["status"], "app_version": APP_VERSION},
        "inputs": inputs, "results": results, "provenance": provenance, "methods": methods,
        "assumptions": assumptions, "uncertainty": uncertainty, "validation": validation,
    }
