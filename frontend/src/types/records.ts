/** Saved simulation records (backend app/storage). */

export interface RecordSummary {
  id: string;
  created_at: string;
  label: string;
  notes: string | null;
  scenario_id: string;
  scenario_name: string | null;
  session_id: string | null;
  sim_time_s: number;
  app_version: string;
  validation_status: string;
  health_category: string | null;
  has_comparison: number;
}

export interface ModelEntry {
  version: string;
  status: string;
  method: string;
  validation: string;
  doc: string;
}

export interface SimulationRecord {
  id: string;
  created_at: string;
  label: string;
  notes: string | null;
  schema_version: number;
  header: { scenario_id: string; scenario_name: string; data_classification: string; session_id: string | null; sim_time_s: number; mode: string; fluid_model: string; status: string; app_version: string };
  inputs: {
    boundary: Record<string, number>;
    fluid_model: string;
    black_oil: Record<string, unknown> | null;
    valves: { tag: string; kind: string; position_pct: number | null; commanded_pct: number | null; state: string | null; available: boolean | null }[];
    chemicals: { id: string; name: string; status: string; injection_m3s: number | null }[];
    sand_choke: unknown;
  };
  results: {
    instruments: { tag: string; type: string; description: string; value_si: number | null; unit_si: string; status: string }[];
    rates_arrival: { oil_sm3_d: number; gas_sm3_d: number; water_sm3_d: number } | null;
    sand: { at_choke_kg_d: number | null } | null;
    choke_health: { category: string } | null;
    recommendation: { title: string } | null;
    cavitation: { risk?: string } | null;
    [k: string]: unknown;
  };
  provenance: Record<string, string>;
  methods: Record<string, ModelEntry>;
  assumptions: string[];
  uncertainty: Record<string, unknown>;
  comparison?: unknown;
  validation: { overall: string; model_status_range: string | null; erosion_confidence: string | null; data_classification: string; statement: string };
}
