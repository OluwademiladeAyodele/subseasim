/**
 * Simulation records: save the current assessment (inputs, results,
 * methods, provenance, uncertainty, validation) to the server database,
 * browse, inspect, export as JSON and delete. Records are immutable.
 */
import { Download, FileText, Save, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { Badge, Button, Input, Panel } from "@/components/ui/primitives";
import { fmt } from "@/lib/units";
import { api } from "@/services/api";
import type { RecordSummary, SimulationRecord } from "@/types/records";

function simTime(s: number) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h >= 24 ? `${Math.floor(h / 24)} d ${h % 24} h` : `${h} h ${String(m).padStart(2, "0")} min`;
}

export function RecordsPage() {
  const { sim, state } = useWorkstation();
  const [rows, setRows] = useState<RecordSummary[]>([]);
  const [sel, setSel] = useState<SimulationRecord | null>(null);
  const [label, setLabel] = useState("");
  const [notes, setNotes] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => api.listRecords().then(setRows).catch((e: Error) => setErr(e.message)), []);
  useEffect(() => { refresh(); }, [refresh]);

  const save = async () => {
    if (!sim.sessionId || !label.trim()) return;
    setBusy(true);
    try {
      const r = await api.saveRecord(sim.sessionId, label.trim(), notes.trim() || null);
      setLabel("");
      setNotes("");
      setErr(null);
      await refresh();
      setSel(await api.getRecord(r.id));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const open = async (id: string) => {
    try { setSel(await api.getRecord(id)); } catch (e) { setErr((e as Error).message); }
  };
  const remove = async (id: string) => {
    try {
      await api.deleteRecord(id);
      if (sel?.id === id) setSel(null);
      await refresh();
    } catch (e) { setErr((e as Error).message); }
  };

  return (
    <PageBody intro="Save the current assessment with its inputs, results, calculation methods and model versions, data provenance, uncertainty and validation status. Records are stored on the server and cannot be edited; save a new one after a change.">
      {err && <p className="mb-3 text-[13px] text-bad" data-testid="records-error">{err}</p>}
      <div className="grid items-start gap-4 xl:grid-cols-3">
        <Panel title="Save the current assessment" icon={<Save size={16} />}>
          <label className="flex flex-col gap-1 py-0.5">
            <span className="text-[12.5px] text-muted">Label</span>
            <Input aria-label="Record label" value={label} maxLength={120} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Choke 40 % after water-cut change" />
          </label>
          <label className="flex flex-col gap-1 py-0.5">
            <span className="text-[12.5px] text-muted">Notes</span>
            <Input aria-label="Record notes" value={notes} maxLength={2000} onChange={(e) => setNotes(e.target.value)} />
          </label>
          <p className="mt-1 text-[12px] text-dim">{state.scenario.name} · simulated time {simTime(state.time_s)} · {state.status}</p>
          <Button className="mt-2" variant="primary" size="sm" disabled={!label.trim() || busy || !sim.sessionId} onClick={save} data-testid="record-save">
            <Save size={14} className="mr-1" />Save record
          </Button>
        </Panel>

        <Panel title={`Saved records (${rows.length})`} className="xl:col-span-2" bodyClassName="overflow-x-auto">
          {rows.length === 0 ? <p className="text-[13px] text-muted" data-testid="records-empty">No records yet.</p> : (
            <table className="w-full min-w-[640px] text-[12.5px]" data-testid="records-table">
              <thead className="text-left text-dim">
                <tr>{["Saved (UTC)", "Label", "Scenario", "Sim time", "Choke health", "Validation", ""].map((h) => <th key={h} className="py-1 pr-2 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className={`border-t border-line ${sel?.id === r.id ? "bg-accent/[0.06]" : ""}`}>
                    <td className="num py-1 pr-2">{r.created_at.replace("T", " ").slice(0, 16)}</td>
                    <td className="py-1 pr-2">
                      <button type="button" className="text-left font-semibold text-accent hover:underline" onClick={() => open(r.id)}>{r.label}</button>
                      {r.has_comparison ? <Badge tone="info" className="ml-1">comparison</Badge> : null}
                    </td>
                    <td className="py-1 pr-2">{r.scenario_name ?? r.scenario_id}</td>
                    <td className="num py-1 pr-2">{simTime(r.sim_time_s)}</td>
                    <td className="py-1 pr-2">{r.health_category ?? "—"}</td>
                    <td className="py-1 pr-2 text-muted">{r.validation_status}</td>
                    <td className="py-1 text-right">
                      <a className="inline-flex px-1 text-muted hover:text-fg" href={`/api/records/${r.id}/report`} target="_blank" rel="noreferrer" aria-label={`report ${r.label}`} title="Engineering report (print to PDF)"><FileText size={14} /></a>
                      <a className="inline-flex px-1 text-muted hover:text-fg" href={`/api/records/${r.id}/export`} aria-label={`export ${r.label}`} title="Export JSON"><Download size={14} /></a>
                      <Button size="xs" variant="ghost" aria-label={`delete ${r.label}`} onClick={() => remove(r.id)}><Trash2 size={13} /></Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        {sel && <RecordDetail r={sel} />}
      </div>
    </PageBody>
  );
}

function RecordDetail({ r }: { r: SimulationRecord }) {
  const res = r.results;
  const chk = r.inputs.valves.find((v) => v.tag === "CHK-101");
  return (
    <Panel title={`Record: ${r.label}`} className="xl:col-span-3" subtitle={`${r.header.scenario_name} · saved ${r.created_at.replace("T", " ").slice(0, 19)} UTC · app ${r.header.app_version} · schema ${r.schema_version}`}
      right={<Badge tone={r.validation.overall.startsWith("Field-calibrated") ? "info" : "warn"} data-testid="record-validation">{r.validation.overall}</Badge>}>
      <div className="grid gap-4 lg:grid-cols-3 text-[12.5px]" data-testid="record-detail">
        <div>
          <h3 className="mb-1 t-eyebrow">Key results</h3>
          <ul className="space-y-0.5">
            <li>Simulated time {simTime(r.header.sim_time_s)} · {r.header.mode} · {r.header.fluid_model}</li>
            {chk && <li>CHK-101 at {fmt(chk.position_pct, 1)} %</li>}
            {res.rates_arrival && <li>Oil {fmt(res.rates_arrival.oil_sm3_d, 0)} · gas {fmt(res.rates_arrival.gas_sm3_d, 0)} · water {fmt(res.rates_arrival.water_sm3_d, 0)} Sm³/d</li>}
            {res.sand && <li>Sand at the choke {fmt(res.sand.at_choke_kg_d, 2)} kg/d</li>}
            {res.choke_health && <li>Choke health: <span className="font-semibold">{res.choke_health.category}</span></li>}
            {res.recommendation && <li>{res.recommendation.title}</li>}
            {res.cavitation?.risk && <li>Cavitation: {res.cavitation.risk}</li>}
          </ul>
          <h3 className="mb-1 mt-3 t-eyebrow">Validation</h3>
          <p className="text-muted">{r.validation.model_status_range}. {r.validation.statement}</p>
        </div>
        <div>
          <h3 className="mb-1 t-eyebrow">Data provenance</h3>
          <table className="w-full" data-testid="record-provenance">
            <tbody>
              {Object.entries(r.provenance).map(([k, v]) => (
                <tr key={k} className="border-t border-line"><td className="py-0.5 pr-2 text-muted">{k.replace(/_/g, " ")}</td><td className="py-0.5">{v}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <h3 className="mb-1 t-eyebrow">Methods and model versions</h3>
          <ul className="space-y-1">
            {Object.entries(r.methods).map(([k, m]) => (
              <li key={k}><span className="font-semibold">{k.replace(/_/g, " ")}</span> v{m.version} · {m.status}<div className="text-[11.5px] text-dim">{m.method}</div></li>
            ))}
          </ul>
        </div>
      </div>
      {r.notes && <p className="mt-2 text-[12.5px]">Notes: {r.notes}</p>}
      <a className="mt-2 inline-flex items-center gap-1 text-[13px] font-semibold text-accent hover:underline" href={`/api/records/${r.id}/report`} target="_blank" rel="noreferrer" data-testid="record-report-link">
        <FileText size={14} />Open the engineering report{r.comparison ? " (with the scenario comparison)" : ""}
      </a>
      <details className="mt-2 text-[12px] text-dim">
        <summary className="cursor-pointer">Assumptions ({r.assumptions.length})</summary>
        <ul className="mt-1 list-disc pl-5">{r.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
      </details>
    </Panel>
  );
}
