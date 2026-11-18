/**
 * Scenario comparison: alternative operating choices calculated with the
 * same models as the live session (steady twins, background job), shown
 * side by side with the difference from the current operation. A completed
 * study can be saved with a simulation record and printed as a report.
 */
import { FileText, GitCompare, Plus, Save, Trash2 } from "lucide-react";
import { useState } from "react";

import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { JobProgress } from "@/components/JobProgress";
import { Badge, Button, Input, Panel, Select } from "@/components/ui/primitives";
import { fmt } from "@/lib/units";
import { api } from "@/services/api";
import type { CaseMetrics, StudyCase, StudyResult, Variant } from "@/types/comparison";
import { type Job, jobActive } from "@/types/jobs";

type NumKey = "choke_pct" | "reservoir_pressure_bara" | "downstream_pressure_bara" | "water_cut" | "gor_sm3_sm3" | "sand_rate_kg_d" | "d50_um";
const FIELDS: { k: NumKey; label: string; unit: string; scale?: number }[] = [
  { k: "choke_pct", label: "Choke", unit: "%" },
  { k: "reservoir_pressure_bara", label: "Reservoir P", unit: "bara" },
  { k: "downstream_pressure_bara", label: "Manifold P", unit: "bara" },
  { k: "water_cut", label: "Water cut", unit: "%", scale: 100 },
  { k: "gor_sm3_sm3", label: "GOR", unit: "Sm³/Sm³" },
  { k: "sand_rate_kg_d", label: "Sand rate", unit: "kg/d" },
  { k: "d50_um", label: "D50", unit: "µm" },
];

// Rows of the result table: label, unit, getter, decimals, which direction is BETTER (for the delta colour)
type Row = { label: string; get: (c: StudyCase) => number | string | null; d?: number; better?: "up" | "down" };
const N = (k: keyof CaseMetrics) => (c: StudyCase) => c.now[k] as number | null;
const F = (k: keyof CaseMetrics) => (c: StudyCase) => c.after_horizon[k] as number | null;
const ROWS: { group: string; rows: Row[] }[] = [
  { group: "Operating point", rows: [
    { label: "Choke opening %", get: N("choke_pct"), d: 1 },
    { label: "Reservoir pressure bara", get: N("reservoir_pressure_bara"), d: 1 },
    { label: "Water cut %", get: (c) => (c.now.water_cut == null ? null : c.now.water_cut * 100), d: 1 },
    { label: "Choke ΔP bar", get: N("choke_dp_bar"), d: 1 },
  ] },
  { group: "Production (manifold, standard conditions)", rows: [
    { label: "Oil Sm³/d", get: N("oil_sm3_d"), d: 0, better: "up" },
    { label: "Gas Sm³/d", get: N("gas_sm3_d"), d: 0 },
    { label: "Water Sm³/d", get: N("water_sm3_d"), d: 0, better: "down" },
  ] },
  { group: "Sanding", rows: [
    { label: "Drawdown bar", get: N("drawdown_bar"), d: 1 },
    { label: "Sanding risk index (onset = 1)", get: N("risk_index"), d: 2, better: "down" },
    { label: "Sand at the choke kg/d", get: N("sand_at_choke_kg_d"), d: 2, better: "down" },
  ] },
  { group: "Choke erosion", rows: [
    { label: "Jet velocity m/s", get: N("jet_velocity_m_s"), d: 1, better: "down" },
    { label: "Cage-hole wear mm/yr", get: N("hole_rate_mm_y"), d: 3, better: "down" },
    { label: "Wear starts from", get: (c) => c.wear_start },
    { label: "Health after horizon", get: (c) => c.after_horizon.health },
    { label: "Governing allowance used after horizon %", get: (c) => (c.after_horizon.governing_consumed == null ? null : c.after_horizon.governing_consumed * 100), d: 1, better: "down" },
    { label: "Remaining life P50 after horizon, days", get: F("life_p50_days"), d: 0, better: "up" },
    { label: "Remaining life P10 – P90, days", get: (c) => (c.after_horizon.life_p10_days == null ? null : `${fmt(c.after_horizon.life_p10_days, 0)} – ${fmt(c.after_horizon.life_p90_days, 0)}`) },
    { label: "First limit", get: (c) => c.after_horizon.first_limit },
  ] },
  { group: "Screening", rows: [
    { label: "Cavitation", get: (c) => c.now.cavitation_risk },
    { label: "API RP 14E max u/Ve", get: N("api14e_max_ratio"), d: 2, better: "down" },
  ] },
];

function Delta({ v, base, d = 1, better }: { v: number; base: number | null; d?: number; better?: "up" | "down" }) {
  if (base == null || !Number.isFinite(base)) return null;
  const diff = v - base;
  if (Math.abs(diff) < 10 ** -(d + 1)) return null;
  const good = better ? (better === "up" ? diff > 0 : diff < 0) : null;
  const pct = base !== 0 ? ` (${diff > 0 ? "+" : ""}${fmt((diff / Math.abs(base)) * 100, 0)} %)` : "";
  return (
    <div className={`text-[11px] ${good == null ? "text-dim" : good ? "text-ok" : "text-bad"}`}>
      {diff > 0 ? "+" : ""}{fmt(diff, d)}{pct}
    </div>
  );
}

export function ComparisonPage() {
  const { state, actions, sim } = useWorkstation();
  // each case keeps a stable id so the (uncontrolled) number cells stay with their row when a case is removed
  const [rows, setRows] = useState<{ id: number; v: Variant }[]>([{ id: 1, v: { label: "Choke 45 %", choke_pct: 45 } }, { id: 2, v: { label: "Choke 60 %", choke_pct: 60 } }]);
  const variants = rows.map((r) => r.v);
  const [horizon, setHorizon] = useState("365");
  const [job, setJob] = useState<Job | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<{ jobId: string; r: StudyResult } | null>(null);
  const [recLabel, setRecLabel] = useState("");
  const [saved, setSaved] = useState<{ id: string; label: string } | null>(null);
  const mats = (state.erosion_materials ?? []).map((m) => [m.key, m.name] as [string, string]);
  const h = Number(horizon);

  const upd = (i: number, p: Partial<Variant>) => setRows(rows.map((r, j) => (j === i ? { ...r, v: { ...r.v, ...p } } : r)));
  const run = async () => {
    setSaved(null);
    const clean = variants.map((v) => Object.fromEntries(Object.entries(v).filter(([, x]) => x !== null && x !== undefined && x !== "")) as Variant);
    const j = await actions.startJob("scenario_comparison", { variants: clean, horizon_days: h });
    if (typeof j === "string") setErr(j);
    else {
      setErr(null);
      setJob(j);
    }
  };
  const save = async () => {
    if (!sim.sessionId || !result || !recLabel.trim()) return;
    try {
      const r = await api.saveRecord(sim.sessionId, recLabel.trim(), null, result.jobId);
      setSaved({ id: r.id, label: r.label });
      setErr(null);
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <PageBody intro="Compare operating options before you act. Each case is solved with the same models as this session (a steady copy carrying its current state and choke wear); the live simulation is not changed.">
      <div className="grid items-start gap-4">
        <Panel title="Cases to compare" icon={<GitCompare size={16} />} subtitle={`Base: current operation of ${state.scenario.name}. Empty fields keep the current value.`} bodyClassName="overflow-x-auto">
          <table className="w-full min-w-[1000px] text-[12.5px]" data-testid="variant-table">
            <thead className="text-left text-muted">
              <tr>
                <th className="pr-2">Label</th>
                {FIELDS.map((f) => <th key={f.k} className="pr-2">{f.label} <span className="font-normal text-dim">{f.unit}</span></th>)}
                <th className="pr-2">Trim material (new trim)</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map(({ id, v }, i) => (
                <tr key={id}>
                  <td className="py-0.5 pr-2"><Input aria-label={`case ${i + 1} label`} value={v.label} maxLength={60} onChange={(e) => upd(i, { label: e.target.value })} /></td>
                  {FIELDS.map((f) => (
                    <td key={f.k} className="py-0.5 pr-2">
                      <Input aria-label={`case ${i + 1} ${f.label}`} inputMode="decimal" className="w-24"
                        defaultValue={v[f.k] == null ? "" : String((v[f.k] as number) * (f.scale ?? 1))}
                        onChange={(e) => {
                          const t = e.target.value.trim();
                          const n = Number(t);
                          upd(i, { [f.k]: t === "" || !Number.isFinite(n) ? null : n / (f.scale ?? 1) });
                        }} />
                    </td>
                  ))}
                  <td className="py-0.5 pr-2">
                    <Select aria-label={`case ${i + 1} trim material`} value={v.trim_material ?? ""} onChange={(e) => upd(i, { trim_material: e.target.value || null })}>
                      <option value="">unchanged</option>
                      {mats.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                    </Select>
                  </td>
                  <td><Button size="xs" variant="ghost" aria-label={`remove case ${i + 1}`} onClick={() => setRows(rows.filter((_, j) => j !== i))}><Trash2 size={13} /></Button></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Button size="xs" disabled={variants.length >= 6} onClick={() => setRows([...rows, { id: Math.max(0, ...rows.map((r) => r.id)) + 1, v: { label: `Case ${rows.length + 1}` } }])}><Plus size={13} className="mr-1" />Add case</Button>
            <span className="text-[12px] text-dim">up to 6 cases</span>
            <span className="flex-1" />
            <label className="flex items-center gap-2 text-[12.5px] text-muted">Wear horizon
              <Input aria-label="Wear horizon days" inputMode="decimal" className="w-20" value={horizon} onChange={(e) => setHorizon(e.target.value)} /> days
            </label>
            <Button variant="primary" size="sm" data-testid="run-comparison" disabled={!variants.length || !(h >= 0 && h <= 3650) || jobActive(job) || variants.some((v) => !v.label.trim())} onClick={run}>
              Run comparison
            </Button>
          </div>
          {err && <p className="mt-2 text-[12.5px] text-bad" data-testid="comparison-error">{err}</p>}
          {job && <JobProgress job={job} onFinished={(j) => { if (j.state === "completed" && j.result) setResult({ jobId: j.id, r: j.result as unknown as StudyResult }); }} />}
        </Panel>

        {result && <Results r={result.r} />}

        {result && (
          <Panel title="Save and report" icon={<FileText size={16} />}>
            <div className="flex flex-wrap items-center gap-2">
              <Input aria-label="Comparison record label" className="w-80" placeholder="e.g. Choke options before the next well test" value={recLabel} onChange={(e) => setRecLabel(e.target.value)} />
              <Button size="sm" disabled={!recLabel.trim()} onClick={save} data-testid="save-comparison"><Save size={14} className="mr-1" />Save record with this comparison</Button>
              {saved && (
                <a className="text-[13px] font-semibold text-accent hover:underline" href={`/api/records/${saved.id}/report`} target="_blank" rel="noreferrer" data-testid="comparison-report-link">
                  Open the engineering report
                </a>
              )}
            </div>
            <p className="mt-1 text-[12px] text-dim">The record stores the current session assessment together with this comparison; the report prints both.</p>
          </Panel>
        )}
      </div>
    </PageBody>
  );
}

function Results({ r }: { r: StudyResult }) {
  const base = r.cases[0];
  return (
    <Panel title={`Results: ${r.cases.length} cases, ${fmt(r.horizon_days, 0)}-day wear horizon`} bodyClassName="overflow-x-auto" right={<Badge tone="info">steady operating points</Badge>}>
      <table className="w-full min-w-[760px] text-[12.5px]" data-testid="comparison-results">
        <thead>
          <tr className="text-left">
            <th className="py-1 pr-3 font-medium text-dim">Quantity</th>
            {r.cases.map((c) => (
              <th key={c.id} className="py-1 pr-3 text-right align-bottom">
                <div className="font-semibold">{c.label}</div>
                <div className="text-[11px] font-normal text-dim">{c.changes.join(" · ") || "current operation"}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map((g) => [
            <tr key={g.group}><td colSpan={r.cases.length + 1} className="pt-3 pb-1 t-eyebrow">{g.group}</td></tr>,
            ...g.rows.map((row) => (
              <tr key={row.label} className="border-t border-line">
                <td className="py-1 pr-3 text-muted">{row.label}</td>
                {r.cases.map((c, i) => {
                  const v = row.get(c);
                  const b = row.get(base);
                  return (
                    <td key={c.id} className="num py-1 pr-3 text-right" data-testid={`cell-${c.id}-${row.label}`}>
                      {v == null ? "—" : typeof v === "number" ? fmt(v, row.d ?? 1) : v}
                      {i > 0 && typeof v === "number" && <Delta v={v} base={typeof b === "number" ? b : null} d={row.d} better={row.better} />}
                    </td>
                  );
                })}
              </tr>
            )),
          ])}
        </tbody>
      </table>
      <p className="mt-2 text-[12px] text-dim">{r.method}</p>
      <ul className="mt-1 list-disc pl-5 text-[12px] text-dim">{r.limitations.map((x) => <li key={x}>{x}</li>)}</ul>
    </Panel>
  );
}
