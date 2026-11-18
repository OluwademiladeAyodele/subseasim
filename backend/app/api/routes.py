"""REST and WebSocket API. Thin layer: validation + delegation to the engine."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.api.schemas import (
    BlackOilUpdate,
    BoundaryUpdate,
    FastForwardRequest,
    FluidModelRequest,
    MPFMFaultRequest,
    CreateSessionRequest,
    FluidUpdate,
    IntegrityTestRequest,
    LifecycleRequest,
    ModeRequest,
    PumpRequest,
    SandCsvRequest,
    SelectorCommandRequest,
    SupplyRequest,
    LoadScenarioRequest,
    SpeedRequest,
    TrainingAnswerRequest,
    TrainingStartRequest,
    ValveCommandRequest,
)
from app.models.sand import SandChokeInputs
from app.scenarios.loader import ScenarioNotFound, get_scenario, list_scenarios
from app.sessions import Session, SessionLimitReached, manager
from app.simulation.components.elements import CommandRejected
from app.simulation.engine import InvalidOperatingInput
from app.training.framework import TrainingError
from app.training.registry import EXERCISES

router = APIRouter(prefix="/api")


def _session(sid: str) -> Session:
    try:
        return manager.get(sid)
    except KeyError:
        raise HTTPException(404, f"session {sid!r} not found") from None


async def _after_change(s: Session) -> dict:
    s.update_training()
    await s.broadcast()
    return s.payload()


@router.get("/health")
async def health() -> dict:
    m = manager.metrics
    return {
        "status": "ok", "simulated": True, "sessions": len(manager.sessions),
        "running": m["running"], "sockets": m["sockets"],
        "tick_ms": round(m["tick_ms"], 1), "tick_ms_max": round(m["tick_ms_max"], 1),
        "loop_period_s": round(m["real_period_s"], 3),
    }


@router.get("/scenarios")
async def scenarios() -> list[dict]:
    return [{"id": s.id, "name": s.name, "description": s.description, "data_classification": s.data_classification} for s in list_scenarios()]


@router.get("/scenarios/{scenario_id}")
async def scenario(scenario_id: str) -> dict:
    try:
        return get_scenario(scenario_id).model_dump(by_alias=True)
    except ScenarioNotFound:
        raise HTTPException(404, f"scenario {scenario_id!r} not found") from None


@router.get("/training/exercises")
async def exercises() -> list[dict]:
    return [e.summary() for e in EXERCISES.values()]


@router.post("/sessions", status_code=201)
async def create_session(req: CreateSessionRequest) -> dict:
    try:
        s = manager.create(req.scenario_id)
    except ScenarioNotFound:
        raise HTTPException(404, f"scenario {req.scenario_id!r} not found") from None
    except SessionLimitReached as exc:
        raise HTTPException(503, str(exc)) from None
    return s.payload()


@router.get("/sessions/{sid}")
async def get_session(sid: str) -> dict:
    return _session(sid).payload()


@router.get("/sessions/{sid}/history")
async def history(sid: str) -> list[dict]:
    return _session(sid).engine.history.all()


@router.get("/sessions/{sid}/events")
async def events(sid: str) -> list[dict]:
    return [e.to_dict() for e in _session(sid).engine.events.all()]


@router.post("/sessions/{sid}/lifecycle")
async def lifecycle(sid: str, req: LifecycleRequest) -> dict:
    s = _session(sid)
    try:
        getattr(s.engine, req.action)()
    except CommandRejected as exc:
        raise HTTPException(409, str(exc)) from None
    if req.action == "reset":
        s.training = None if s.training is None else type(s.training)(s.training.d)
    return await _after_change(s)


@router.post("/sessions/{sid}/speed")
async def speed(sid: str, req: SpeedRequest) -> dict:
    s = _session(sid)
    try:
        s.engine.set_time_scale(req.time_scale)
    except CommandRejected as exc:
        raise HTTPException(422, str(exc)) from None
    return await _after_change(s)


@router.post("/sessions/{sid}/mode")
async def set_mode(sid: str, req: ModeRequest) -> dict:
    s = _session(sid)
    s.engine.set_mode(req.mode)
    s.training = None if s.training is None else type(s.training)(s.training.d)
    return await _reinit(s)


async def _reinit(s: Session) -> dict:
    """The model was rebuilt: push a full re-initialisation to clients."""
    payload = s.payload()
    for ws in list(s.sockets):
        try:
            await ws.send_json(s.init_message())
        except Exception:  # noqa: BLE001
            s.sockets.discard(ws)
    s.sent_event_id = s.engine.events.last_id
    s.sent_sample_seq = s.engine.history.last_seq
    return payload


@router.post("/sessions/{sid}/chemicals/{chem_id}")
async def chemical_pump(sid: str, chem_id: str, req: PumpRequest) -> dict:
    s = _session(sid)
    try:
        s.engine.set_pump(chem_id, running=req.running, discharge_pressure_pa=req.discharge_pressure_pa)
    except CommandRejected as exc:
        raise HTTPException(409, str(exc)) from None
    except InvalidOperatingInput as exc:
        raise HTTPException(422, str(exc)) from None
    return await _after_change(s)


@router.post("/sessions/{sid}/integrity/tests")
async def integrity_start(sid: str, req: IntegrityTestRequest) -> dict:
    s = _session(sid)
    try:
        s.engine.start_integrity_test(**req.model_dump())
    except CommandRejected as exc:
        await s.broadcast()
        raise HTTPException(409, str(exc)) from None
    return await _after_change(s)


@router.post("/sessions/{sid}/integrity/tests/{test_id}/abort")
async def integrity_abort(sid: str, test_id: int) -> dict:
    s = _session(sid)
    try:
        s.engine.abort_integrity_test(test_id)
    except CommandRejected as exc:
        raise HTTPException(409, str(exc)) from None
    return await _after_change(s)


@router.post("/sessions/{sid}/scenario")
async def load_scenario(sid: str, req: LoadScenarioRequest) -> dict:
    s = _session(sid)
    try:
        s.engine.load_scenario(get_scenario(req.scenario_id))
    except ScenarioNotFound:
        raise HTTPException(404, f"scenario {req.scenario_id!r} not found") from None
    s.training = None
    return await _reinit(s)


def _resolve_tag(s: Session, tag: str) -> str:
    """Accept the engineering tag or its display alias (reference HMI tag)."""
    if tag in s.engine.restrictions:
        return tag
    for eng, alias in s.engine.scenario.tag_aliases.items():
        if alias.tag == tag:
            return eng
    return tag


@router.post("/sessions/{sid}/hydraulics/selectors/{tag}")
async def selector_command(sid: str, tag: str, req: SelectorCommandRequest) -> dict:
    s = _session(sid)
    tag = _resolve_tag(s, tag)
    try:
        s.engine.command_selector(tag, req.command)
    except CommandRejected as exc:
        raise HTTPException(404 if "unknown" in str(exc) else 409, str(exc)) from None
    return await _after_change(s)


@router.post("/sessions/{sid}/hydraulics/supplies/{supply_id}")
async def hydraulic_supply(sid: str, supply_id: str, req: SupplyRequest) -> dict:
    s = _session(sid)
    try:
        s.engine.set_hydraulic_supply(supply_id, req.available)
    except CommandRejected as exc:
        raise HTTPException(404, str(exc)) from None
    return await _after_change(s)


@router.post("/sessions/{sid}/valves/{tag}")
async def valve_command(sid: str, tag: str, req: ValveCommandRequest) -> dict:
    s = _session(sid)
    tag = _resolve_tag(s, tag)
    if tag not in s.engine.restrictions:
        raise HTTPException(404, f"valve {tag!r} not found")
    try:
        s.engine.command_valve(tag, req.command, req.position_pct)
    except CommandRejected as exc:
        await s.broadcast()
        raise HTTPException(409, str(exc)) from None
    return await _after_change(s)


@router.put("/sessions/{sid}/boundary")
async def boundary(sid: str, req: BoundaryUpdate) -> dict:
    s = _session(sid)
    try:
        s.engine.set_boundary(**req.model_dump())
    except InvalidOperatingInput as exc:
        raise HTTPException(422, str(exc)) from None
    return await _after_change(s)


@router.put("/sessions/{sid}/fluid")
async def fluid(sid: str, req: FluidUpdate) -> dict:
    s = _session(sid)
    try:
        s.engine.set_fluid(
            density=req.density_kg_m3, viscosity=req.viscosity_pas, specific_heat=req.specific_heat_j_kgk,
            thermal_expansion=req.thermal_expansion_1_k, bubble_point_pressure=req.bubble_point_pressure_pa,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return await _after_change(s)


@router.put("/sessions/{sid}/black-oil")
async def black_oil(sid: str, req: BlackOilUpdate) -> dict:
    s = _session(sid)
    try:
        s.engine.set_black_oil(**req.model_dump())
    except CommandRejected as exc:
        raise HTTPException(409, str(exc)) from None
    except InvalidOperatingInput as exc:
        raise HTTPException(422, str(exc)) from None
    return await _after_change(s)


@router.put("/sessions/{sid}/sand-choke/inputs")
async def sand_inputs(sid: str, req: SandChokeInputs) -> dict:
    s = _session(sid)
    s.engine.set_sand_inputs(req)
    return await _after_change(s)


@router.post("/sessions/{sid}/sand-choke/measurements/csv")
async def sand_measurements_csv(sid: str, req: SandCsvRequest) -> dict:
    from app.simulation.sand.measurements import CsvImportError

    s = _session(sid)
    try:
        n = s.engine.import_sand_measurements(req.csv, req.replace)
    except CsvImportError as exc:
        raise HTTPException(422, {"message": str(exc), "errors": exc.errors}) from None
    except CommandRejected as exc:
        raise HTTPException(409, str(exc)) from None
    out = await _after_change(s)
    out["imported"] = n
    return out


@router.post("/sessions/{sid}/sand-choke/example")
async def sand_example(sid: str) -> dict:
    s = _session(sid)
    try:
        s.engine.load_sand_example()
    except CommandRejected as exc:
        raise HTTPException(409, str(exc)) from None
    return await _after_change(s)


@router.post("/sessions/{sid}/sand-choke/fast-forward")
async def sand_fast_forward(sid: str, req: FastForwardRequest) -> dict:
    s = _session(sid)
    try:
        s.engine.sand_fast_forward(req.days)
    except CommandRejected as exc:
        raise HTTPException(409, str(exc)) from None
    return await _after_change(s)


@router.put("/sessions/{sid}/mpfm/faults")
async def mpfm_faults(sid: str, req: MPFMFaultRequest) -> dict:
    s = _session(sid)
    try:
        s.engine.set_mpfm_faults(**req.model_dump())
    except CommandRejected as exc:
        raise HTTPException(409, str(exc)) from None
    return await _after_change(s)


@router.post("/sessions/{sid}/mpfm/calibrate")
async def mpfm_calibrate(sid: str) -> dict:
    s = _session(sid)
    try:
        s.engine.calibrate_mpfm()
    except CommandRejected as exc:
        raise HTTPException(409, str(exc)) from None
    return await _after_change(s)


@router.post("/sessions/{sid}/fluid-model")
async def fluid_model(sid: str, req: FluidModelRequest) -> dict:
    s = _session(sid)
    try:
        s.engine.set_fluid_model(req.model)
    except CommandRejected as exc:
        raise HTTPException(409, str(exc)) from None
    s.training = None if s.training is None else type(s.training)(s.training.d)
    return await _reinit(s)


@router.post("/sessions/{sid}/training/start")
async def training_start(sid: str, req: TrainingStartRequest) -> dict:
    s = _session(sid)
    try:
        s.start_training(req.exercise_id)
    except KeyError:
        raise HTTPException(404, f"exercise {req.exercise_id!r} not found") from None
    payload = s.payload()
    # A new scenario was loaded: push a full re-initialisation to clients.
    for ws in list(s.sockets):
        try:
            await ws.send_json(s.init_message())
        except Exception:  # noqa: BLE001
            s.sockets.discard(ws)
    s.sent_event_id = s.engine.events.last_id
    s.sent_sample_seq = s.engine.history.last_seq
    return payload


@router.post("/sessions/{sid}/training/answer")
async def training_answer(sid: str, req: TrainingAnswerRequest) -> dict:
    s = _session(sid)
    if s.training is None:
        raise HTTPException(409, "no training exercise is active")
    try:
        s.training.answer(req.step_id, req.choice)
    except TrainingError as exc:
        raise HTTPException(409, str(exc)) from None
    return await _after_change(s)


@router.post("/sessions/{sid}/training/advance")
async def training_advance(sid: str) -> dict:
    s = _session(sid)
    if s.training is None:
        raise HTTPException(409, "no training exercise is active")
    try:
        s.training.advance()
    except TrainingError as exc:
        raise HTTPException(409, str(exc)) from None
    return await _after_change(s)


@router.post("/sessions/{sid}/training/stop")
async def training_stop(sid: str) -> dict:
    s = _session(sid)
    s.training = None
    s.engine.events.add(s.engine.time_s, "training", "Training exercise closed")
    return await _after_change(s)


ws_router = APIRouter()


@ws_router.websocket("/ws/sessions/{sid}")
async def session_ws(websocket: WebSocket, sid: str) -> None:
    if sid not in manager.sessions:
        # Accept first: closing during the handshake is reported to browsers
        # as an HTTP 403 / close code 1006, so the client could never tell
        # "session gone" (e.g. after a server restart) from a network blip.
        await websocket.accept()
        await websocket.close(code=4404, reason="session not found")
        return
    s = manager.get(sid)
    await websocket.accept()
    s.sockets.add(websocket)
    try:
        await websocket.send_json(s.init_message())
        while True:
            # Clients do not send commands over the socket (REST is used);
            # receiving keeps the connection alive and detects disconnects.
            await websocket.receive_text()
            s.touch()
    except WebSocketDisconnect:
        pass
    finally:
        s.sockets.discard(websocket)
