"""Engineering report: a self-contained, printable HTML document built from
a saved simulation record (and its attached scenario comparison, if any).

Everything in the report comes from the stored record, so the report is
reproducible and traceable: the same record always gives the same report.
Print it to PDF from the browser. All text is HTML-escaped.
"""

from __future__ import annotations

import html
import math

CSS = """
@page { size: A4; margin: 16mm 14mm; }
:root { --ink:#0f172a; --muted:#475569; --line:#cbd5e1; --soft:#f1f5f9; --accent:#0369a1; --warn:#b45309; --bad:#b91c1c; }
* { box-sizing: border-box; }
body { font: 10.5pt/1.45 Inter, "Segoe UI", system-ui, sans-serif; color: var(--ink); background:#fff; margin: 0 auto; max-width: 980px; padding: 24px; }
h1 { font-size: 19pt; margin: 0 0 2px; } h2 { font-size: 13pt; margin: 22px 0 6px; padding-bottom: 3px; border-bottom: 2px solid var(--accent); }
h3 { font-size: 11pt; margin: 12px 0 4px; }
.sub { color: var(--muted); margin: 0 0 10px; }
.banner { border: 1px solid var(--warn); background: #fffbeb; color: #78350f; padding: 8px 12px; border-radius: 6px; margin: 10px 0; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 6px 18px; }
.kv { display:flex; justify-content: space-between; gap: 8px; border-bottom: 1px dotted var(--line); padding: 2px 0; }
.kv span:first-child { color: var(--muted); }
table { border-collapse: collapse; width: 100%; margin: 4px 0 8px; font-size: 9.5pt; }
th, td { border: 1px solid var(--line); padding: 3px 6px; text-align: left; vertical-align: top; }
th { background: var(--soft); font-weight: 600; }
td.n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.tag { display:inline-block; padding: 0 6px; border-radius: 9px; background: var(--soft); font-size: 9pt; }
.bad { color: var(--bad); font-weight: 600; } .warn { color: var(--warn); font-weight: 600; }
ul { margin: 2px 0 6px 18px; padding: 0; } li { margin: 1px 0; }
.foot { color: var(--muted); font-size: 8.5pt; margin-top: 24px; border-top: 1px solid var(--line); padding-top: 6px; }
@media print { body { padding: 0; } h2 { break-after: avoid; } table, .banner { break-inside: avoid; } .noprint { display:none; } }
"""


def e(v) -> str:
    return html.escape("" if v is None else str(v))


def num(v, d: int = 1, unit: str = "") -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float)):
        s = f"{v:,.{d}f}"
        return f"{s} {unit}".strip()
    return e(v)


def kv(rows: list[tuple[str, str]]) -> str:
    return '<div class="grid">' + "".join(f'<div class="kv"><span>{e(k)}</span><span>{v}</span></div>' for k, v in rows) + "</div>"


def table(head: list[str], rows: list[list[str]], numeric: set[int] | None = None) -> str:
    numeric = numeric or set()
    h = "".join(f"<th>{e(x)}</th>" for x in head)
    body = "".join("<tr>" + "".join(f'<td class="n">{c}</td>' if i in numeric else f"<td>{c}</td>" for i, c in enumerate(r)) + "</tr>"
                   for r in rows)
    return f"<table><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table>"


def bullets(items) -> str:
    items = [x for x in (items or []) if x]
    return "<ul>" + "".join(f"<li>{e(x)}</li>" for x in items) + "</ul>" if items else '<p class="sub">None.</p>'


_SUFFIX = (("_sm3_sm3", "Sm³/Sm³"), ("_kg_m3", "kg/m³"), ("_wt_pct", "wt %"), ("_j_kgk", "J/kg·K"), ("_pa", "bara"), ("_k", "°C"),
           ("_pas", "Pa·s"), ("_bara", "bara"), ("_c", "°C"))
_LABEL = {"oil_api": "Oil gravity (°API)", "gas_specific_gravity": "Gas specific gravity (air = 1)", "water_cut": "Water cut",
          "name": "Fluid"}


def _param(k: str, v) -> tuple[str, str]:
    """Readable label and value with units for a parameter key such as 'bubble_point_reservoir_pa'."""
    if k in _LABEL:
        lbl = _LABEL[k]
        if k == "water_cut" and isinstance(v, (int, float)):
            return lbl, num(v * 100, 1, "%")
        return lbl, num(v, 3) if isinstance(v, (int, float)) else e(v)
    for suf, unit in _SUFFIX:
        if k.endswith(suf) and isinstance(v, (int, float)):
            base = k[: -len(suf)].replace("_", " ").capitalize()
            if suf == "_pa":
                return base, num(v / 1e5, 1, unit)
            if suf == "_k":
                return base, num(v - 273.15, 1, unit)
            return base, num(v, 3, unit)
    return k.replace("_", " ").capitalize(), num(v, 3) if isinstance(v, (int, float)) else e(v)


def _value(inst: dict) -> str:
    v, u = inst.get("value_si"), inst.get("unit_si") or ""
    if v is None:
        return "—"
    if u.startswith("Pa"):
        return num(v / 1e5, 2, "bara" if "(a)" in u else "bar")
    if u == "K":
        return num(v - 273.15, 1, "°C")
    if u == "m3/s":
        return num(v * 86400, 1, "m³/d")
    return num(v, 3, u)


def render(rec: dict) -> str:
    h, inp, res, val = rec["header"], rec["inputs"], rec["results"], rec["validation"]
    sc_in = inp.get("sand_choke") or {}
    parts: list[str] = []
    a = parts.append
    a(f"<h1>Engineering report: {e(rec['label'])}</h1>")
    a(f'<p class="sub">{e(h["scenario_name"])} · simulated time {num(h["sim_time_s"] / 3600, 2, "h")} · saved {e(rec["created_at"])} UTC · '
      f'record {e(rec["id"])} · SubseaSim {e(h["app_version"])} (record schema {e(rec.get("schema_version"))})</p>')
    a(f'<div class="banner"><b>Validation status: {e(val["overall"])}.</b> {e(val["statement"])} Data classification: '
      f'{e(val.get("data_classification"))}. Model status range: {e(val.get("model_status_range"))}.</div>')
    if rec.get("notes"):
        a(f"<p><b>Notes:</b> {e(rec['notes'])}</p>")

    # 1 configuration
    b = inp.get("boundary") or {}
    a("<h2>1. Simulation configuration</h2>")
    a(kv([("Model", e(h.get("mode"))), ("Fluid model", e(h.get("fluid_model"))), ("Run status", e(h.get("status"))),
          ("Reservoir pressure", num((b.get("reservoir_pressure_pa") or 0) / 1e5, 1, "bara")),
          ("Reservoir temperature", num((b.get("reservoir_temperature_k") or 273.15) - 273.15, 1, "°C")),
          ("Productivity index", num((b.get("productivity_index_si") or 0) * 86400 * 1e5, 2, "m³/d/bar")),
          ("Downstream (manifold) pressure", num((b.get("downstream_pressure_pa") or 0) / 1e5, 1, "bara"))]))

    # 2 fluid
    bo = inp.get("black_oil")
    a("<h2>2. Reservoir fluid properties</h2>")
    if bo:
        a(kv([_param(k, v) for k, v in bo.items() if not isinstance(v, (dict, list))]))
    else:
        a(kv([_param(k, v) for k, v in (inp.get("single_phase_fluid") or {}).items()]))

    # 3 production
    ra, rr = res.get("rates_arrival") or {}, res.get("rates_reservoir") or {}
    a("<h2>3. Production conditions</h2>")
    a(table(["Location", "Oil Sm³/d", "Gas Sm³/d", "Water Sm³/d", "GOR Sm³/Sm³", "Water cut"],
            [[lbl, num(r.get("oil_sm3_d"), 1), num(r.get("gas_sm3_d"), 0), num(r.get("water_sm3_d"), 1), num(r.get("gor_sm3_sm3"), 1),
              num((r.get("water_cut") or 0) * 100, 1, "%")] for lbl, r in (("Sandface (entering the well)", rr), ("Manifold (arrival)", ra)) if r],
            {1, 2, 3, 4, 5}))

    # 4 valves
    a("<h2>4. Valve and choke states</h2>")
    a(table(["Tag", "Type", "Position %", "Commanded %", "State"],
            [[e(v["tag"]), e(v["kind"]), num(v.get("position_pct"), 1), num(v.get("commanded_pct"), 1), e(v.get("state"))] for v in inp.get("valves") or []],
            {2, 3}))

    # 5 measurements
    a("<h2>5. Pressure, temperature and flow readings (simulated transmitters)</h2>")
    a(table(["Tag", "Description", "Value", "Status"],
            [[e(i["tag"]), e(i["description"]), _value(i), e(i["status"])] for i in res.get("instruments") or [] if i["type"] in ("pressure", "temperature", "flow", "differential_pressure")],
            {2}))

    # 6 MPFM
    m = res.get("mpfm")
    if m:
        a("<h2>6. Multiphase flow meter</h2>")
        me, tr, un = m.get("measured") or {}, m.get("true") or {}, m.get("uncertainty_pct") or {}
        a(f'<p>{e(m.get("tag"))} · quality <b>{e(m.get("quality"))}</b>{" · flags: " + e(", ".join(m.get("flags") or [])) if m.get("flags") else ""}</p>')
        a(table(["Quantity", "MPFM indicated", "Simulated true", "Uncertainty (k=2)"],
                [[k.replace("_", " "), num(me.get(k), 1), num(tr.get(k), 1), num(un.get(k), 1, "%") if un.get(k) is not None else "—"]
                 for k in ("oil_sm3_d", "gas_sm3_d", "water_sm3_d", "liquid_sm3_d") if k in me or k in tr], {1, 2, 3}))

    # 7 sand
    sand = res.get("sand")
    if sand:
        on = sand.get("onset") or {}
        si = sc_in.get("sand") or {}
        a("<h2>7. Sand production</h2>")
        a(kv([("Mode", e(sand.get("mode"))), ("Drawdown", num(on.get("drawdown_bar"), 1, "bar")),
              ("Critical drawdown", num(on.get("critical_drawdown_bar"), 1, "bar")), ("Sanding risk index", num(on.get("risk_index"), 2)),
              ("Formation sand", num(sand.get("formation_kg_d"), 2, "kg/d")), ("Produced (after screens)", num(sand.get("produced_kg_d"), 2, "kg/d")),
              ("Arriving at the choke", num(sand.get("at_choke_kg_d"), 2, "kg/d")),
              ("PSD D10 / D50 / D90", f'{num(si.get("d10_um"), 0)} / {num(si.get("d50_um"), 0)} / {num(si.get("d90_um"), 0)} µm'),
              ("Grain density", num(si.get("grain_density_kg_m3"), 0, "kg/m³"))]))
        det = res.get("detector")
        if det:
            a(f'<p>Sand detector {e(det.get("tag"))}: {num(det.get("reading_g_s"), 3, "g/s")} (true {num(det.get("true_g_s"), 3, "g/s")}), status '
              f'{e(det.get("status"))}{" — ALARM" if det.get("alarm") else ""}; uncertainty ±{num(det.get("uncertainty_pct"), 0)} % (k=2).</p>')
        mh = res.get("measured_sand_history")
        if mh and mh.get("count"):
            ab = mh.get("abnormal") or {}
            a(f'<p>Measured sand history: {e(mh["count"])} records. {"<span class=bad>" if ab.get("flag") else ""}{e(ab.get("text"))}'
              f'{"</span>" if ab.get("flag") else ""}</p>')

    # 8 erosion
    crit = res.get("wear_criteria") or []
    if crit:
        a("<h2>8. Choke erosion and remaining life</h2>")
        v = res.get("velocities") or {}
        a(kv([("Choke jet velocity", num(v.get("u_jet"), 1, "m/s")), ("Critical flow", num(v.get("critical_flow"), 0)),
              ("Trim service time", num(res.get("service_days"), 1, "days")), ("Governing criterion", e(res.get("governing_criterion"))),
              ("First limit reached", e(res.get("first_limit")))]))
        rows = []
        for c in crit:
            ld = c.get("life_days") or {}
            rows.append([e(c["label"]), num(c.get("used"), 3, c.get("unit") or ""), num(c.get("allowance"), 3, c.get("unit") or ""),
                         num((c.get("consumed") or 0) * 100, 1, "%") if c.get("consumed") is not None else "—",
                         num(c.get("rate_per_year"), 4), f'{num(ld.get("p10"), 0)} / {num(ld.get("p50"), 0)} / {num(ld.get("p90"), 0)}' if ld else "—"])
        a(table(["Criterion", "Used", "Allowance", "Consumed", "Rate per year", "Remaining life P10 / P50 / P90 (days)"], rows, {1, 2, 3, 4, 5}))

    # 9 cavitation and 14E
    cav = res.get("cavitation")
    if cav and cav.get("available"):
        a("<h2>9. Cavitation and flashing screening</h2>")
        w = cav.get("water") or {}
        o = cav.get("oil") or {}
        a(f'<p><b>{e(cav.get("risk"))}</b> · {e(cav.get("status"))} (not CFD).</p>')
        a(kv([("P1 / P2", f'{num(cav.get("p1_bara"), 1)} / {num(cav.get("p2_bara"), 1)} bara'), ("Vena contracta", num(cav.get("vena_contracta_bara"), 1, "bara")),
              ("FL", e(cav.get("fl")) if cav.get("fl") is not None else "not entered"), ("Bubble point", f'{num(o.get("pb_bara"), 1)} bara ({e(o.get("pb_source"))})'),
              ("σ (water)", num(w.get("sigma"), 2)), ("Water vapour pressure", num(w.get("pv_bara"), 3, "bara"))]))
        a(f'<p>Oil: {e(o.get("text"))}</p>' + (f'<p>Water: {e(w.get("text"))}</p>' if w else ""))
        if cav.get("damage_locations"):
            a("<h3>Potential damage locations</h3>" + bullets(cav["damage_locations"]))
        if cav.get("missing"):
            a("<h3>Missing data</h3>" + bullets(cav["missing"]))
    ev = res.get("erosional_velocity")
    if ev and ev.get("available"):
        a("<h3>API RP 14E erosional velocity (supplementary)</h3>")
        a(table(["Location", "Mixture velocity m/s", "Ve m/s", "u / Ve"],
                [[e(r["label"]), num(r.get("u_mix_m_s"), 2), num(r.get("ve_m_s"), 2), num(r.get("ratio"), 2)] if r.get("available")
                 else [e(r["label"]), "—", "—", f"unavailable ({e(r.get('missing'))})"] for r in ev.get("locations") or []], {1, 2, 3}))
        a(bullets(ev.get("notes")))

    # 10 health and recommendation
    hc, reco, conf = res.get("choke_health"), res.get("recommendation"), res.get("confidence")
    if hc:
        a("<h2>10. Component health and maintenance assessment</h2>")
        a(f'<p>Choke health: <b>{e(hc.get("category"))}</b>. {e(hc.get("note"))}</p>')
        if reco:
            a(f'<h3>{e(reco.get("title"))}</h3><p>{e(reco.get("text"))}</p>')
            if reco.get("reasons"):
                a("<h3>Why</h3>" + bullets(reco["reasons"]))
            if reco.get("actions"):
                a("<h3>Recommended actions</h3>" + bullets(reco["actions"]))
        if conf:
            a(f'<p>Confidence: <b>{e(conf.get("category"))}</b></p>' + bullets(conf.get("factors")))

    # 11 operating history
    hist, insp = sc_in.get("history") or [], sc_in.get("inspections") or []
    a("<h2>11. Operating history and inspections</h2>")
    a(f"<p>{len(hist)} operating period(s), {num(sum(p.get('days') or 0 for p in hist), 0)} days in total; {len(insp)} inspection record(s); "
      f"initial service time {num(sc_in.get('initial_service_days'), 0, 'days')}.</p>" if sc_in else "<p>No sand / choke inputs.</p>")

    # 12 comparison
    cmp = rec.get("comparison")
    if cmp:
        a(f'<h2>12. Scenario comparison ({e(len(cmp["cases"]))} cases, {num(cmp["horizon_days"], 0)}-day horizon)</h2>')
        a(f"<p class=sub>{e(cmp.get('method'))}</p>")
        rows_def = [("Changes", lambda c, n, f: e("; ".join(c["changes"]) or "—")), ("Wear starts from", lambda c, n, f: e(c["wear_start"])),
                    ("Choke opening %", lambda c, n, f: num(n.get("choke_pct"), 1)), ("Oil Sm³/d", lambda c, n, f: num(n.get("oil_sm3_d"), 0)),
                    ("Gas Sm³/d", lambda c, n, f: num(n.get("gas_sm3_d"), 0)), ("Water Sm³/d", lambda c, n, f: num(n.get("water_sm3_d"), 0)),
                    ("Choke ΔP bar", lambda c, n, f: num(n.get("choke_dp_bar"), 1)), ("Drawdown bar", lambda c, n, f: num(n.get("drawdown_bar"), 1)),
                    ("Sanding risk index", lambda c, n, f: num(n.get("risk_index"), 2)), ("Sand at choke kg/d", lambda c, n, f: num(n.get("sand_at_choke_kg_d"), 2)),
                    ("Jet velocity m/s", lambda c, n, f: num(n.get("jet_velocity_m_s"), 1)), ("Hole wear mm/yr", lambda c, n, f: num(n.get("hole_rate_mm_y"), 3)),
                    ("Cavitation", lambda c, n, f: e(n.get("cavitation_risk"))),
                    (f"Health after horizon", lambda c, n, f: e(f.get("health"))),
                    ("Remaining life P50 after horizon (d)", lambda c, n, f: num(f.get("life_p50_days"), 0)),
                    ("First limit", lambda c, n, f: e(f.get("first_limit")))]
        head = ["Quantity"] + [c["label"] for c in cmp["cases"]]
        body = [[e(lbl)] + [fn(c, c["now"], c["after_horizon"]) for c in cmp["cases"]] for lbl, fn in rows_def]
        a(table(head, body, set(range(1, len(head)))))
        a("<h3>Comparison limitations</h3>" + bullets(cmp.get("limitations")))

    # 13 provenance, methods, assumptions, uncertainty
    a("<h2>13. Data provenance</h2>")
    a(table(["Item", "Provenance"], [[e(k.replace("_", " ")), e(v)] for k, v in (rec.get("provenance") or {}).items()]))
    a("<h2>14. Methods and model versions</h2>")
    a(table(["Module", "Version", "Status", "Method", "Validation"],
            [[e(k.replace("_", " ")), e(m["version"]), e(m["status"]), e(m["method"]), e(m["validation"])] for k, m in (rec.get("methods") or {}).items()]))
    u = rec.get("uncertainty") or {}
    a("<h2>15. Uncertainty</h2>")
    a(kv([("MPFM (k=2)", e(", ".join(f"{k} ±{v:.1f} %" for k, v in (u.get("mpfm_uncertainty_pct") or {}).items() if isinstance(v, (int, float))) or "—")),
          ("Erosion components (σ ln)", e(", ".join(f"{k} {v:.2f}" for k, v in (u.get("erosion_uncertainty_components_sigma_ln") or {}).items()) or "—")),
          ("Detector (k=2)", num(u.get("detector_uncertainty_pct"), 0, "%"))]))
    a("<h2>16. Model assumptions and limitations</h2>" + bullets(rec.get("assumptions")))
    a(f'<p class="foot">Generated by SubseaSim from record {e(rec["id"])}. Training and decision-support simulator: not connected to, and not a '
      f"substitute for, the control system or engineering verification of the actual equipment.</p>")
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{e(rec['label'])} - SubseaSim report</title><style>{CSS}</style></head><body>{''.join(parts)}</body></html>")
