"""Simulation records: a durable, traceable store of what was simulated.

One record = one saved assessment of a session: the input conditions, the
results, the calculation methods and model versions, the assumptions, the
uncertainty, the validation status and the PROVENANCE of every input group
(measured / estimated / simulated / imported / illustrative / configured).

Storage is SQLite through the Python standard library (no extra service).
The file is ``$SUBSEASIM_DB_PATH`` (default ``backend/data/records.sqlite``),
read at call time so tests and deployments can point elsewhere. Records are
immutable once written (no update API): a new assessment is a new record.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 3  # 2: has_comparison column; 3: surrogates table (migrated in place)
_DEFAULT = Path(__file__).resolve().parent.parent.parent / "data" / "records.sqlite"
_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS simulation_records (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    label TEXT NOT NULL,
    notes TEXT,
    scenario_id TEXT NOT NULL,
    scenario_name TEXT,
    session_id TEXT,
    sim_time_s REAL NOT NULL,
    app_version TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    health_category TEXT,
    has_comparison INTEGER NOT NULL DEFAULT 0,
    body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_records_created ON simulation_records (created_at);
CREATE INDEX IF NOT EXISTS ix_records_scenario ON simulation_records (scenario_id);
CREATE TABLE IF NOT EXISTS surrogates (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    name TEXT NOT NULL,
    method TEXT NOT NULL,
    scenario_id TEXT,
    n_cases INTEGER NOT NULL,
    sources TEXT NOT NULL,
    body TEXT NOT NULL
);
"""

SUMMARY_COLS = ("id", "created_at", "label", "notes", "scenario_id", "scenario_name", "session_id", "sim_time_s",
                "app_version", "validation_status", "health_category", "has_comparison")


class RecordNotFound(KeyError):
    pass


def db_path() -> Path:
    return Path(os.environ.get("SUBSEASIM_DB_PATH") or _DEFAULT)


@contextmanager
def _connect():
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        con = sqlite3.connect(p, timeout=10)
        try:
            con.row_factory = sqlite3.Row
            con.executescript(_SCHEMA)
            _migrate(con)
            yield con
            con.commit()
        finally:
            con.close()


def _migrate(con: sqlite3.Connection) -> None:
    """Bring an older database to SCHEMA_VERSION in place (records are kept)."""
    cols = {r[1] for r in con.execute("PRAGMA table_info(simulation_records)")}
    if "has_comparison" not in cols:  # 1 -> 2
        con.execute("ALTER TABLE simulation_records ADD COLUMN has_comparison INTEGER NOT NULL DEFAULT 0")
    con.execute("INSERT INTO meta (key, value) VALUES ('schema_version', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(SCHEMA_VERSION),))


def save(body: dict, label: str, notes: str | None = None) -> dict:
    """Store a record body (see app.storage.assessment.build_record). Returns the summary."""
    rid = uuid.uuid4().hex
    now = datetime.now(UTC).isoformat(timespec="seconds")
    body = {**body, "id": rid, "created_at": now, "label": label, "notes": notes}
    hdr = body["header"]
    row = {"id": rid, "created_at": now, "label": label, "notes": notes, "scenario_id": hdr["scenario_id"],
           "scenario_name": hdr.get("scenario_name"), "session_id": hdr.get("session_id"), "sim_time_s": hdr["sim_time_s"],
           "app_version": hdr["app_version"], "validation_status": body["validation"]["overall"],
           "health_category": (body["results"].get("choke_health") or {}).get("category"),
           "has_comparison": 1 if body.get("comparison") else 0}
    with _connect() as con:
        con.execute(f"INSERT INTO simulation_records ({', '.join(SUMMARY_COLS)}, body) VALUES "
                    f"({', '.join('?' for _ in SUMMARY_COLS)}, ?)", (*[row[c] for c in SUMMARY_COLS], json.dumps(body)))
    return row


def list_records(scenario_id: str | None = None, limit: int = 100) -> list[dict]:
    q = f"SELECT {', '.join(SUMMARY_COLS)} FROM simulation_records"
    args: list = []
    if scenario_id:
        q += " WHERE scenario_id = ?"
        args.append(scenario_id)
    q += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
    args.append(max(1, min(limit, 1000)))
    with _connect() as con:
        return [dict(r) for r in con.execute(q, args)]


def get(rid: str) -> dict:
    with _connect() as con:
        r = con.execute("SELECT body FROM simulation_records WHERE id = ?", (rid,)).fetchone()
    if r is None:
        raise RecordNotFound(rid)
    return json.loads(r["body"])


# ------------------------------------------------------------ surrogates
def save_surrogate(sur) -> dict:
    """Store a trained surrogate (its CASE LIBRARY and settings; the model is
    refitted deterministically on load)."""
    sid = uuid.uuid4().hex
    row = {"id": sid, "created_at": sur.created_at, "name": sur.name, "method": sur.method, "scenario_id": sur.scenario_id,
           "n_cases": len(sur.cases), "sources": json.dumps(sur.source_summary)}
    with _connect() as con:
        con.execute("INSERT INTO surrogates (id, created_at, name, method, scenario_id, n_cases, sources, body) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (sid, row["created_at"], row["name"], row["method"], row["scenario_id"], row["n_cases"], row["sources"], json.dumps(sur.to_dict())))
    return row | {"sources": sur.source_summary}


def list_surrogates() -> list[dict]:
    with _connect() as con:
        rows = [dict(r) for r in con.execute("SELECT id, created_at, name, method, scenario_id, n_cases, sources FROM surrogates "
                                             "ORDER BY created_at DESC, rowid DESC")]
    for r in rows:
        r["sources"] = json.loads(r["sources"])
    return rows


def get_surrogate_body(sid: str) -> dict:
    with _connect() as con:
        r = con.execute("SELECT body FROM surrogates WHERE id = ?", (sid,)).fetchone()
    if r is None:
        raise RecordNotFound(sid)
    return json.loads(r["body"])


def delete_surrogate(sid: str) -> None:
    with _connect() as con:
        n = con.execute("DELETE FROM surrogates WHERE id = ?", (sid,)).rowcount
    if n == 0:
        raise RecordNotFound(sid)


def delete(rid: str) -> None:
    with _connect() as con:
        n = con.execute("DELETE FROM simulation_records WHERE id = ?", (rid,)).rowcount
    if n == 0:
        raise RecordNotFound(rid)
