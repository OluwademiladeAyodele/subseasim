"""Scenario loading.

Scenario files are JSON in ``app/scenarios/data``. A file may derive from
another with ``"extends": "<id>"``; top-level keys are deep-merged and
``"element_overrides": {"<element id>": {...}}`` patches individual
elements. The merged document is validated against ``ScenarioConfig``.
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.models.scenario import ScenarioConfig


class ScenarioNotFound(KeyError):
    pass


def _deep_merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _raw_files(directory: Path) -> dict[str, dict]:
    raw: dict[str, dict] = {}
    for path in sorted(directory.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        raw[doc["id"]] = doc
    return raw


def _resolve(doc_id: str, raw: dict[str, dict], seen: tuple[str, ...] = ()) -> dict:
    if doc_id not in raw:
        raise ScenarioNotFound(doc_id)
    if doc_id in seen:
        raise ValueError(f"circular scenario inheritance: {seen + (doc_id,)}")
    doc = copy.deepcopy(raw[doc_id])
    parent_id = doc.pop("extends", None)
    overrides = doc.pop("element_overrides", {})
    if parent_id:
        doc = _deep_merge(_resolve(parent_id, raw, seen + (doc_id,)), doc)
    if overrides:
        sub = doc.get("subsystems", {}).get("elements", [])
        known = {e["id"] for e in doc["elements"]} | {e["id"] for e in sub}
        unknown = set(overrides) - known
        if unknown:
            raise ValueError(f"element_overrides reference unknown elements: {sorted(unknown)}")
        doc["elements"] = [_deep_merge(e, overrides.get(e["id"], {})) for e in doc["elements"]]
        if sub:
            doc["subsystems"]["elements"] = [_deep_merge(e, overrides.get(e["id"], {})) for e in sub]
    return doc


@lru_cache(maxsize=1)
def _catalogue() -> dict[str, ScenarioConfig]:
    raw = _raw_files(settings.scenario_dir)
    return {sid: ScenarioConfig.model_validate(_resolve(sid, raw)) for sid in raw}


def list_scenarios() -> list[ScenarioConfig]:
    return list(_catalogue().values())


def get_scenario(scenario_id: str) -> ScenarioConfig:
    cat = _catalogue()
    if scenario_id not in cat:
        raise ScenarioNotFound(scenario_id)
    return cat[scenario_id].model_copy(deep=True)


# ------------------------------------------------------------------ schematic
LAYOUT_DIR = Path(__file__).resolve().parent / "layouts"


@lru_cache(maxsize=8)
def _schematic(layout_id: str) -> dict:
    from app.models.schematic import SchematicLayout

    path = LAYOUT_DIR / f"{layout_id}.json"
    if not path.is_file():
        raise ScenarioNotFound(f"schematic layout {layout_id!r}")
    return SchematicLayout.model_validate_json(path.read_text(encoding="utf-8")).model_dump()


def get_schematic(layout_id: str) -> dict:
    """Validated workstation schematic layout (positions only)."""
    return copy.deepcopy(_schematic(layout_id))
