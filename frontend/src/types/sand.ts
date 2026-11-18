/** Sand production, detection and choke-erosion types (mirror of backend app/models/sand.py and sand/system.py). */

export interface HoleRow {
  axial_position_mm: number;
  diameter_mm: number;
  count: number;
}

export interface SandChokeInputs {
  geomechanics: {
    depth_tvd_m: number | null;
    overburden_gradient_bar_m: number | null;
    min_horizontal_stress_gradient_bar_m: number | null;
    max_horizontal_stress_gradient_bar_m: number | null;
    initial_reservoir_pressure_bara: number | null;
    stress_path_coefficient: number | null;
    twc_strength_mpa: number | null;
    ucs_mpa: number | null;
    twc_ucs_ratio: number | null;
    biot_coefficient: number | null;
    poisson_ratio: number | null;
    water_weakening_fraction: number | null;
    porosity: number | null;
    permeability_md: number | null;
  };
  completion: {
    completion_type: "cased_perforated_standalone_screens" | "cased_perforated_no_screens" | "openhole_standalone_screens" | "gravel_pack";
    perforation_diameter_mm: number | null;
    shot_density_spm: number | null;
    perforated_interval_m: number | null;
    screen_type: "wire_wrapped" | "premium_mesh" | "other" | null;
    screen_aperture_um: number | null;
    screen_damage_fraction: number;
    bridging_factor: number;
  };
  sand: {
    grain_density_kg_m3: number;
    d10_um: number | null;
    d50_um: number | null;
    d90_um: number | null;
    mode: "predictive" | "measured";
    measured_value: number | null;
    measured_unit: "kg_h" | "kg_d" | "g_s" | "pptb" | "ppm_mass_liquid" | "ppm_mass_total" | "ppm_vol_liquid";
    measured_uncertainty_pct: number;
    rate_coefficient_kg_m3: number | null;
    rate_exponent: number;
  };
  choke: {
    design: "plug_and_cage" | "external_sleeve" | "needle_and_seat" | "other";
    model_label: string | null;
    max_cv: number | null;
    min_controllable_cv: number | null;
    actuator_steps: number | null;
    cv_table: [number, number][];
    stroke_mm: number | null;
    cage_inner_diameter_mm: number | null;
    cage_wall_thickness_mm: number | null;
    hole_rows: HoleRow[];
    trim_material: string | null;
    body_material: string | null;
    trim_impact_angle_deg: number;
    plug_share: number;
    plug_diameter_mm: number | null;
    choke_outlet_bore_mm: number | null;
    gallery_diameter_mm: number | null;
    body_wall_thickness_mm: number | null;
    erosion_feedback: boolean;
  };
  custom_materials: { name: string; k: number; n: number; density_kg_m3: number; behaviour: "ductile" | "brittle" }[];
  acceptance: {
    max_hole_diameter_increase_mm: number | null;
    max_cv_increase_pct: number | null;
    max_plug_loss_mm: number | null;
    max_body_wall_loss_mm: number | null;
    max_outlet_wall_loss_mm: number | null;
    reference_step: number | null;
  };
  thresholds: {
    increased_wear: number;
    inspection_recommended: number;
    changeout_assessment: number;
    critical: number;
    elevated_rate_mm_y: number;
  };
  history: {
    label: string;
    days: number;
    choke_step: number;
    upstream_pressure_bara: number;
    downstream_pressure_bara: number;
    oil_sm3_d: number;
    gas_sm3_d: number;
    water_sm3_d: number;
    sand_kg_d: number;
    temperature_c: number;
  }[];
  inspections: {
    label: string;
    service_days: number;
    measured_max_hole_increase_mm: number | null;
    measured_cv_increase_pct: number | null;
    measured_plug_loss_mm: number | null;
    notes: string;
    trim_replaced: boolean;
  }[];
  initial_service_days: number;
}

export interface ErosionMaterial {
  key: string;
  name: string;
  k: number;
  n: number;
  density_kg_m3: number;
  behaviour: string;
  source: string;
}

export interface WearCriterion {
  key: string;
  label: string;
  unit: string;
  used: number;
  allowance: number | null;
  rate_per_s: number;
  rate_per_year: number;
  consumed: number | null;
  life_days: { p10: number; p50: number; p90: number } | null;
  life_sand_kg: number | null;
  life_liquid_sm3: number | null;
  sigma_ln: number;
  calibrated_by_inspection: boolean;
}

export interface SandChokeResults {
  available: boolean;
  reason?: string;
  service_days?: number;
  inputs_status?: Record<string, { complete: boolean; missing: string[] }>;
  sand?: {
    mode: string;
    formation_kg_d: number | null;
    produced_kg_d: number | null;
    at_choke_kg_d: number;
    missing: string[];
    assumed: string[];
    onset: {
      available: boolean;
      missing: string[];
      assumed: string[];
      critical_drawdown_bar: number | null;
      critical_bhfp_bara: number | null;
      drawdown_bar: number | null;
      risk_index: number | null;
      sigma_v_bar: number | null;
      sigma_h_bar: number | null;
      effective_strength_bar: number | null;
      notes: string[];
    } | null;
    screen: { available: boolean; passing_fraction: number | null; produced_d50_um: number | null; missing: string[]; notes: string[] };
    psd: { d50_um: number; sigma_ln: number } | null;
  } | null;
  transport?: { model: string; deposition: { segment: number; v_sl: number; v_crit: number; risk: boolean }[]; deposition_risk_segments?: number; deposition_note?: string };
  velocities?: Record<string, number | null | boolean> | null;
  erosion?: {
    trim_material: { key: string; name: string; k: number; n: number; behaviour: string; source: string } | null;
    erosion_ratio_kg_kg: number | null;
    trim_volume_rate_mm3_d: number | null;
    rows: { axial_position_mm: number; diameter_mm: number; count: number; increase_mm: number; rate_mm_y: number | null }[];
  } | null;
  criteria?: WearCriterion[];
  governing?: string | null;
  first_limit?: string | null;
  health?: { category: string; consumed_fraction: number | null; reasons: string[]; note: string };
  confidence?: { category: string; factors: string[] };
  recommendation?: { title: string; text: string; reasons: string[]; actions: string[]; disclaimer: string };
  cv_tracking?: {
    available: boolean;
    note?: string;
    ratio?: number;
    deviation_pct?: number;
    uncertainty_pct?: number;
    significant?: boolean;
    samples?: { service_days: number; ratio: number }[];
    possible_causes?: string[];
  };
  calibration?: { factor_median: number; sigma_ln: number; prior_sigma_ln: number; points: { label: string; service_days: number; used: boolean; ratio: number | null; note: string }[] };
  uncertainty_components?: Record<string, number>;
  cumulative?: Record<string, number>;
  wear_history?: { service_days: number[]; max_hole_mm: number[]; sand_kg: number[]; liquid_sm3: number[] };
  limitations?: string[];
}
