/** Scenario comparison (backend app/studies/comparison.py). */

export interface Variant {
  label: string;
  choke_pct?: number | null;
  reservoir_pressure_bara?: number | null;
  downstream_pressure_bara?: number | null;
  water_cut?: number | null;
  gor_sm3_sm3?: number | null;
  sand_rate_kg_d?: number | null;
  d50_um?: number | null;
  trim_material?: string | null;
}

export interface CaseMetrics {
  choke_pct: number | null;
  reservoir_pressure_bara: number | null;
  water_cut: number | null;
  gor_sm3_sm3: number | null;
  oil_sm3_d: number | null;
  gas_sm3_d: number | null;
  water_sm3_d: number | null;
  choke_p1_bara: number | null;
  choke_p2_bara: number | null;
  choke_dp_bar: number | null;
  drawdown_bar: number | null;
  critical_drawdown_bar: number | null;
  risk_index: number | null;
  sand_produced_kg_d: number | null;
  sand_at_choke_kg_d: number | null;
  jet_velocity_m_s: number | null;
  hole_rate_mm_y: number | null;
  first_limit: string | null;
  life_p10_days: number | null;
  life_p50_days: number | null;
  life_p90_days: number | null;
  governing: string | null;
  governing_consumed: number | null;
  service_days: number | null;
  health: string | null;
  cavitation_risk: string | null;
  cavitation_regime: string | null;
  api14e_max_ratio: number | null;
  confidence: string | null;
}

export interface StudyCase {
  id: string;
  label: string;
  changes: string[];
  wear_start: string;
  now: CaseMetrics;
  after_horizon: CaseMetrics;
}

export interface StudyResult {
  message: string;
  horizon_days: number;
  scenario_id: string;
  sim_time_s: number;
  cases: StudyCase[];
  method: string;
  limitations: string[];
}
