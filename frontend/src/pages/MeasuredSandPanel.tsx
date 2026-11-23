/**
 * Measured sand history (Sand & choke inputs page): CSV import / export,
 * manual records and the abnormal-increase review trigger. Validation and
 * unit conversion happen in the backend; an invalid CSV is rejected whole,
 * with an error per line.
 */
import { Download, FileUp, Plus, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button, Input, Panel, Select } from "@/components/ui/primitives";
import type { MeasuredUnit, SandChokeInputs, SandMeasurement } from "@/types/sand";

const UNITS: [MeasuredUnit, string][] = [
  ["kg_d", "kg/d"], ["kg_h", "kg/h"], ["g_s", "g/s"], ["pptb", "pptb"],
  ["ppm_mass_liquid", "ppm mass (liquid)"], ["ppm_mass_total", "ppm mass (total)"], ["ppm_vol_liquid", "ppm vol (liquid)"],
];
const METHODS: [SandMeasurement["method"], string][] = [
  ["sand_trap", "Sand trap"], ["acoustic_detector", "Acoustic detector"], ["intrusive_probe", "Intrusive probe"],
  ["well_test_sample", "Well-test sample"], ["other", "Other"],
];
const COLS = ["timestamp", "value", "unit", "method", "uncertainty_pct", "liquid_rate_sm3_d", "water_cut", "d10_um", "d50_um", "d90_um", "note"] as const;

export function toCsv(rows: SandMeasurement[]): string {
  const esc = (v: unknown) => (v == null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
  return [COLS.join(","), ...[...rows].sort((a, b) => a.timestamp.localeCompare(b.timestamp)).map((r) => COLS.map((c) => esc(r[c])).join(","))].join("\n") + "\n";
}

type Draft = SandChokeInputs;

function readText(f: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result ?? ""));
    r.onerror = () => reject(r.error);
    r.readAsText(f);
  });
}

export function MeasuredSandPanel({ d, setD, dirty, onImport }: { d: Draft; setD: (d: Draft) => void; dirty: boolean; onImport: (csv: string, replace: boolean) => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [replace, setReplace] = useState(false);
  const rows = d.sand.measurements;
  const setRows = (m: SandMeasurement[]) => setD({ ...d, sand: { ...d.sand, measurements: m } });
  const upd = (i: number, patch: Partial<SandMeasurement>) => setRows(rows.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const exportCsv = () => {
    const url = URL.createObjectURL(new Blob([toCsv(rows)], { type: "text/csv" }));
    const el = document.createElement("a");
    el.href = url;
    el.download = "sand_measurements.csv";
    el.click();
    URL.revokeObjectURL(url);
  };
  return (
    <Panel title="Measured sand history" className="xl:col-span-2"
      subtitle={d.sand.mode === "measured" ? "Measured mode: the LATEST record sets the sand rate used by the erosion model." : "Predictive mode: the history is trended and checked, but the model uses the prediction."}>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Button size="xs" disabled={dirty} onClick={() => fileRef.current?.click()} data-testid="sand-csv-import"
          title={dirty ? "Save or discard the other changes first" : "Columns: timestamp, value, unit, method, uncertainty_pct, liquid_rate_sm3_d, water_cut, d10_um, d50_um, d90_um, note"}>
          <FileUp size={13} className="mr-1" />Import CSV
        </Button>
        <label className="flex items-center gap-1 text-[12px] text-muted">
          <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} aria-label="Replace existing records" />replace existing records
        </label>
        <Button size="xs" onClick={exportCsv} disabled={!rows.length}><Download size={13} className="mr-1" />Export CSV</Button>
        <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" data-testid="sand-csv-file"
          onChange={async (e) => {
            const f = e.target.files?.[0];
            if (f) onImport(await readText(f), replace);
            e.target.value = "";
          }} />
        {dirty && <span className="text-[12px] text-warn">save the other changes before importing</span>}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-[12.5px]" data-testid="measurement-table">
          <thead className="text-left text-muted">
            <tr>{["Timestamp (ISO)", "Value", "Unit", "Method", "±1σ %", "Liquid Sm³/d", "WC", "Note", ""].map((h) => <th key={h} className="pr-2">{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="py-0.5 pr-2"><Input aria-label={`measurement ${i + 1} timestamp`} value={r.timestamp} onChange={(e) => upd(i, { timestamp: e.target.value })} /></td>
                <td className="py-0.5 pr-2"><NumCell label={`measurement ${i + 1} value`} value={r.value} onChange={(v) => v != null && upd(i, { value: v })} /></td>
                <td className="py-0.5 pr-2">
                  <Select aria-label={`measurement ${i + 1} unit`} value={r.unit} onChange={(e) => upd(i, { unit: e.target.value as MeasuredUnit })}>
                    {UNITS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  </Select>
                </td>
                <td className="py-0.5 pr-2">
                  <Select aria-label={`measurement ${i + 1} method`} value={r.method} onChange={(e) => upd(i, { method: e.target.value as SandMeasurement["method"] })}>
                    {METHODS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  </Select>
                </td>
                {(["uncertainty_pct", "liquid_rate_sm3_d", "water_cut"] as const).map((k) => (
                  <td key={k} className="py-0.5 pr-2">
                    <NumCell label={`measurement ${i + 1} ${k}`} value={r[k]} onChange={(v) => upd(i, { [k]: v })} />
                  </td>
                ))}
                <td className="py-0.5 pr-2"><Input aria-label={`measurement ${i + 1} note`} value={r.note ?? ""} onChange={(e) => upd(i, { note: e.target.value || null })} /></td>
                <td><Button size="xs" variant="ghost" aria-label={`remove measurement ${i + 1}`} onClick={() => setRows(rows.filter((_, j) => j !== i))}><Trash2 size={13} /></Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Button size="xs" className="mt-1" onClick={() => setRows([...rows, { timestamp: new Date().toISOString().slice(0, 10), value: 0, unit: "kg_d", method: "sand_trap", uncertainty_pct: null, liquid_rate_sm3_d: null, water_cut: null, d10_um: null, d50_um: null, d90_um: null, note: null }])}>
        <Plus size={13} className="mr-1" />Add record
      </Button>
      <p className="mt-1 text-[12px] text-dim">Concentration units (pptb, ppm) need the liquid rate (and the water cut for mass ppm) to be converted to kg/d for the trend.</p>
      <h3 className="mb-1 mt-3 t-eyebrow">Abnormal-increase review trigger (configurable, not a safety limit)</h3>
      <div className="grid gap-x-6 md:grid-cols-3">
        <TriggerField label="Ratio to baseline median" value={d.sand.abnormal_increase_ratio} onChange={(v) => v != null && v > 1 && setD({ ...d, sand: { ...d.sand, abnormal_increase_ratio: v } })} testId="in-abnormal-ratio" />
        <TriggerField label="Baseline records" value={d.sand.abnormal_baseline_count} onChange={(v) => v != null && v >= 1 && setD({ ...d, sand: { ...d.sand, abnormal_baseline_count: Math.round(v) } })} />
        <TriggerField label="Minimum increase (kg/d)" value={d.sand.abnormal_min_increase_kg_d} onChange={(v) => setD({ ...d, sand: { ...d.sand, abnormal_min_increase_kg_d: v } })} />
      </div>
    </Panel>
  );
}

/** Numeric table cell: keeps the typed text (empty, "2.") and reports only valid numbers (empty = null). */
function NumCell({ label, value, onChange }: { label: string; value: number | null; onChange: (v: number | null) => void }) {
  const [text, setText] = useState(value == null ? "" : String(value));
  // resync when the value changes from outside (row removed, CSV imported), not while typing "2."
  useEffect(() => {
    const parsed = text.trim() === "" ? null : Number(text);
    if (parsed !== value) setText(value == null ? "" : String(value));
  }, [value]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Input aria-label={label} inputMode="decimal" value={text}
      onChange={(e) => {
        setText(e.target.value);
        const t = e.target.value.trim();
        if (t === "") onChange(null);
        else if (Number.isFinite(Number(t))) onChange(Number(t));
      }} />
  );
}

function TriggerField({ label, value, onChange, testId }: { label: string; value: number | null; onChange: (v: number | null) => void; testId?: string }) {
  const [text, setText] = useState(value == null ? "" : String(value));
  return (
    <label className="flex flex-col gap-0.5 py-0.5">
      <span className="text-[12px] text-muted">{label}</span>
      <Input aria-label={label} data-testid={testId} inputMode="decimal" value={text}
        onChange={(e) => {
          setText(e.target.value);
          const t = e.target.value.trim();
          if (t === "") onChange(null);
          else if (Number.isFinite(Number(t))) onChange(Number(t));
        }} />
    </label>
  );
}
