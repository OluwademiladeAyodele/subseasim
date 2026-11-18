"""Engineering model registry: method, version, model status and validation
of every calculation module. Saved simulation records and reports quote it,
so each result can be traced to the method that produced it.

Model status follows the ladder of the engineering specification:
analytical estimate < correlation-based screening < simplified simulation <
surrogate-model prediction < high-fidelity CFD < experimentally validated <
field-calibrated. Bump a module's version whenever its equations or
constants change.
"""

from __future__ import annotations

APP_VERSION = "0.4.0"

STATUS_LADDER = (
    "Analytical estimate",
    "Correlation-based screening",
    "Simplified simulation",
    "Surrogate-model prediction",
    "High-fidelity CFD",
    "Experimentally validated",
    "Field-calibrated",
)

MODELS: dict[str, dict] = {
    "dynamic_hydraulics": {
        "version": "2.1", "status": "Simplified simulation",
        "method": "Lumped compressible P/Q network (line pack, wall elasticity, inertia), implicit Euler + Newton, fixed step; radial reservoir transient",
        "validation": "Verified against analytic limits and the steady solver; not field-validated", "doc": "DYNAMIC_SIMULATION_MODEL.md"},
    "black_oil_pvt": {
        "version": "1.0", "status": "Correlation-based screening",
        "method": "Standing (Rs, Pb, Bo), Vasquez-Beggs, Beggs-Robinson, DAK / Sutton Z, Lee-Gonzalez-Eakin, McCain water",
        "validation": "Verified against published charts / hand evaluation; generic correlations, not fitted to a PVT report", "doc": "MULTIPHASE_FLOW_MODEL.md"},
    "multiphase_flow": {
        "version": "1.0", "status": "Simplified simulation",
        "method": "Beggs & Brill (or no-slip) pipe flow, Sachdeva choke (critical / sub-critical), mass-based transport",
        "validation": "Verified (single-phase limits, conservation); Beggs & Brill extrapolated to tubing; not field-validated", "doc": "MULTIPHASE_FLOW_MODEL.md"},
    "mpfm": {
        "version": "1.0", "status": "Simplified simulation",
        "method": "Venturi dP + dual-energy gamma phase fractions, slip model, GUM uncertainty propagation",
        "validation": "Verified (inversion, identities, GUM); representative meter, not a vendor instrument", "doc": "MPFM_MEASUREMENT_MODEL.md"},
    "sanding": {
        "version": "1.0", "status": "Correlation-based screening",
        "method": "Willson et al. (2002) TWC critical drawdown; calibrated empirical post-onset rate; log-normal PSD; screen bridging",
        "validation": "Verified against hand evaluation; rate coefficient must be calibrated with field sand data", "doc": "SAND_PRODUCTION_MODEL.md"},
    "measured_sand_history": {
        "version": "1.0", "status": "Analytical estimate",
        "method": "Unit conversion to kg/d; abnormal increase = latest > ratio x median of previous N (configurable)",
        "validation": "Hand-calculated conversions; trigger is a review prompt, not a safety limit", "doc": "SAND_PRODUCTION_MODEL.md"},
    "sand_transport": {
        "version": "1.0", "status": "Simplified simulation",
        "method": "Conservative upwind transport on the mass-tracked composition grid; Durand deposition screening",
        "validation": "Verified (transit delay, conservation); deposition not simulated", "doc": "SAND_TRANSPORT_MODEL.md"},
    "sand_detector": {
        "version": "1.0", "status": "Simplified simulation",
        "method": "Acoustic detector: calibration bias, noise floor, minimum velocity, range",
        "validation": "Model behaviour verified; not a vendor instrument", "doc": "SAND_TRANSPORT_MODEL.md"},
    "choke_erosion": {
        "version": "1.0", "status": "Correlation-based screening",
        "method": "DNV-RP-O501 particle erosion on cage holes / plug, straight-pipe outlet, gallery impingement; Bayesian calibration from inspections",
        "validation": "Verified against hand evaluation of DNV equations; constants to be verified against the licensed document; geometry generic", "doc": "CHOKE_EROSION_MODEL.md"},
    "choke_maintenance": {
        "version": "1.0", "status": "Correlation-based screening",
        "method": "Wear against site allowances, P10/P50/P90 remaining life (log-normal), Cv tracking, configurable health categories",
        "validation": "Categories are configured thresholds, not universal limits", "doc": "CHOKE_MAINTENANCE_MODEL.md"},
    "cavitation": {
        "version": "1.0", "status": "Correlation-based screening",
        "method": "IEC 60534-2-1 FL vena-contracta / choked dP; sigma = (P1 - Pv)/(P1 - P2) vs valve-specific limits; IAPWS-IF97 Pv",
        "validation": "Verified against IF97 verification values and hand calculation; not CFD", "doc": "CHOKE_CAVITATION_MODEL.md"},
    "surrogate": {
        "version": "1.0", "status": "Surrogate-model prediction",
        "method": "Gaussian process (ARD squared-exponential, max. marginal likelihood) or quadratic response surface on a case library; envelope check",
        "validation": "Leave-one-out cross-validation against its training source (RMSE, R2, 95 % coverage); inherits that source's limitations", "doc": "SURROGATE_MODELS.md"},
    "api14e": {
        "version": "1.0", "status": "Correlation-based screening",
        "method": "API RP 14E erosional velocity Ve = C / sqrt(rho_m), supplementary",
        "validation": "Hand evaluation; not a sand-erosion or choke model", "doc": "CHOKE_EROSION_MODEL.md"},
}


def models(*keys: str) -> dict[str, dict]:
    return {k: MODELS[k] for k in (keys or MODELS)}
