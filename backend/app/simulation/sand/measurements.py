"""Measured sand history: CSV import, conversion to a common mass rate,
abnormal-increase detection and the measured rate used by the erosion model.

Every record keeps its own unit. Mass-rate records (kg/h, kg/d, g/s) convert
directly to kg/d. Concentration records (pptb, ppm) need the liquid rate at the
time of the measurement (and the water cut for mass-based ppm); they are
converted with the CURRENT fluid properties (stock-tank densities, GOR) and
are left unconverted, and excluded from the trend test, when the liquid rate
was not recorded.

Abnormal increase (a configurable REVIEW TRIGGER, not a safety limit): the
latest converted rate exceeds ``abnormal_increase_ratio`` x the median of the
previous ``abnormal_baseline_count`` converted records and, if given, by at
least ``abnormal_min_increase_kg_d``.
"""

from __future__ import annotations

import csv
import io
import statistics

from pydantic import ValidationError

from app.models.sand import SandInputs, SandMeasurement
from app.simulation.sand.production import measured_rate_kg_s

COLUMNS = ["timestamp", "value", "unit", "method", "uncertainty_pct", "liquid_rate_sm3_d", "water_cut", "d10_um", "d50_um", "d90_um", "note"]
REQUIRED = ["timestamp", "value"]

UNIT_ALIASES = {
    "kg/d": "kg_d", "kg/day": "kg_d", "kgd": "kg_d", "kg_d": "kg_d",
    "kg/h": "kg_h", "kg/hr": "kg_h", "kg_h": "kg_h",
    "g/s": "g_s", "g_s": "g_s",
    "pptb": "pptb", "lb/1000bbl": "pptb",
    "ppm_mass_liquid": "ppm_mass_liquid", "ppmw_liquid": "ppm_mass_liquid",
    "ppm_mass_total": "ppm_mass_total", "ppmw_total": "ppm_mass_total",
    "ppm_vol_liquid": "ppm_vol_liquid", "ppmv_liquid": "ppm_vol_liquid",
}
METHOD_ALIASES = {
    "sand_trap": "sand_trap", "sand trap": "sand_trap", "trap": "sand_trap",
    "acoustic_detector": "acoustic_detector", "acoustic": "acoustic_detector", "sdt": "acoustic_detector",
    "intrusive_probe": "intrusive_probe", "probe": "intrusive_probe", "erosion probe": "intrusive_probe",
    "well_test_sample": "well_test_sample", "well test": "well_test_sample", "sample": "well_test_sample",
    "other": "other", "": "other",
}
UNIT_LABEL = {"kg_d": "kg/d", "kg_h": "kg/h", "g_s": "g/s", "pptb": "pptb", "ppm_mass_liquid": "ppm (mass, liquid)",
              "ppm_mass_total": "ppm (mass, total)", "ppm_vol_liquid": "ppm (vol, liquid)"}
MASS_UNITS = ("kg_d", "kg_h", "g_s")


class CsvImportError(ValueError):
    def __init__(self, errors: list[dict]):
        super().__init__(f"{len(errors)} invalid line(s) in the sand measurement CSV")
        self.errors = errors


def parse_csv(text: str) -> list[SandMeasurement]:
    """Parse measurement CSV (header row required). Atomic: any invalid line
    raises CsvImportError listing every problem; nothing is imported."""
    rows = list(csv.reader(io.StringIO(text.strip().lstrip("﻿"))))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        raise CsvImportError([{"line": 1, "error": "empty file"}])
    header = [h.strip().lower() for h in rows[0]]
    errors: list[dict] = []
    unknown = [h for h in header if h not in COLUMNS]
    if unknown:
        errors.append({"line": 1, "error": f"unknown column(s): {', '.join(unknown)} (allowed: {', '.join(COLUMNS)})"})
    for c in REQUIRED:
        if c not in header:
            errors.append({"line": 1, "error": f"missing required column '{c}'"})
    if errors:
        raise CsvImportError(errors)
    out: list[SandMeasurement] = []
    for n, r in enumerate(rows[1:], start=2):
        raw = {h: (r[i].strip() if i < len(r) else "") for i, h in enumerate(header)}
        rec: dict = {}
        try:
            for k, v in raw.items():
                if v == "":
                    continue
                if k == "unit":
                    u = UNIT_ALIASES.get(v.lower())
                    if u is None:
                        raise ValueError(f"unknown unit '{v}' (use one of: {', '.join(sorted(set(UNIT_ALIASES)))})")
                    rec[k] = u
                elif k == "method":
                    m = METHOD_ALIASES.get(v.lower())
                    if m is None:
                        raise ValueError(f"unknown method '{v}'")
                    rec[k] = m
                elif k == "water_cut":
                    rec[k] = float(v.rstrip("%")) / (100.0 if v.endswith("%") else 1.0)
                elif k in ("timestamp", "note"):
                    rec[k] = v
                else:
                    rec[k] = float(v)
            out.append(SandMeasurement.model_validate(rec))
        except ValidationError as exc:
            errors.append({"line": n, "error": "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())})
        except ValueError as exc:
            errors.append({"line": n, "error": str(exc)})
    if errors:
        raise CsvImportError(errors)
    if not out:
        raise CsvImportError([{"line": 2, "error": "no data rows"}])
    return out


def to_csv(records: list[SandMeasurement]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(COLUMNS)
    for r in sorted(records, key=lambda x: x.timestamp):
        d = r.model_dump()
        d["timestamp"] = r.timestamp.isoformat()
        w.writerow(["" if d[c] is None else d[c] for c in COLUMNS])
    return buf.getvalue()


def latest(records: list[SandMeasurement]) -> SandMeasurement | None:
    return max(records, key=lambda r: r.timestamp) if records else None


def effective_sand(s: SandInputs) -> tuple[SandInputs, SandMeasurement | None]:
    """The sand inputs as used by the model: in measured mode with a history,
    the latest record sets the measured value, unit and uncertainty."""
    rec = latest(s.measurements)
    if s.mode != "measured" or rec is None:
        return s, None
    return s.model_copy(update={"measured_value": rec.value, "measured_unit": rec.unit,
                                "measured_uncertainty_pct": rec.uncertainty_pct if rec.uncertainty_pct is not None
                                else s.measured_uncertainty_pct}), rec


def to_kg_d(rec: SandMeasurement, s: SandInputs, rho_oil_sc: float, rho_water_sc: float, rho_gas_sc: float, gor: float) -> float | None:
    """Convert one record to kg/d; None when a concentration lacks the liquid rate."""
    if rec.unit not in MASS_UNITS and rec.liquid_rate_sm3_d is None:
        return None
    q = (rec.liquid_rate_sm3_d or 0.0) / 86400.0
    wc = rec.water_cut if rec.water_cut is not None else 0.0
    liq_mass = q * ((1 - wc) * rho_oil_sc + wc * rho_water_sc)
    total_mass = liq_mass + q * (1 - wc) * gor * rho_gas_sc
    tmp = s.model_copy(update={"measured_value": rec.value, "measured_unit": rec.unit})
    m = measured_rate_kg_s(tmp, q, liq_mass, total_mass)
    return None if m is None else m * 86400.0


def report(s: SandInputs, rho_oil_sc: float, rho_water_sc: float, rho_gas_sc: float, gor: float) -> dict:
    recs = sorted(s.measurements, key=lambda r: r.timestamp)
    series = []
    for r in recs:
        kg_d = to_kg_d(r, s, rho_oil_sc, rho_water_sc, rho_gas_sc, gor)
        series.append({"timestamp": r.timestamp.isoformat(), "value": r.value, "unit": r.unit, "unit_label": UNIT_LABEL[r.unit],
                       "method": r.method, "uncertainty_pct": r.uncertainty_pct, "kg_d": kg_d, "note": r.note,
                       "d50_um": r.d50_um})
    notes: list[str] = []
    unconverted = sum(1 for x in series if x["kg_d"] is None)
    if unconverted:
        notes.append(f"{unconverted} concentration record(s) without the liquid rate cannot be converted to kg/d and are left out of the trend test.")
    if any(x["kg_d"] is not None and x["unit"] not in MASS_UNITS for x in series):
        notes.append("Concentration records are converted with the CURRENT stock-tank densities and GOR.")
    conv = [x for x in series if x["kg_d"] is not None]
    n = s.abnormal_baseline_count
    abnormal = {"flag": False, "available": False, "ratio": None, "baseline_kg_d": None, "latest_kg_d": None,
                "trigger_ratio": s.abnormal_increase_ratio, "baseline_count": n, "min_increase_kg_d": s.abnormal_min_increase_kg_d,
                "text": f"Needs at least 2 converted records (latest + baseline); have {len(conv)}."}
    if len(conv) >= 2:
        last = conv[-1]
        base = conv[-1 - n:-1]
        med = statistics.median(x["kg_d"] for x in base)
        ratio = last["kg_d"] / med if med > 0 else (float("inf") if last["kg_d"] > 0 else 1.0)
        inc = last["kg_d"] - med
        flag = ratio > s.abnormal_increase_ratio and (s.abnormal_min_increase_kg_d is None or inc >= s.abnormal_min_increase_kg_d)
        abnormal = abnormal | {
            "available": True, "flag": flag, "ratio": None if ratio == float("inf") else ratio, "baseline_kg_d": med,
            "latest_kg_d": last["kg_d"], "latest_timestamp": last["timestamp"],
            "text": (f"Latest {last['kg_d']:.2f} kg/d ({last['timestamp'][:10]}) is "
                     + (f"{ratio:.1f} x" if ratio != float("inf") else "above a zero")
                     + f" the median of the previous {len(base)} record(s) ({med:.2f} kg/d): "
                     + ("ABNORMAL INCREASE - review the sand source, the choke and the sand-handling plan." if flag
                        else f"within the review trigger ({s.abnormal_increase_ratio:g} x)."))}
    eff, rec = effective_sand(s)
    return {"count": len(recs), "series": series, "abnormal": abnormal, "notes": notes,
            "drives_model": rec is not None,
            "driving_record": None if rec is None else {"timestamp": rec.timestamp.isoformat(), "value": rec.value,
                                                       "unit_label": UNIT_LABEL[rec.unit], "method": rec.method},
            "mode": s.mode,
            "trigger_note": "Abnormal-increase trigger is configurable (ratio, baseline count, minimum increase) - a review prompt, not a safety limit."}
