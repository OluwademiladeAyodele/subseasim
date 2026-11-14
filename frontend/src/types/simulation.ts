/**
 * Types mirroring the backend API (app/simulation/engine.py snapshot).
 * All physical values are SI: pressure Pa ABSOLUTE, differential Pa,
 * temperature K, flow m3/s. Conversion for display happens in lib/units.ts.
 */

export type SimStatus = "ready" | "running" | "paused";
export type NodeState = "flowing" | "static_reservoir" | "static_boundary" | "trapped";
export type ElementState = "flowing" | "no_flow" | "closed";
export type ElementKind = "inflow" | "pipe" | "valve" | "choke";
export type ValveCommand = "open" | "close" | "set_position";
export type InstrumentType = "pressure" | "temperature" | "flow" | "differential_pressure";
export type InstrumentStatus = "GOOD" | "OUT_OF_RANGE_HIGH" | "OUT_OF_RANGE_LOW" | "UNDETERMINED" | "BAD";

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
}

interface ElementBase {
  id: string;
  name: string;
  kind: ElementKind;
  from: string;
  to: string;
  state: ElementState;
  dp_pa: number | null;
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
}

export type ElementSnapshot = InflowSnapshot | PipeSnapshot | RestrictionSnapshot;

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
  type: "rect" | "line" | "text";
  x?: number;
  y?: number;
  w?: number;
  h?: number;
  x1?: number;
  y1?: number;
  x2?: number;
  y2?: number;
  label?: string;
  label_position?: "top" | "bottom";
  text?: string;
}

export interface Layout {
  width: number;
  height: number;
  nodes: Record<string, LayoutPoint>;
  waypoints: Record<string, LayoutPoint[]>;
  instruments: Record<string, LayoutPoint>;
  annotations: LayoutAnnotation[];
}

export interface SimulationState {
  scenario: ScenarioInfo;
  status: SimStatus;
  time_s: number;
  time_scale: number;
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
  };
  hydraulics: {
    status: "solved" | "closed_in" | "failed";
    q_m3s: number | null;
    mass_flow_kg_s: number | null;
    driving_pressure_pa: number | null;
    residual_pa: number;
    iterations: number;
    message: string;
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

/** Trend sample: keys "t", "q", "inst:<TAG>", "pos:<TAG>", "cmd:<TAG>", "seq". */
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
