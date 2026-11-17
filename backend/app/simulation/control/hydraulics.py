"""Subsea control hydraulics: HPU supplies, SCM selector valves and headers.

Purpose (training): show that every hydraulically actuated tree valve is held
open by control-fluid pressure, that the selector valves route the LP / HP
supplies to the subsea control module (SCM) headers, and that losing the
supply makes fail-safe valves close.

Model (deliberately simple and documented in docs/CHRISTMAS_TREE_LAYOUT.md):

* A supply is an ideal pressure source (HPU discharge referred to the SCM)
  that can be made unavailable (HPU trip / umbilical failure).
* A selector valve opens linearly over its stroke time.
* Each header pressure follows a first-order lag:
      dp/dt = o * (p_supply - p) / tau_charge - (1 - o) * p / tau_bleed
  with o the selector-valve opening (0..1) and p_supply = 0 when the supply
  is unavailable. Header bleed-down represents pilot consumption and leakage
  to the return line; actuator volumes, pilot valves and umbilical pressure
  transients are not modelled.
* The pressure available to a valve actuator is the HIGHEST header pressure
  of its supply (SCM A / SCM B redundancy). Below the supply's minimum
  operating pressure the actuators can no longer be held open: fail-safe
  valves are commanded closed (spring return) and opening commands are
  rejected. Valves not listed as fail-safe (stepping-actuator chokes,
  metering valves) fail as-is.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.core import units as u
from app.models.scenario import ControlHydraulicsConfig


@dataclass
class SelectorState:
    tag: str
    name: str
    header: str
    stroke_time_s: float
    opening: float  # 0..1
    commanded: float  # 0 or 1

    @property
    def moving(self) -> bool:
        return abs(self.opening - self.commanded) > 1e-9


@dataclass
class HeaderState:
    id: str
    name: str
    tag: str
    supply: str
    scm: str
    tau_charge: float
    tau_bleed: float
    p: float  # [Pa]


@dataclass
class SupplyState:
    id: str
    name: str
    tag: str
    p_nominal: float  # [Pa]
    p_min: float  # [Pa]
    available: bool

    @property
    def p(self) -> float:
        return self.p_nominal if self.available else 0.0


class ControlHydraulics:
    def __init__(self, cfg: ControlHydraulicsConfig):
        self.cfg = cfg
        self.supplies = {
            s.id: SupplyState(s.id, s.name, s.tag, u.bara_to_pa(s.pressure_bara), u.bara_to_pa(s.minimum_operating_pressure_bara), s.available)
            for s in cfg.supplies
        }
        self.headers: dict[str, HeaderState] = {}
        for h in cfg.headers:
            if h.supply not in self.supplies:
                raise ValueError(f"hydraulic header {h.id}: unknown supply {h.supply!r}")
            self.headers[h.id] = HeaderState(h.id, h.name, h.tag, h.supply, h.scm, h.charge_time_constant_s, h.bleed_time_constant_s, 0.0)
        self.selectors: dict[str, SelectorState] = {}
        for v in cfg.selector_valves:
            if v.header not in self.headers:
                raise ValueError(f"selector valve {v.tag}: unknown header {v.header!r}")
            o = 1.0 if v.initial_open else 0.0
            self.selectors[v.tag] = SelectorState(v.tag, v.name, v.header, v.stroke_time_s, o, o)
        for tag, sid in cfg.valve_supply.items():
            if sid not in self.supplies:
                raise ValueError(f"valve {tag}: unknown hydraulic supply {sid!r}")
        # initial condition: headers at their steady state
        for h in self.headers.values():
            o = self._opening(h.id)
            sp = self.supplies[h.supply].p
            # steady state of the first-order balance
            a, b = o / h.tau_charge, (1 - o) / h.tau_bleed
            h.p = a * sp / (a + b) if a + b > 0 else 0.0
        self.lost: set[str] = {sid for sid in self.supplies if not self.supply_ok(sid)}

    # --------------------------------------------------------------- queries
    def _opening(self, header_id: str) -> float:
        return max((s.opening for s in self.selectors.values() if s.header == header_id), default=0.0)

    def supply_pressure_at_actuators(self, sid: str) -> float:
        return max((h.p for h in self.headers.values() if h.supply == sid), default=0.0)

    def supply_ok(self, sid: str) -> bool:
        return self.supply_pressure_at_actuators(sid) >= self.supplies[sid].p_min

    def supply_of(self, valve_tag: str) -> str | None:
        return self.cfg.valve_supply.get(valve_tag)

    def can_open(self, valve_tag: str) -> tuple[bool, str]:
        sid = self.supply_of(valve_tag)
        if sid is None or self.supply_ok(sid):
            return True, ""
        s = self.supplies[sid]
        return False, (f"insufficient {s.name} hydraulic pressure at the SCM ({u.pa_to_bara(self.supply_pressure_at_actuators(sid)):.0f} "
                       f"bara, minimum {u.pa_to_bara(s.p_min):.0f} bara): the actuator cannot be opened")

    # -------------------------------------------------------------- commands
    def command_selector(self, tag: str, open_: bool) -> None:
        self.selectors[tag].commanded = 1.0 if open_ else 0.0

    def set_supply_available(self, sid: str, available: bool) -> None:
        self.supplies[sid].available = available

    # ------------------------------------------------------------------ time
    def step(self, dt: float) -> tuple[list[str], list[str]]:
        """Advance; returns (supplies lost this step, supplies restored)."""
        for s in self.selectors.values():
            if s.moving:
                rate = dt / s.stroke_time_s
                s.opening = min(s.commanded, s.opening + rate) if s.commanded > s.opening else max(s.commanded, s.opening - rate)
        for h in self.headers.values():
            o = self._opening(h.id)
            sp = self.supplies[h.supply].p
            a, b = o / h.tau_charge, (1 - o) / h.tau_bleed
            k = a + b
            if k <= 0:
                continue
            target = a * sp / k
            # exact solution of the linear ODE over dt (unconditionally stable)
            h.p = target + (h.p - target) * math.exp(-k * dt)
        lost, restored = [], []
        for sid in self.supplies:
            ok = self.supply_ok(sid)
            if not ok and sid not in self.lost:
                self.lost.add(sid)
                lost.append(sid)
            elif ok and sid in self.lost:
                self.lost.discard(sid)
                restored.append(sid)
        return lost, restored

    def fail_safe_valves(self, sid: str) -> list[str]:
        return [t for t in self.cfg.fail_safe_close if self.cfg.valve_supply.get(t) == sid]

    def snapshot(self) -> dict:
        return {
            "supplies": [
                {"id": s.id, "name": s.name, "tag": s.tag, "available": s.available, "pressure_pa": s.p,
                 "nominal_pressure_pa": s.p_nominal, "minimum_operating_pressure_pa": s.p_min,
                 "actuator_pressure_pa": self.supply_pressure_at_actuators(s.id), "ok": self.supply_ok(s.id),
                 "valves": sorted(t for t, x in self.cfg.valve_supply.items() if x == s.id),
                 "fail_safe_close": self.fail_safe_valves(s.id)}
                for s in self.supplies.values()
            ],
            "headers": [
                {"id": h.id, "name": h.name, "tag": h.tag, "supply": h.supply, "scm": h.scm, "pressure_pa": h.p}
                for h in self.headers.values()
            ],
            "selector_valves": [
                {"tag": s.tag, "name": s.name, "header": s.header, "opening_pct": 100 * s.opening,
                 "commanded_pct": 100 * s.commanded, "moving": s.moving, "stroke_time_s": s.stroke_time_s}
                for s in self.selectors.values()
            ],
        }
