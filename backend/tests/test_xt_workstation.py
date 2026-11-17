"""XT workstation (reference layout 'Production 230XP22B'): schematic layout
integrity, display aliases, calibration to the legible reference readings,
control hydraulics (selector valves / fail-safe) and the additional methanol
injection routes."""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from app.core import units as u
from app.main import app
from app.models.schematic import SchematicLayout
from app.scenarios.loader import get_scenario, get_schematic
from app.simulation.components.elements import CommandRejected
from app.simulation.engine import SimulationEngine

SCN = "xt_230xp22b"


@pytest.fixture(scope="module")
def scenario():
    return get_scenario(SCN)


@pytest.fixture(scope="module")
def layout():
    return SchematicLayout.model_validate(get_schematic(SCN))


def _engine(scenario) -> SimulationEngine:
    return SimulationEngine(scenario.model_copy(deep=True))


def _val(e: SimulationEngine, tag: str) -> float:
    v = e.readings[tag].value
    assert v is not None, tag
    return v


# ------------------------------------------------------------------ layout
def test_every_layout_model_reference_resolves(scenario, layout):
    e = _engine(scenario)
    elements = {x.id for x in e.dyn.elements.values()}  # type: ignore[union-attr]
    instruments = {i.tag for i in e.instruments}
    chems = {c.id for c in scenario.chemicals}
    hyd = scenario.control_hydraulics
    refs = {
        "element": elements, "instrument": instruments, "chemical": chems,
        "selector": {s.tag for s in hyd.selector_valves}, "header": {h.id for h in hyd.headers},
        "supply": {s.id for s in hyd.supplies}, "page": {"diagnostics"},
    }
    for c in layout.components:
        for ref in [c.model, *c.models]:
            if ref is None:
                continue
            kind, _, ident = ref.partition(":")
            assert ident in refs[kind], f"{c.id}: unresolved {ref}"
    for ln in layout.lines:
        for eid in ln.elements:
            assert eid in elements, f"line {ln.id}: unknown element {eid}"
        if ln.chemical:
            assert ln.chemical in chems
    for k in layout.connectors:
        if k.model:
            assert k.model.split(":", 1)[1] in chems


def test_every_valve_and_reference_transmitter_is_on_the_schematic(scenario, layout):
    """Each restriction / check valve of the tree is independently drawn and
    every aliased (reference) transmitter appears in a panel."""
    on_sheet = {r.split(":", 1)[1] for c in layout.components for r in [c.model, *c.models] if r}
    e = _engine(scenario)
    for el in e.dyn.elements.values():  # type: ignore[union-attr]
        if el.kind in ("valve", "choke", "check_valve"):
            assert el.id in on_sheet, f"valve {el.id} missing from the schematic"
    inst_tags = {i.tag for i in e.instruments}
    for eng, a in scenario.tag_aliases.items():
        if eng in inst_tags and a.status != "addition":
            assert eng in on_sheet, f"reference transmitter {a.tag} ({eng}) missing"
    ids = [c.id for c in layout.components]
    assert len(ids) == len(set(ids)), "component ids must be unique"


def test_reference_positions_are_preserved(layout):
    """Relative arrangement of the reference page (photo pixel measurements
    mapped through the documented transform)."""
    ref = layout.reference
    by = {c.id: c for c in layout.components}

    def photo(cid):
        c = by[cid]
        return (c.x / ref.scale + ref.photo_origin_px[0], c.y / ref.scale + ref.photo_origin_px[1])

    expect = {  # photo pixels (keystone-straightened), tolerance 1.5 px
        "PMV": (233, 279), "SCSSV": (233, 326), "AMV": (202, 279), "AWV": (165, 139), "XOV": (171, 196),
        "SLV": (82, 196), "PWV": (441, 145), "CHOKE": (481, 145), "CIV302": (315, 176), "MIV302": (370, 265),
        "MIV303": (370, 290), "CIV304": (130, 356), "SEL-LP-A": (468, 326), "SEL-HP-B": (468, 433),
    }
    for cid, (px, py) in expect.items():
        x, y = photo(cid)
        assert abs(x - px) < 1.5 and abs(y - py) < 1.5, (cid, x, y)
    # broad grouping: annulus left of the bore, chemicals right of it, choke furthest right, selectors bottom right
    assert by["AMV"].x < by["PMV"].x < by["CIV302"].x < by["PWV"].x < by["CHOKE"].x
    assert by["SEL-LP-A"].y > by["PWV"].y and by["SEL-LP-A"].x > by["PMV"].x
    assert by["SLV"].x < by["XOV"].x < by["PMV"].x


def test_lines_are_connected(layout):
    """Every line end lies on another line (tee/junction), a component port,
    a connector or a drawn terminal (tree cap, manifold)."""
    endpoints = []
    segs = []
    for ln in layout.lines:
        endpoints += [(ln.id, ln.points[0]), (ln.id, ln.points[-1])]
        segs += [(ln.id, a, b) for a, b in zip(ln.points, ln.points[1:])]
    terminals = [(k.x, k.y) for k in layout.connectors] + [tuple(c.tap) for c in layout.components if c.tap is not None]
    for a in layout.annotations:
        if a["type"] in ("bar", "manifold"):
            terminals += [(x, y) for x in (a["x"], a["x"] + a["w"]) for y in (a["y"], a["y"] + a["h"])]

    def on_seg(p, a, b, tol=1.0):
        (px, py), (ax, ay), (bx, by) = p, a, b
        L2 = (bx - ax) ** 2 + (by - ay) ** 2
        t = 0 if L2 == 0 else max(0, min(1, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / L2))
        return math.hypot(px - (ax + t * (bx - ax)), py - (ay + t * (by - ay))) <= tol

    def near_terminal(p):
        return any(abs(p[0] - x) < 1 and abs(p[1] - y) < 1 for x, y in terminals) or any(
            a["type"] in ("bar", "manifold") and a["x"] - 1 <= p[0] <= a["x"] + a["w"] + 1 and a["y"] - 1 <= p[1] <= a["y"] + a["h"] + 1
            for a in layout.annotations)

    for lid, p in endpoints:
        others = [s for s in segs if s[0] != lid]
        assert near_terminal(p) or any(on_seg(p, a, b) for _, a, b in others), f"{lid} end {p} is dangling"


def test_components_sit_on_their_flow_path(layout):
    lines = {ln.id: ln for ln in layout.lines}
    for c in layout.components:
        if not c.flow_path or c.type in ("tag_panel", "choke_panel", "sand_detector", "header_panel"):
            continue
        ln = lines[c.flow_path]
        d = min(
            math.hypot(c.x - (a[0] + t * (b[0] - a[0])), c.y - (a[1] + t * (b[1] - a[1])))
            for a, b in zip(ln.points, ln.points[1:])
            for t in [max(0, min(1, ((c.x - a[0]) * (b[0] - a[0]) + (c.y - a[1]) * (b[1] - a[1])) / max(1e-9, (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)))]
        )
        assert d < 1.0, f"{c.id} is {d:.1f} units off its flow path {c.flow_path}"
    for c in layout.components:
        if c.tap is not None and c.flow_path:
            ln = lines[c.flow_path]
            assert any(
                min(a[0], b[0]) - 1 <= c.tap[0] <= max(a[0], b[0]) + 1 and min(a[1], b[1]) - 1 <= c.tap[1] <= max(a[1], b[1]) + 1
                for a, b in zip(ln.points, ln.points[1:])
            ), f"{c.id} tap not on {c.flow_path}"


def test_layout_positions_do_not_affect_measurement_location(scenario, monkeypatch):
    """Moving every component in the layout changes nothing in the model:
    readings depend only on the engineering configuration."""
    import copy

    import app.simulation.engine as engine_mod

    e1 = _engine(scenario)
    e1.start()
    e1.advance(120)
    moved = copy.deepcopy(get_schematic(SCN))
    for c in moved["components"]:
        c["x"] += 123.0
        c["y"] -= 45.0
        if c.get("tap"):
            c["tap"] = [c["tap"][0] + 50, c["tap"][1]]
    monkeypatch.setattr(engine_mod, "get_schematic", lambda _id: moved)
    e2 = _engine(scenario)
    e2.start()
    e2.advance(120)
    assert e2.snapshot()["schematic"]["components"][0]["x"] == moved["components"][0]["x"]
    assert {k: r.value for k, r in e1.readings.items()} == {k: r.value for k, r in e2.readings.items()}


# ------------------------------------------------------------------ aliases
def test_display_aliases_cover_the_confidently_read_reference_tags(scenario):
    shown = {a.tag: a.status for a in scenario.tag_aliases.values()}
    for tag in ["AWV3034", "AMV3030", "PMV3004", "PWV3005", "SCSSV3003", "PCV3006", "XOV3032", "SLV3035",
                "PT3002", "PT3003", "PT3004", "PT3005", "PT3008", "PT3009", "PT3014", "PT3030", "PD3014"]:
        assert shown.get(tag) == "verified", tag
    tags = [a.tag for a in scenario.tag_aliases.values()]
    assert len(tags) == len(set(tags)), "display tags must be unique"
    # aliases refer to real engineering tags
    e = _engine(scenario)
    known = set(e.restrictions) | {i.tag for i in e.instruments} | {s.tag for s in scenario.control_hydraulics.selector_valves} \
        | {h.tag for h in scenario.control_hydraulics.headers} | {s.tag for s in scenario.control_hydraulics.supplies}
    assert set(scenario.tag_aliases) <= known


# ------------------------------------------- readings are the model's own
def test_readings_are_calculated_not_copied_from_the_reference(scenario):
    """The photograph defines the architecture only: transmitter values come
    from the engineering inputs and follow them."""
    e = _engine(scenario)
    p_cav = _val(e, "PT-104")
    # consistent with the steady hydraulic solution of the configured system
    assert p_cav == pytest.approx(e.hyd.node_pressure["N_PMV_PWV"], rel=1e-3)
    # the two transmitters on the same volume agree, the differential equals the pressure difference
    assert _val(e, "PT-107") == pytest.approx(p_cav, abs=0.05e5)
    assert _val(e, "PDT-401") == pytest.approx(_val(e, "PT-404") - _val(e, "PT-403"), abs=0.1e5)
    # a different reservoir input gives different readings
    e2 = _engine(scenario)
    e2.set_boundary(reservoir_pressure_pa=u.bara_to_pa(330))
    e2.recompute()
    assert e2.hyd.node_pressure["N_PMV_PWV"] < p_cav - 2e5


def test_valve_operations_drive_the_transmitters(scenario):
    e = _engine(scenario)
    e.start()
    e.advance(60)
    cav0, dn0 = _val(e, "PT-104"), _val(e, "PT-103")
    e.command_valve("PWV-101", "close")
    e.advance(900)
    cav1, dn1 = _val(e, "PT-104"), _val(e, "PT-103")
    assert cav1 > cav0 + 10e5  # tree cavity builds toward shut-in pressure
    assert dn1 < dn0 - 1e5  # choke outlet falls toward flowline pressure
    # choke throttling changes the operating point
    e.command_valve("PWV-101", "open")
    e.advance(600)
    e.command_valve("CHK-101", "set_position", 80)
    e.advance(900)
    assert _val(e, "PT-104") < cav0  # more open choke -> lower tree pressure, higher rate
    # opening the crossover connects the annulus service-line junction to the tree cavity
    e.command_valve("XOV-101", "open")
    e.command_valve("SLV-101", "close")
    e.advance(300)
    assert _val(e, "PT-404") == pytest.approx(_val(e, "PT-104"), abs=2e5)


# ------------------------------------------------------- control hydraulics
def test_loss_of_lp_supply_closes_fail_safe_valves_and_blocks_opening(scenario):
    e = _engine(scenario)
    e.start()
    chk0 = e.restrictions["CHK-101"].actuator.position_pct
    e.command_valve("AMV-101", "open")
    e.command_valve("CIV-302", "open")
    e.advance(60)
    e.command_selector("SEL-LP-A", "close")
    e.command_selector("SEL-LP-B", "close")
    e.advance(60)
    assert e.restrictions["PMV-101"].actuator.position_pct == 100  # headers still above minimum
    e.advance(1200)
    hyd = e.ctrl
    assert not hyd.supply_ok("LP") and hyd.supply_ok("HP")
    pos = {t: e.restrictions[t].actuator.position_pct for t in ("PMV-101", "PWV-101", "AMV-101", "CHK-101", "SCSSV-101", "CIV-302")}
    assert pos["PMV-101"] == 0 and pos["PWV-101"] == 0 and pos["AMV-101"] == 0 and pos["CIV-302"] == 0
    assert pos["CHK-101"] == pytest.approx(chk0)  # stepping actuator fails as-is
    assert pos["SCSSV-101"] == 100  # on HP, still powered
    assert any(ev.category == "alarm" and "LOSS OF LP" in ev.message for ev in e.events.all())
    with pytest.raises(CommandRejected, match="insufficient LP hydraulic pressure"):
        e.command_valve("PWV-101", "open")
    e.command_valve("PWV-101", "close")  # closing is always possible
    # one selector valve restores the supply (SCM A/B redundancy)
    e.command_selector("SEL-LP-B", "open")
    e.advance(120)
    assert hyd.supply_ok("LP")
    e.command_valve("PMV-101", "open")


def test_single_selector_valve_keeps_the_supply_redundant(scenario):
    e = _engine(scenario)
    e.start()
    e.command_selector("SEL-HP-A", "close")
    e.advance(3600)
    assert e.ctrl.supply_ok("HP")
    assert e.restrictions["SCSSV-101"].actuator.position_pct == 100


def test_hpu_trip_on_hp_closes_scssv(scenario):
    e = _engine(scenario)
    e.start()
    e.set_hydraulic_supply("HP", False)
    e.advance(240)
    assert e.restrictions["SCSSV-101"].actuator.commanded_pct == 0
    e.advance(60)
    assert e.restrictions["SCSSV-101"].actuator.position_pct == 0


# ----------------------------------------------------- methanol routes (MIV)
def test_miv_routes_inject_into_their_own_nodes_and_conserve_volume(scenario):
    e = _engine(scenario)
    e.start()
    e.command_valve("MIV-303", "open")  # between PWV and the choke only
    e.advance(900)
    dyn = e.dyn
    c = next(x for x in dyn.circuits if x.cfg.id == "methanol")
    up, dn = c.routes
    assert dn.status == "injecting" and up.status == "isolated"
    assert dn.cum_m3 > 0.05 and up.cum_m3 < 1e-6
    # volume conservation of the transported chemical: injected = in line + exported (+ to reservoir)
    k = c.k
    injected = float(dyn.grid.injected[k])
    assert injected == pytest.approx(c.cum_injected_m3 + up.cum_m3 + dn.cum_m3, rel=1e-6, abs=1e-9)
    balance = float(dyn.grid.inventory()[k]) + float(dyn.grid.out_boundary[k]) + float(dyn.grid.out_reservoir[k])
    assert balance == pytest.approx(injected, rel=1e-6, abs=1e-9)
    # methanol injected downstream of PWV does not reach the tree cavity (upstream), but is downstream of the choke
    g = dyn.grid
    cav = g.node_value("N_PMV_PWV", g.F, g.dT_throttle, "c", chem=k, injections_at=dyn.injections_at_nodes())
    dc = g.node_value("N_DC", g.F, g.dT_throttle, "c", chem=k, injections_at=dyn.injections_at_nodes())
    assert cav < 1e-9 < dc
    snap = e.snapshot(False)
    meoh = next(x for x in snap["chemicals"] if x["id"] == "methanol")
    assert meoh["total_injection_m3s"] == pytest.approx(sum(max(r["flow_m3s"], 0) for r in meoh["routes"]) + max(meoh["injection_flow_m3s"], 0))
    assert any("through MIV-303 STARTED" in ev.message for ev in e.events.all())


# ---------------------------------------------------------------------- API
def test_api_accepts_display_tags_and_exposes_layout_and_hydraulics():
    with TestClient(app) as client:
        r = client.post("/api/sessions", json={"scenario_id": SCN})
        assert r.status_code == 201
        body = r.json()
        sid, st = body["session_id"], body["state"]
        assert st["schematic"]["id"] == SCN
        assert st["tag_aliases"]["PMV-101"]["tag"] == "PMV3004"
        assert {h["tag"] for h in st["control_hydraulics"]["headers"]} == {"PT-HYD-LPA", "PT-HYD-LPB", "PT-HYD-HPA", "PT-HYD-HPB"}
        r = client.post(f"/api/sessions/{sid}/valves/PWV3005", json={"command": "close"})
        assert r.status_code == 200
        pwv = next(x for x in r.json()["state"]["elements"] if x.get("tag") == "PWV-101")
        assert pwv["commanded_pct"] == 0
        r = client.post(f"/api/sessions/{sid}/hydraulics/selectors/SEL-LP-A", json={"command": "close"})
        assert r.status_code == 200
        sel = next(x for x in r.json()["state"]["control_hydraulics"]["selector_valves"] if x["tag"] == "SEL-LP-A")
        assert sel["commanded_pct"] == 0
        assert client.post(f"/api/sessions/{sid}/hydraulics/selectors/NOPE", json={"command": "close"}).status_code == 404
        assert client.post(f"/api/sessions/{sid}/hydraulics/supplies/LP", json={"available": False}).status_code == 200
        assert client.post(f"/api/sessions/{sid}/hydraulics/supplies/XX", json={"available": False}).status_code == 404
