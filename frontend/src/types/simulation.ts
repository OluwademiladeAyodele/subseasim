/**
 * Types mirroring the backend API (app/simulation/engine.py snapshot).
 * All physical values are SI: pressure Pa ABSOLUTE, differential Pa,
 * temperature K, flow m3/s. Conversion for display happens in lib/units.ts.
 */
import type { ErosionMaterial, SandChokeInputs, SandChokeResults } from "./sand";

export type { ErosionMaterial, SandChokeInputs, SandChokeResults } from "./sand";

export type SimStatus = "ready" | "running" | "paused";
export type SimMode = "steady" | "dynamic";
export type NodeState = "flowing" | "static_reservoir" | "static_boundary" | "trapped" | "not_modelled";
export type ElementState = "flowing" | "no_flow" | "closed" | "not_modelled";
export type ElementKind = "inflow" | "pipe" | "valve" | "choke" | "check_valve";
export type ValveCommand = "open" | "close" | "set_position";
export type InstrumentType = "pressure" | "temperature" | "flow" | "differential_pressure" | "concentration";
export type InstrumentStatus = "GOOD" | "OUT_OF_RANGE_HIGH" | "OUT_OF_RANGE_LOW" | "UNDETERMINED" | "BAD" | "NOT_MODELLED";

export interface ScenarioInfo {
  id: string;
  name: string;
  description: string;
  data_classification: string;
}

export interface NodeSnapshot {
  id: string;
  name: string;
  elevation_m: number;
  pressure_pa: number | null;
  temperature_k: number | null;
  state: NodeState;
  /** dynamic mode: dP/dt over the last solver step [Pa/s] */
  rate_pa_s?: number;
  /** dynamic mode: steady-state reference pressure (production path) */
  steady_pressure_pa?: number | null;
  /** fixed-pressure boundary node */
  boundary?: boolean;
}

interface ElementBase {
  id: string;
  name: string;
  kind: ElementKind;
  from: string;
  to: string;
  state: ElementState;
  dp_pa: number | null;
  branch?: boolean;
  flow_m3s?: number | null;
}

export interface InflowSnapshot extends ElementBase {
  kind: "inflow";
  productivity_index_si: number;
}

export interface PipeSnapshot extends ElementBase {
  kind: "pipe";
  role: "tubing" | "flowline" | "jumper";
  length_m: number;
  inner_diameter_m: number;
  roughness_m: number;
  dz_m: number;
  overall_htc_w_m2k: number;
  hydrostatic_dp_pa: number;
  friction_dp_pa?: number;
  velocity_m_s: number | null;
  reynolds: number;
  zone?: string;
  inlet_flow_m3s?: number;
  outlet_flow_m3s?: number;
  volume_m3?: number;
  capacitance_m3_per_pa?: number;
  wave_speed_m_s?: number;
  acoustic_transit_s?: number;
  residence_time_s?: number | null;
  segments?: number;
  linepack_change_m3?: number;
  pressure_profile?: { x_m: number; p_pa: number }[];
  profile?: { x_m: number[]; t_k: number[]; c: Record<string, number[]> };
}

export interface CheckValveSnapshot extends ElementBase {
  kind: "check_valve";
  tag: string;
  cracking_pressure_pa: number;
  open?: boolean;
}

export interface RestrictionSnapshot extends ElementBase {
  kind: "valve" | "choke";
  tag: string;
  subtype: string;
  position_pct: number;
  commanded_pct: number;
  moving: boolean;
  time_to_target_s: number;
  full_stroke_time_s: number;
  capacity_m2: number;
  characteristic: string;
  characteristic_description: string;
  rangeability: number;
  supports_intermediate: boolean;
  available: boolean;
  supported_commands: ValveCommand[];
  bore_diameter_m?: number;
  loss_coefficient_open?: number;
  cv_max?: number;
  phase?: "idle" | "delay" | "travel";
  actuation_delay_s?: number;
  close_stroke_time_s?: number;
  nominal_stroke_time_s?: number | null;
  seat_leak_area_mm2?: number;
  leaking?: boolean;
}

export type ElementSnapshot = InflowSnapshot | PipeSnapshot | RestrictionSnapshot | CheckValveSnapshot;

export interface InstrumentSnapshot {
  tag: string;
  type: InstrumentType;
  description: string;
  node: string | null;
  high_node: string | null;
  low_node: string | null;
  unit_si: string;
  range_min_si: number;
  range_max_si: number;
  pv_si: number | null;
  value_si: number | null;
  status: InstrumentStatus;
  element?: string | null;
  distance_m?: number | null;
  chemical?: string | null;
  display_unit?: "ppm" | "vol%" | null;
  response?: { time_constant_s: number; update_interval_s: number; resolution_si: number };
}

export interface ChemicalSnapshot {
  id: string;
  name: string;
  status: string;
  pump_running: boolean;
  discharge_pressure_pa: number;
  static_pressure_pa: number;
  supply_pressure_pa: number;
  injection_node: string;
  injection_node_name: string;
  injection_flow_m3s: number;
  available_differential_pa: number;
  injection_point_pressure_pa: number;
  isolation_valve: string;
  control_valve: string;
  check_valve: string | null;
  pressure_transmitter: string | null;
  flow_transmitter: string | null;
  fully_mixed_concentration: number;
  cumulative_injected_m3: number;
  /** optional second route into the annulus service line */
  annulus_route?: {
    valve: string;
    check_valve: string;
    flow_transmitter: string | null;
    status: string;
    flow_m3s: number;
    cumulative_m3: number;
    junction_pressure_pa: number;
  } | null;
  /** further injection routes of this circuit into the production path */
  routes?: ChemicalRoute[];
  /** total flow into the production path over all routes [m3/s] */
  total_injection_m3s?: number;
  in_production_line_m3: number;
  exported_m3: number;
  front_distance_m: number;
  analysers: { tag: string; distance_from_injection_m: number | null; plug_flow_transit_s: number | null }[];
  color: string;
  display_unit: "ppm" | "vol%";
  target_min: number | null;
  target_max: number | null;
}

export interface ChemicalRoute {
  id: string;
  name: string;
  valve: string;
  check_valve: string;
  flow_transmitter: string | null;
  injection_node: string;
  injection_node_name: string;
  status: string;
  flow_m3s: number;
  cumulative_m3: number;
}

export interface TagAlias {
  tag: string;
  status: "verified" | "uncertain" | "placeholder" | "addition";
  note: string;
}

export interface HydraulicSupply {
  id: string;
  name: string;
  tag: string;
  available: boolean;
  pressure_pa: number;
  nominal_pressure_pa: number;
  minimum_operating_pressure_pa: number;
  actuator_pressure_pa: number;
  ok: boolean;
  valves: string[];
  fail_safe_close: string[];
}

export interface ControlHydraulics {
  supplies: HydraulicSupply[];
  headers: { id: string; name: string; tag: string; supply: string; scm: string; pressure_pa: number }[];
  selector_valves: { tag: string; name: string; header: string; opening_pct: number; commanded_pct: number; moving: boolean; stroke_time_s: number }[];
}

export type SchPoint = [number, number];

export interface SchComponent {
  id: string;
  type: string;
  model: string | null;
  models: string[];
  x: number;
  y: number;
  w: number;
  h: number;
  rotation: number;
  ports: Record<string, SchPoint>;
  flow_path: string | null;
  tap: SchPoint | null;
  label: { dx: number; dy: number; anchor: "start" | "middle" | "end" } | null;
  group: string | null;
  note: string;
}

export interface SchLine {
  id: string;
  cls: "production" | "annulus" | "service" | "chemical" | "methanol" | "downhole_chemical" | "hydraulic";
  points: SchPoint[];
  elements: string[];
  chemical: string | null;
  model?: string | null;
  from_ref: string | null;
  to_ref: string | null;
}

export interface SchematicLayout {
  id: string;
  title: string;
  subtitle: string;
  width: number;
  height: number;
  reference: { source: string; method: string; photo_origin_px: SchPoint; scale: number; notes: string[] };
  groups: { id: string; label: string; x: number; y: number; w: number; h: number; frame: boolean }[];
  lines: SchLine[];
  components: SchComponent[];
  connectors: { id: string; x: number; y: number; direction: "left" | "right" | "up" | "down"; label: string; model: string | null; label_side?: "left" | "right" }[];
  annotations: { type: string; x: number; y: number; w?: number; h?: number; text?: string; label?: string }[];
}

export interface PhaseRates {
  oil_sm3_d: number;
  gas_sm3_d: number;
  water_sm3_d: number;
  liquid_sm3_d: number;
  gor_sm3_sm3: number;
  water_cut: number;
  mass_kg_s: number;
  oil_mass_kg_s: number;
  gas_mass_kg_s: number;
  water_mass_kg_s: number;
}

export interface MultiphaseNode {
  node: string;
  name: string;
  p_pa: number;
  t_k: number;
  gor_sm3_sm3: number;
  water_cut: number;
  rs_sm3_sm3: number;
  bubble_point_pa: number;
  bo: number;
  bg: number;
  bw: number;
  z: number;
  rho_oil: number;
  rho_gas: number;
  rho_water: number;
  mu_oil_pas: number;
  mu_gas_pas: number;
  mu_water_pas: number;
  gvf: number;
  rho_mix_ns: number;
  free_gas_mass_fraction: number;
  q_oil_m3s: number;
  q_gas_m3s: number;
  q_water_m3s: number;
  mass_flow_kg_s: number;
}

export interface MultiphasePipe {
  element: string;
  segment?: number;
  node?: string;
  distance_m?: number;
  pattern: string;
  holdup: number;
  lambda_l: number;
  v_sl: number;
  v_sg: number;
  rho_s: number;
  rho_ns: number;
  friction_multiplier?: number;
  p_pa: number;
  t_k: number;
  gor?: number;
  water_cut?: number;
}

export interface ComponentBalance {
  in_kg: number;
  out_kg: number;
  inventory_kg: number;
  inventory_change_kg: number;
  residual_kg: number;
  relative_residual: number;
}

export interface MultiphaseReport {
  fluid_model: "black_oil";
  correlation: "beggs_brill" | "no_slip";
  dynamic_formulation: string;
  standard_conditions: { p_pa: number; t_k: number; note: string };
  reference_density_kg_m3: number;
  params: {
    name: string;
    oil_api: number;
    gas_specific_gravity: number;
    producing_gor_sm3_sm3: number;
    water_cut: number;
    water_salinity_wt_pct: number;
    oil_density_sc_kg_m3: number;
    gas_density_sc_kg_m3: number;
    water_density_sc_kg_m3: number;
    bubble_point_reservoir_pa: number;
  };
  rates_reservoir: PhaseRates;
  rates_arrival: PhaseRates;
  nodes: MultiphaseNode[];
  pipes: MultiphasePipe[];
  mass_balance: Record<"oil" | "gas" | "water", ComponentBalance> | null;
  validity: { correlation: string; in_range: boolean; notes: string[] }[];
  steady_reference: { ok: boolean; message: string; critical_choke: boolean; rates: PhaseRates | null } | null;
  limitations: string[];
}

export interface MPFMValues {
  oil_sm3_d: number;
  gas_sm3_d: number;
  water_sm3_d: number;
  liquid_sm3_d: number;
  oil_m3_d: number;
  gas_m3_d: number;
  water_m3_d: number;
  liquid_m3_d: number;
  mass_kg_s: number;
  mixture_density_kg_m3: number;
  water_cut: number;
  gor_sm3_sm3: number;
  gvf: number;
  lvf: number;
}

export interface MPFMSnapshot {
  tag: string;
  name?: string;
  quality: "GOOD" | "DEGRADED" | "BAD" | "NOT_READY" | "NOT_MODELLED";
  reason?: string;
  location_node?: string;
  principle?: string;
  geometry?: { inlet_diameter_m: number; beta: number; throat_diameter_m: number; discharge_coefficient: number };
  flags?: { severity: "info" | "warning" | "error"; code: string; message: string }[];
  measured?: MPFMValues | null;
  true?: MPFMValues | null;
  difference?: Partial<MPFMValues> | null;
  uncertainty_pct?: Record<string, number> | null;
  uncertainty_budget?: Record<string, Record<string, number>> | null;
  signals?: { p_pa: number | null; t_k: number | null; dp_pa: number | null; attenuation_low: number | null; attenuation_high: number | null;
    true_dp_pa: number | null; true_p_pa: number | null; true_t_k: number | null };
  phase_fractions?: { measured: Record<string, number>; raw: Record<string, number>; true_gas_void_fraction: number | null } | null;
  meter_slip_model?: string;
  meter_pvt?: { oil_api: number; gas_specific_gravity: number; water_salinity_wt_pct: number; producing_gor_sm3_sm3: number; water_cut: number };
  true_fluid?: { oil_api: number; gas_specific_gravity: number; water_salinity_wt_pct: number };
  faults?: { dp_offset_bar: number; dp_stuck: boolean; gamma_failed: boolean; pt_failed: boolean };
  calibration?: { last_s: number; days_since: number; interval_days: number; cd_actual: number; cd_drift_pct_per_year: number };
  envelope?: { dp_min_bar: number; dp_max_bar: number; gvf_max: number };
  reference_conditions?: string;
  sand_effect?: string;
}

export type IntegrityType = "pressure_hold" | "inflow" | "stroke";

export interface IntegrityTestSnapshot {
  id: number;
  type: IntegrityType;
  name: string;
  test_node: string | null;
  transmitter: string | null;
  valve: string | null;
  stabilisation_s: number;
  duration_s: number;
  max_change_bar: number;
  stroke_tolerance_pct: number;
  started_s: number;
  phase: "stabilising" | "holding" | "stroking" | "passed" | "failed" | "aborted";
  hold_start_s: number | null;
  p_hold_start_pa: number | null;
  p_now_pa: number | null;
  test_volume_m3: number;
  capacitance_m3_per_bar: number;
  trace: [number, number][];
  result: Record<string, number | boolean>;
  message: string;
}

export interface IntegrityPreset {
  id: string;
  name: string;
  type: IntegrityType;
  description: string;
  test_node: string | null;
  pressure_transmitter: string | null;
  valve: string | null;
  stabilisation_s: number;
  duration_s: number;
  max_change_bar: number;
  stroke_tolerance_pct: number;
}

export interface ClockInfo {
  elapsed_s: number;
  time_of_day_s: number;
  solver_step_s: number;
  fixed_step: boolean;
  achieved_speed: number | null;
  allowed_speeds: number[];
}

export interface Diagnostic {
  severity: "error" | "warning" | "info";
  code: string;
  message: string;
  location: string | null;
}

export interface LayoutPoint {
  x: number;
  y: number;
}

export interface LayoutAnnotation {
  type: "rect" | "line" | "text" | "body" | "cap" | "connector";
  direction?: "left" | "right" | "up" | "down";
  label_at?: "above" | "below" | "beyond";
  x?: number;
  y?: number;
  w?: number;
  h?: number;
  x1?: number;
  y1?: number;
  x2?: number;
  y2?: number;
  label?: string;
  label_position?: "top" | "bottom" | "top-right";
  text?: string;
}

export interface Layout {
  width: number;
  height: number;
  nodes: Record<string, LayoutPoint>;
  waypoints: Record<string, LayoutPoint[]>;
  instruments: Record<string, LayoutPoint>;
  annotations: LayoutAnnotation[];
  /** where along its line each valve symbol sits (0..1, default 0.5) */
  symbol_fraction?: Record<string, number>;
}

export interface SimulationState {
  scenario: ScenarioInfo;
  mode?: SimMode;
  status: SimStatus;
  time_s: number;
  time_scale: number;
  clock?: ClockInfo;
  briefing?: string[];
  steady_reference?: { status: string; q_m3s: number | null; node_pressure_pa: Record<string, number | null>; note: string };
  chemicals?: ChemicalSnapshot[];
  /** engineering tag -> display tag of the reference HMI (static) */
  tag_aliases?: Record<string, TagAlias>;
  /** engineering-workstation schematic layout (static), null if none */
  schematic?: SchematicLayout | null;
  control_hydraulics?: ControlHydraulics | null;
  fluid_model?: "single_phase" | "black_oil";
  /** fluid models this scenario supports (static) */
  fluid_models?: ("single_phase" | "black_oil")[];
  multiphase?: MultiphaseReport | null;
  mpfm?: MPFMSnapshot | null;
  sand_choke?: SandChokeResults | null;
  /** static: inputs entered for this session (null = scenario has none) */
  sand_choke_inputs?: SandChokeInputs | null;
  sand_choke_example_available?: boolean;
  erosion_materials?: ErosionMaterial[];
  chemical_config?: { id: string; name: string; color: string; display_unit: "ppm" | "vol%"; target_min: number | null; target_max: number | null }[];
  integrity?: { tests: IntegrityTestSnapshot[]; test_points: { transmitter: string; node: string; description: string }[] };
  integrity_presets?: IntegrityPreset[];
  annulus?: { temperature_k: number } | null;
  reservoir_model?: {
    radii_m: number[];
    kh_m3: number;
    permeability_m2: number;
    diffusivity_m2_s: number;
    pore_volume_m3: number;
    pressure_profile_pa: number[];
  } | null;
  transport_balance?: Record<string, { injected_m3: number; in_line_m3: number; exported_m3: number; to_reservoir_m3: number }>;
  model: Record<string, string>;
  boundary: {
    reservoir_pressure_pa: number;
    reservoir_temperature_k: number;
    productivity_index_si: number;
    downstream_pressure_pa: number;
    downstream_fluid_temperature_k: number;
  };
  fluid: {
    name: string;
    density_kg_m3: number;
    viscosity_pas: number;
    specific_heat_j_kgk: number;
    thermal_expansion_1_k: number;
    bubble_point_pressure_pa: number;
    compressibility_1_pa?: number;
  };
  hydraulics: {
    status: "solved" | "closed_in" | "failed";
    q_m3s: number | null;
    mass_flow_kg_s: number | null;
    driving_pressure_pa: number | null;
    residual_pa: number;
    iterations: number;
    message: string;
    reservoir_inflow_m3s?: number;
    max_pressure_rate_pa_s?: number;
    process_settling?: string | null;
  };
  nodes: NodeSnapshot[];
  elements: ElementSnapshot[];
  instruments: InstrumentSnapshot[];
  diagnostics: Diagnostic[];
  last_event_id: number;
  last_sample_seq: number;
  layout?: Layout;
  training_rules?: { max_opening_differential_bar: number | null };
}

export interface SimEvent {
  id: number;
  sim_time_s: number;
  wall_time: number;
  category: string;
  message: string;
  component: string | null;
  severity: "info" | "warning" | "error";
  detail: string | null;
}

/** Trend sample: keys "t", "q", "inst:<TAG>", "ref:<TAG>" (steady-state reference), "pos:<TAG>", "cmd:<TAG>", "seq". */
export type Sample = Record<string, number | null>;

// ------------------------------------------------------------------ training
export interface TrainingOption {
  id: string;
  text: string;
}

export interface TrainingResponse {
  choice: string;
  correct?: boolean;
  correct_option?: string | null;
  explanation?: string;
}

export interface TrainingReview {
  text: string;
  table?: { columns: string[]; rows: (string | number)[][] };
}

export interface PredictionResult {
  step_id: string;
  title: string;
  choice: string;
  choice_text: string;
  correct_option: string | null;
  correct_text: string | null;
  correct: boolean | null;
  explanation: string | null;
}

export interface ExerciseSummary {
  id: string;
  number: number;
  title: string;
  scenario_id: string;
  objectives: string[];
  initial_configuration: string[];
  instructions: string[];
  expected_observations: string[];
  step_count: number;
}

export interface TrainingState {
  exercise: ExerciseSummary;
  index: number;
  steps: { id: string; kind: string; title: string; status: "complete" | "current" | "pending" }[];
  current: {
    id: string;
    kind: "info" | "task" | "prediction" | "question" | "review" | "summary";
    title: string;
    body: string;
    complete: boolean;
    options?: TrainingOption[];
    response?: TrainingResponse | null;
    hint?: string | null;
    review?: TrainingReview;
  };
  observations: Record<string, Record<string, unknown>>;
  score: {
    questions_correct: number;
    questions_total: number;
    predictions_correct: number;
    predictions_total: number;
    predictions_resolved: number;
  };
  finished: boolean;
  summary?: {
    predictions: PredictionResult[];
    questions: { step_id: string; title: string; choice?: string; correct?: boolean; correct_option?: string; explanation?: string }[];
    duration_s: number;
  };
}

export interface SessionPayload {
  session_id: string;
  state: SimulationState;
  training: TrainingState | null;
}

export interface WsMessage extends SessionPayload {
  type: "init" | "update";
  events: SimEvent[];
  samples: Sample[];
}
