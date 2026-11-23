/** Surrogate models (backend app/surrogates). */

export const SURROGATE_INPUTS: { key: string; label: string; unit: string; min: number; max: number; scale?: number }[] = [
  { key: "choke_pct", label: "Choke opening", unit: "%", min: 20, max: 70 },
  { key: "reservoir_pressure_bara", label: "Reservoir pressure", unit: "bara", min: 300, max: 400 },
  { key: "downstream_pressure_bara", label: "Manifold pressure", unit: "bara", min: 40, max: 80 },
  { key: "water_cut", label: "Water cut", unit: "%", min: 10, max: 60, scale: 100 },
  { key: "gor_sm3_sm3", label: "GOR", unit: "Sm³/Sm³", min: 80, max: 200 },
  { key: "sand_rate_kg_d", label: "Sand rate", unit: "kg/d", min: 0, max: 30 },
  { key: "d50_um", label: "Median grain size D50", unit: "µm", min: 80, max: 300 },
];

export const SURROGATE_OUTPUTS: { key: string; label: string; unit: string }[] = [
  { key: "oil_sm3_d", label: "Oil rate", unit: "Sm³/d" },
  { key: "gas_sm3_d", label: "Gas rate", unit: "Sm³/d" },
  { key: "water_sm3_d", label: "Water rate", unit: "Sm³/d" },
  { key: "choke_dp_bar", label: "Choke differential", unit: "bar" },
  { key: "drawdown_bar", label: "Drawdown", unit: "bar" },
  { key: "risk_index", label: "Sanding risk index", unit: "-" },
  { key: "sand_at_choke_kg_d", label: "Sand at the choke", unit: "kg/d" },
  { key: "jet_velocity_m_s", label: "Choke jet velocity", unit: "m/s" },
  { key: "hole_rate_mm_y", label: "Cage-hole wear rate", unit: "mm/yr" },
];

export interface SurrogateSummary {
  id: string;
  created_at: string;
  name: string;
  method: "gp" | "poly";
  scenario_id: string | null;
  n_cases: number;
  sources: Record<string, number>;
}

export interface OutputValidation {
  loo_rmse: number;
  loo_r2: number | null;
  loo_coverage_95: number;
  y_min: number;
  y_max: number;
  loo_points: [number, number][];
}

export interface SurrogateCard {
  id: string;
  name: string;
  method: "gp" | "poly";
  model_version: string;
  scenario_id: string | null;
  created_at: string;
  inputs: { key: string; label: string; unit: string; min: number; max: number }[];
  outputs: { key: string; label: string; unit: string }[];
  n_cases: number;
  sources: Record<string, number>;
  status: string;
  validation: Record<string, OutputValidation>;
  typical_spacing: number;
  notes: string[];
  limitations: string[];
}

export interface Envelope {
  inside: boolean;
  outside_inputs: { input: string; value: number; min: number; max: number }[];
  nearest_case_distance: number;
  typical_spacing: number;
  sparse: boolean;
  message: string;
}

export interface Prediction {
  inputs: Record<string, number>;
  outputs: Record<string, { mean: number; std: number; p2_5: number; p97_5: number; label: string; unit: string }>;
  envelope: Envelope;
  status: string;
  trained_on: Record<string, number>;
}

export interface SimulatorCheck {
  inputs: Record<string, number>;
  envelope: Envelope;
  outputs: Record<string, { surrogate: number; std: number; simulator: number | null; difference: number | null; within_95: boolean | null }>;
  simulator: string;
}
