"""Application-level (non-engineering) settings.

Engineering parameters live in scenario files, never here.
Values can be overridden with environment variables prefixed SUBSEASIM_.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    #: Wall-clock period of the simulation loop [s]. Rendering-independent.
    tick_period_s: float = field(default_factory=lambda: _env_float("SUBSEASIM_TICK_PERIOD_S", 0.25))
    #: Largest simulation-time sub-step used by the integrator [s].
    max_substep_s: float = field(default_factory=lambda: _env_float("SUBSEASIM_MAX_SUBSTEP_S", 5.0))
    #: Minimum simulation time between stored trend samples [s].
    sample_interval_s: float = field(default_factory=lambda: _env_float("SUBSEASIM_SAMPLE_INTERVAL_S", 1.0))
    #: Trend-history ring-buffer length (samples per session).
    history_length: int = field(default_factory=lambda: _env_int("SUBSEASIM_HISTORY_LENGTH", 3600))
    #: Max event-log entries kept per session.
    event_log_length: int = field(default_factory=lambda: _env_int("SUBSEASIM_EVENT_LOG_LENGTH", 500))
    #: Max concurrent sessions on one server.
    max_sessions: int = field(default_factory=lambda: _env_int("SUBSEASIM_MAX_SESSIONS", 50))
    #: Sessions with no websocket and no activity for this long are removed [s].
    session_idle_timeout_s: float = field(default_factory=lambda: _env_float("SUBSEASIM_SESSION_IDLE_TIMEOUT_S", 4 * 3600))
    #: Allowed simulation speed multipliers.
    allowed_time_scales: tuple[float, ...] = (1.0, 10.0, 60.0, 300.0)
    #: Directory with built frontend (served in production). Empty = not served.
    frontend_dist: str = field(default_factory=lambda: os.environ.get("SUBSEASIM_FRONTEND_DIST", ""))
    #: Comma-separated CORS origins for development.
    cors_origins: str = field(default_factory=lambda: os.environ.get("SUBSEASIM_CORS_ORIGINS", "http://localhost:5173"))

    scenario_dir: Path = Path(__file__).resolve().parent.parent / "scenarios" / "data"


settings = Settings()
