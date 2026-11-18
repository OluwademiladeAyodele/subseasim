"""Sand production, sand transport, sand detection, choke-erosion and choke-cavitation INPUTS.

Every site-specific value is optional: a calculation that needs a missing
input reports "unavailable - missing inputs: ..." instead of using a
made-up value. Units are in every field name. These inputs are edited in
the app (Sand & choke inputs page) and can be exported / imported as JSON.
See docs/SAND_PRODUCTION_MODEL.md, docs/CHOKE_EROSION_MODEL.md and
docs/CHOKE_MAINTENANCE_MODEL.md.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Pos = Annotated[float, Field(gt=0)]
NonNeg = Annotated[float, Field(ge=0)]
Frac = Annotated[float, Field(ge=0, le=1)]


class _S(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GeomechanicsInputs(_S):
    """Reservoir rock and in-situ stresses at the completed interval."""

    depth_tvd_m: Pos | None = None
    #: Total vertical (overburden) stress gradient [bar/m] (~0.22-0.25).
    overburden_gradient_bar_m: Pos | None = None
    #: Minimum horizontal total stress gradient [bar/m].
    min_horizontal_stress_gradient_bar_m: Pos | None = None
    #: Maximum horizontal total stress gradient [bar/m] (defaults to the minimum).
    max_horizontal_stress_gradient_bar_m: Pos | None = None
    #: Initial reservoir pressure (stress-path reference) [bara].
    initial_reservoir_pressure_bara: Pos | None = None
    #: Horizontal stress-path coefficient d(sigma_h)/d(Pp) during depletion (0.5-0.8 typical).
    stress_path_coefficient: Frac | None = None
    #: Thick-walled-cylinder (hollow cylinder, OD/ID = 3) collapse strength [MPa] - PREFERRED.
    twc_strength_mpa: Pos | None = None
    #: Unconfined compressive strength [MPa] - used only if TWC is not given.
    ucs_mpa: Pos | None = None
    #: TWC / UCS ratio used when only UCS is known (site correlation; 1.5-4 typical).
    twc_ucs_ratio: Pos | None = None
    biot_coefficient: Annotated[float, Field(gt=0, le=1)] | None = None
    poisson_ratio: Annotated[float, Field(gt=0, lt=0.5)] | None = None
    #: Strength reduction at 100 % water saturation of the near-wellbore (water weakening).
    water_weakening_fraction: Frac | None = None
    porosity: Annotated[float, Field(gt=0, lt=0.6)] | None = None
    permeability_md: Pos | None = None


class CompletionInputs(_S):
    completion_type: Literal["cased_perforated_standalone_screens", "cased_perforated_no_screens", "openhole_standalone_screens",
                             "gravel_pack"] = "cased_perforated_standalone_screens"
    perforation_diameter_mm: Pos | None = None
    shot_density_spm: Pos | None = None
    perforated_interval_m: Pos | None = None
    screen_type: Literal["wire_wrapped", "premium_mesh", "other"] | None = None
    #: Nominal screen aperture / slot width [micrometres].
    screen_aperture_um: Pos | None = None
    #: Fraction of the screen area that has failed (hole / erosion) - bypasses retention.
    screen_damage_fraction: Frac = 0.0
    #: Bridging: once a stable sand bridge forms at the screen only grains finer than
    #: aperture / bridging_factor pass (1 = purely geometric retention, 2-3 typical).
    bridging_factor: Annotated[float, Field(ge=1, le=5)] = 2.0


class SandInputs(_S):
    grain_density_kg_m3: Pos = 2650.0
    #: Formation particle-size distribution (sieve / laser) [micrometres].
    d10_um: Pos | None = None
    d50_um: Pos | None = None
    d90_um: Pos | None = None
    #: Sand production mode: predictive (geomechanics) or measured / configured.
    mode: Literal["predictive", "measured"] = "predictive"
    #: Measured / configured produced sand (at the wellhead, i.e. after the screens).
    measured_value: NonNeg | None = None
    measured_unit: Literal["kg_h", "kg_d", "g_s", "pptb", "ppm_mass_liquid", "ppm_mass_total", "ppm_vol_liquid"] = "kg_d"
    #: Relative standard uncertainty of the measured sand rate [%].
    measured_uncertainty_pct: NonNeg = 30.0
    #: Predictive model: formation sand mass per m3 of produced liquid (reservoir conditions) at
    #: twice the critical drawdown [kg/m3]. MUST be calibrated (sand-trap / detector data).
    rate_coefficient_kg_m3: NonNeg | None = None
    rate_exponent: Pos = 1.5


class DetectorInputs(_S):
    tag: str = "SDT-101"
    detector_type: Literal["acoustic_non_intrusive", "intrusive_erosion_probe"] = "acoustic_non_intrusive"
    #: Calibration factor uncertainty (1 sigma) [%].
    calibration_uncertainty_pct: NonNeg = 25.0
    #: Mixture velocity below which an acoustic detector cannot detect sand [m/s].
    min_velocity_m_s: NonNeg = 1.0
    #: Background (flow-noise) equivalent sand rate [g/s].
    noise_floor_g_s: NonNeg = 0.005
    alarm_threshold_g_s: Pos = 0.1
    range_max_g_s: Pos = 50.0


class HoleRow(_S):
    """A row of cage holes: holes start to open when the plug passes ``axial_position_mm``."""

    axial_position_mm: NonNeg
    diameter_mm: Pos
    count: Annotated[int, Field(ge=1, le=200)]


class ChokeTrimInputs(_S):
    """Production choke trim (plug & multi-hole cage)."""

    design: Literal["plug_and_cage", "external_sleeve", "needle_and_seat", "other"] = "plug_and_cage"
    model_label: str | None = None
    max_cv: Pos | None = None
    min_controllable_cv: Pos | None = None
    actuator_steps: Annotated[int, Field(ge=1, le=10000)] | None = None
    #: Vendor Cv vs step table [[step, Cv], ...] - nominal (new trim).
    cv_table: list[tuple[float, float]] = Field(default_factory=list)
    #: Plug stroke from closed to fully open [mm].
    stroke_mm: Pos | None = None
    cage_inner_diameter_mm: Pos | None = None
    cage_wall_thickness_mm: Pos | None = None
    hole_rows: list[HoleRow] = Field(default_factory=list)
    trim_material: str | None = None  # key into the material library
    body_material: str | None = None
    #: Mean particle impact angle at the trim [deg].
    trim_impact_angle_deg: Annotated[float, Field(gt=0, le=90)] = 30.0
    #: Share of the trim material loss at the plug / seat (rest at the cage holes).
    plug_share: Frac = 0.3
    plug_diameter_mm: Pos | None = None
    choke_outlet_bore_mm: Pos | None = None
    gallery_diameter_mm: Pos | None = None
    body_wall_thickness_mm: Pos | None = None
    #: Let the predicted hole growth change the simulated choke Cv (closed loop).
    erosion_feedback: bool = True


class CustomMaterial(_S):
    name: str
    k: Pos  # DNV-style K [ (m/s)^-n ]
    n: Pos
    density_kg_m3: Pos
    behaviour: Literal["ductile", "brittle"]


class AcceptanceCriteria(_S):
    """When the operator inspects / changes out the choke (site practice)."""

    max_hole_diameter_increase_mm: Pos | None = None
    max_cv_increase_pct: Pos | None = None
    max_plug_loss_mm: Pos | None = None
    max_body_wall_loss_mm: Pos | None = None
    max_outlet_wall_loss_mm: Pos | None = None
    #: Reference step for the Cv-increase criterion (normal operating opening).
    reference_step: float | None = None


class HealthThresholds(_S):
    """Fraction of the most-consumed allowance at which each category starts."""

    increased_wear: Frac = 0.25
    inspection_recommended: Frac = 0.5
    changeout_assessment: Frac = 0.75
    critical: Frac = 0.9
    #: Trim erosion rate that flags "elevated erosion risk" [mm/year of hole growth].
    elevated_rate_mm_y: Pos = 1.0


class HistoryPeriod(_S):
    """Past operating period applied to pre-load wear (e.g. monthly averages)."""

    label: str = ""
    days: Pos
    choke_step: NonNeg
    upstream_pressure_bara: Pos
    downstream_pressure_bara: Pos
    oil_sm3_d: NonNeg
    gas_sm3_d: NonNeg
    water_sm3_d: NonNeg
    sand_kg_d: NonNeg
    temperature_c: float = 60.0


class InspectionRecord(_S):
    label: str = ""
    #: Service time of the trim at the inspection [days since installation].
    service_days: NonNeg
    measured_max_hole_increase_mm: NonNeg | None = None
    measured_cv_increase_pct: float | None = None
    measured_plug_loss_mm: NonNeg | None = None
    notes: str = ""
    #: Trim replaced at this inspection (wear and calibration history restart).
    trim_replaced: bool = False


class FlPoint(_S):
    opening_pct: Annotated[float, Field(ge=0, le=100)]
    fl: Annotated[float, Field(gt=0, le=1)]


class CavitationInputs(_S):
    """Valve-specific cavitation data of the production choke trim. Every
    value comes from the manufacturer or a PVT report; nothing is assumed."""

    #: Liquid pressure-recovery factor FL (IEC 60534-2-1) of the trim, one value for all openings.
    fl: Annotated[float, Field(gt=0, le=1)] | None = None
    #: FL against opening (preferred when the vendor gives it); overrides ``fl``.
    fl_table: list[FlPoint] = Field(default_factory=list)
    fl_source: str | None = None
    #: Cavitation index limits sigma = (P1 - Pv)/(P1 - P2) for this trim (ISA-RP75.23 form).
    sigma_incipient: Pos | None = None
    sigma_constant: Pos | None = None
    #: Manufacturer's recommended minimum sigma (damage limit).
    sigma_damage: Pos | None = None
    threshold_source: str | None = None
    #: Bubble point of the produced oil from a PVT report [bara]; overrides the correlation.
    bubble_point_bara: Pos | None = None
    #: Sensitivity band applied to the bubble point [%].
    bubble_point_uncertainty_pct: Annotated[float, Field(ge=0, le=50)] = 10.0

    @model_validator(mode="after")
    def _ordered(self):
        vals = [v for v in (self.sigma_incipient, self.sigma_constant, self.sigma_damage) if v is not None]
        if any(a <= b for a, b in zip(vals, vals[1:])):
            raise ValueError("sigma limits must decrease: incipient > constant > damage")
        return self


class SandChokeInputs(_S):
    geomechanics: GeomechanicsInputs = Field(default_factory=GeomechanicsInputs)
    completion: CompletionInputs = Field(default_factory=CompletionInputs)
    sand: SandInputs = Field(default_factory=SandInputs)
    detector: DetectorInputs = Field(default_factory=DetectorInputs)
    choke: ChokeTrimInputs = Field(default_factory=ChokeTrimInputs)
    cavitation: CavitationInputs = Field(default_factory=CavitationInputs)
    custom_materials: list[CustomMaterial] = Field(default_factory=list)
    acceptance: AcceptanceCriteria = Field(default_factory=AcceptanceCriteria)
    thresholds: HealthThresholds = Field(default_factory=HealthThresholds)
    history: list[HistoryPeriod] = Field(default_factory=list)
    inspections: list[InspectionRecord] = Field(default_factory=list)
    #: Trim service time already accumulated before the simulation starts [days].
    initial_service_days: NonNeg = 0.0

    @model_validator(mode="before")
    @classmethod
    def _rename_retired_detector_tag(cls, data):
        # saves made before the plain-tag nomenclature call the detector XT3001
        det = data.get("detector") if isinstance(data, dict) else None
        if isinstance(det, dict) and det.get("tag") == "XT3001":
            data = {**data, "detector": {**det, "tag": "SDT-101"}}
        return data
