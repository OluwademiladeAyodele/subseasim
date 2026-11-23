/**
 * Surrogate models: train on simulator cases (steady twins, background job)
 * or on imported CFD / experiment / vendor / field cases; inspect the
 * cross-validation; predict with an uncertainty interval inside the
 * validated envelope; check any point against the simulator.
 */
import { Cpu, FileUp, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { JobProgress } from "@/components/JobProgress";
import { Badge, Button, Input, Panel, Select } from "@/components/ui/primitives";
import { fmt } from "@/lib/units";
import { api } from "@/services/api";
import { type Job, jobActive } from "@/types/jobs";
import { type Prediction, type SimulatorCheck, SURROGATE_INPUTS, SURROGATE_OUTPUTS, type SurrogateCard, type SurrogateSummary } from "@/types/surrogates";

const inMeta = (k: string) => SURROGATE_INPUTS.find((x) => x.key === k)!;
const show = (k: string, v: number) => v * (inMeta(k)?.scale ?? 1);
const store = (k: string, v: number) => v / (inMeta(k)?.scale ?? 1);

function Parity({ pts }: { pts: [number, number][] }) {
  const W = 220;
  const vals = pts.flat();
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const s = (v: number) => 8 + ((v - lo) / (hi - lo || 1)) * (W - 16);
  return (
    <svg viewBox={`0 0 ${W} ${W}`} className="h-[180px] w-[180px] rounded border border-line bg-panel" role="img" aria-label="Leave-one-out parity plot">
      <line x1={8} y1={W - 8} x2={W - 8} y2={8} stroke="#94a3b8" strokeDasharray="4 3" />
      {pts.map(([t, p], i) => <circle key={i} cx={s(t)} cy={W - s(p)} r={2.6} fill="#0369a1" fillOpacity={0.8} />)}
      <text x={10} y={W - 12} fontSize={9} fill="#64748b">simulated / measured →</text>
      <text x={12} y={16} fontSize={9} fill="#64748b">↑ predicted (left out)</text>
    </svg>
  );
}

export function SurrogatesPage() {
  const { sim, state } = useWorkstation();
  const [list, setList] = useState<SurrogateSummary[]>([]);
  const [card, setCard] = useState<SurrogateCard | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const refresh = useCallback(() => api.listSurrogates().then(setList).catch((e: Error) => setErr(e.message)), []);
  useEffect(() => { refresh(); }, [refresh]);
  const open = async (id: string) => {
    try { setCard(await api.getSurrogate(id)); setErr(null); } catch (e) { setErr((e as Error).message); }
  };
  const remove = async (id: string) => {
    try { await api.deleteSurrogate(id); if (card?.id === id) setCard(null); await refresh(); } catch (e) { setErr((e as Error).message); }
  };

  return (
    <PageBody intro="A surrogate gives near-instant predictions of selected results, with an uncertainty interval, but only inside the range it was trained on. Train it on simulator cases or import CFD, test or vendor cases; outside its envelope, run the high-fidelity calculation.">
      {err && <p className="mb-3 text-[13px] text-bad" data-testid="surrogate-error">{err}</p>}
      <div className="grid items-start gap-4 xl:grid-cols-3">
        <TrainPanel onDone={async (id) => { await refresh(); await open(id); }} canTrain={state.fluid_model === "black_oil"} />
        <Panel title={`Models (${list.length})`} icon={<Cpu size={16} />} className="xl:col-span-2" bodyClassName="overflow-x-auto">
          {list.length === 0 ? <p className="text-[13px] text-muted" data-testid="surrogates-empty">No surrogate models yet.</p> : (
            <table className="w-full min-w-[560px] text-[12.5px]" data-testid="surrogate-table">
              <thead className="text-left text-dim"><tr>{["Name", "Method", "Cases", "Trained on", "Created (UTC)", ""].map((h) => <th key={h} className="py-1 pr-2 font-medium">{h}</th>)}</tr></thead>
              <tbody>
                {list.map((s) => (
                  <tr key={s.id} className={`border-t border-line ${card?.id === s.id ? "bg-accent/[0.06]" : ""}`}>
                    <td className="py-1 pr-2"><button type="button" className="font-semibold text-accent hover:underline" onClick={() => open(s.id)}>{s.name}</button></td>
                    <td className="py-1 pr-2">{s.method === "gp" ? "Gaussian process" : "Quadratic surface"}</td>
                    <td className="num py-1 pr-2">{s.n_cases}</td>
                    <td className="py-1 pr-2">{Object.entries(s.sources).map(([k, n]) => <Badge key={k} tone={k === "simulator" ? "neutral" : "info"} className="mr-1">{k} {n}</Badge>)}</td>
                    <td className="num py-1 pr-2">{s.created_at.replace("T", " ").slice(0, 16)}</td>
                    <td><Button size="xs" variant="ghost" aria-label={`delete ${s.name}`} onClick={() => remove(s.id)}><Trash2 size={13} /></Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
        {card && <ModelPanel key={card.id} card={card} sessionId={sim.sessionId} />}
        <ImportPanel onDone={async (id) => { await refresh(); await open(id); }} setErr={setErr} />
      </div>
    </PageBody>
  );
}

function TrainPanel({ onDone, canTrain }: { onDone: (id: string) => void; canTrain: boolean }) {
  const { actions } = useWorkstation();
  const [name, setName] = useState("Choke response");
  const [method, setMethod] = useState<"gp" | "poly">("gp");
  const [bounds, setBounds] = useState<Record<string, [number, number] | null>>({ choke_pct: [20, 70], water_cut: [0.2, 0.5] });
  const [outs, setOuts] = useState<string[]>(["oil_sm3_d", "choke_dp_bar", "jet_velocity_m_s", "hole_rate_mm_y"]);
  const [n, setN] = useState("30");
  const [job, setJob] = useState<Job | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = async () => {
    const b = Object.fromEntries(Object.entries(bounds).filter(([, v]) => v)) as Record<string, [number, number]>;
    const j = await actions.startJob("surrogate_build", { name, method, bounds: b, outputs: outs, n_samples: Number(n) });
    if (typeof j === "string") setErr(j);
    else { setErr(null); setJob(j); }
  };
  return (
    <Panel title="Train on simulator cases" subtitle="Latin-hypercube design; each case solved on a steady twin of this session (same models).">
      <label className="flex flex-col gap-1 py-0.5 text-[12.5px] text-muted">Name<Input aria-label="Surrogate name" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} /></label>
      <label className="flex items-center justify-between gap-2 py-0.5 text-[12.5px] text-muted">Method
        <Select aria-label="Surrogate method" value={method} onChange={(e) => setMethod(e.target.value as "gp" | "poly")}>
          <option value="gp">Gaussian process (with uncertainty)</option><option value="poly">Quadratic response surface</option>
        </Select>
      </label>
      <h3 className="mb-1 mt-2 t-eyebrow">Inputs and training range</h3>
      {SURROGATE_INPUTS.map((f) => {
        const b = bounds[f.key];
        return (
          <div key={f.key} className="flex items-center gap-2 py-0.5 text-[12.5px]">
            <input type="checkbox" aria-label={`use ${f.label}`} checked={!!b} onChange={(e) => setBounds({ ...bounds, [f.key]: e.target.checked ? [store(f.key, f.min), store(f.key, f.max)] : null })} />
            <span className="w-36 text-muted">{f.label}</span>
            {b && <>
              <Input aria-label={`${f.label} min`} className="w-16" inputMode="decimal" defaultValue={String(show(f.key, b[0]))} onChange={(e) => Number.isFinite(Number(e.target.value)) && setBounds({ ...bounds, [f.key]: [store(f.key, Number(e.target.value)), b[1]] })} />
              <span className="text-dim">–</span>
              <Input aria-label={`${f.label} max`} className="w-16" inputMode="decimal" defaultValue={String(show(f.key, b[1]))} onChange={(e) => Number.isFinite(Number(e.target.value)) && setBounds({ ...bounds, [f.key]: [b[0], store(f.key, Number(e.target.value))] })} />
              <span className="text-dim">{f.unit}</span>
            </>}
          </div>
        );
      })}
      <h3 className="mb-1 mt-2 t-eyebrow">Outputs</h3>
      <div className="grid grid-cols-2 gap-x-3 text-[12.5px]">
        {SURROGATE_OUTPUTS.map((o) => (
          <label key={o.key} className="flex items-center gap-1.5 py-0.5">
            <input type="checkbox" checked={outs.includes(o.key)} aria-label={`output ${o.label}`} onChange={(e) => setOuts(e.target.checked ? [...outs, o.key] : outs.filter((x) => x !== o.key))} />{o.label}
          </label>
        ))}
      </div>
      <div className="mt-2 flex items-center gap-2 text-[12.5px] text-muted">
        Cases <Input aria-label="Number of cases" className="w-16" inputMode="numeric" value={n} onChange={(e) => setN(e.target.value)} />
        <span className="text-dim">(≈ 1 s each)</span>
        <span className="flex-1" />
        <Button variant="primary" size="sm" data-testid="train-surrogate" disabled={!canTrain || jobActive(job) || !outs.length || !name.trim()} onClick={run}>Train</Button>
      </div>
      {!canTrain && <p className="mt-1 text-[12px] text-warn">Needs the three-phase fluid model.</p>}
      {err && <p className="mt-1 text-[12px] text-bad" data-testid="train-error">{err}</p>}
      {job && <JobProgress job={job} onFinished={(j) => { if (j.state === "completed" && j.result?.id) onDone(String(j.result.id)); }} />}
    </Panel>
  );
}

function ModelPanel({ card, sessionId }: { card: SurrogateCard; sessionId: string | null }) {
  const [x, setX] = useState<Record<string, number>>(() => Object.fromEntries(card.inputs.map((i) => [i.key, (i.min + i.max) / 2])));
  const [pred, setPred] = useState<Prediction | null>(null);
  const [check, setCheck] = useState<SimulatorCheck | null>(null);
  const [sel, setSel] = useState(card.outputs[0]?.key);
  const [err, setErr] = useState<string | null>(null);
  const predict = useCallback(async (q: Record<string, number>) => {
    try { setPred(await api.predictSurrogate(card.id, q)); setCheck(null); setErr(null); } catch (e) { setErr((e as Error).message); }
  }, [card.id]);
  useEffect(() => { predict(x); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const v = sel ? card.validation[sel] : undefined;
  return (
    <Panel title={`Model: ${card.name}`} className="xl:col-span-3" subtitle={`${card.method === "gp" ? "Gaussian process" : "Quadratic response surface"} · ${card.n_cases} cases · v${card.model_version}`}
      right={<Badge tone="warn" data-testid="surrogate-status">{card.status}</Badge>}>
      <div className="grid gap-4 lg:grid-cols-3 text-[12.5px]">
        <div>
          <h3 className="mb-1 t-eyebrow">Cross-validation (leave one out)</h3>
          <table className="w-full" data-testid="surrogate-validation">
            <thead className="text-left text-dim"><tr><th className="font-medium">Output</th><th className="text-right font-medium">R²</th><th className="text-right font-medium">RMSE</th><th className="text-right font-medium">95 % cover</th></tr></thead>
            <tbody>
              {card.outputs.map((o) => {
                const val = card.validation[o.key];
                return (
                  <tr key={o.key} className={`cursor-pointer border-t border-line ${sel === o.key ? "bg-accent/[0.06]" : ""}`} onClick={() => setSel(o.key)}>
                    <td className="py-0.5">{o.label}</td>
                    <td className={`num py-0.5 text-right ${val.loo_r2 != null && val.loo_r2 < 0.9 ? "text-warn" : ""}`}>{val.loo_r2 == null ? "—" : fmt(val.loo_r2, 3)}</td>
                    <td className="num py-0.5 text-right">{fmt(val.loo_rmse, 3)} {o.unit}</td>
                    <td className={`num py-0.5 text-right ${val.loo_coverage_95 < 0.85 ? "text-warn" : ""}`}>{fmt(val.loo_coverage_95 * 100, 0)} %</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-1 text-[11.5px] text-dim">Measures how well the surrogate reproduces its training source, not the accuracy of that source. 95 % cover well below 95 % means the interval is over-confident for that output.</p>
        </div>
        <div className="flex flex-col items-start">
          <h3 className="mb-1 t-eyebrow">Parity: {card.outputs.find((o) => o.key === sel)?.label}</h3>
          {v && <Parity pts={v.loo_points} />}
        </div>
        <div>
          <h3 className="mb-1 t-eyebrow">Training envelope</h3>
          <ul className="space-y-0.5">{card.inputs.map((i) => <li key={i.key}>{i.label}: <span className="num">{fmt(show(i.key, i.min), 2)} – {fmt(show(i.key, i.max), 2)}</span> {inMeta(i.key)?.unit ?? i.unit}</li>)}</ul>
          <p className="mt-1">Trained on: {Object.entries(card.sources).map(([k, n]) => `${k} ${n}`).join(", ")}</p>
          {card.notes.map((n) => <p key={n} className="text-[11.5px] text-dim">{n}</p>)}
        </div>
      </div>

      <h3 className="mb-1 mt-4 t-eyebrow">Predict</h3>
      <div className="flex flex-wrap items-end gap-3">
        {card.inputs.map((i) => (
          <label key={i.key} className="flex flex-col gap-0.5 text-[12px] text-muted">{i.label} ({inMeta(i.key)?.unit ?? i.unit})
            <Input aria-label={`predict ${i.label}`} className="w-24" inputMode="decimal" defaultValue={String(fmt(show(i.key, x[i.key]), 3)).replace(/,/g, "")}
              onChange={(e) => { const n = Number(e.target.value); if (Number.isFinite(n)) setX({ ...x, [i.key]: store(i.key, n) }); }} />
          </label>
        ))}
        <Button size="sm" variant="primary" onClick={() => predict(x)} data-testid="surrogate-predict">Predict</Button>
        <Button size="sm" disabled={!sessionId} data-testid="surrogate-check"
          onClick={async () => { if (!sessionId) return; try { setCheck(await api.checkSurrogate(sessionId, card.id, x)); } catch (e) { setErr((e as Error).message); } }}>
          Check with the simulator
        </Button>
      </div>
      {err && <p className="mt-1 text-[12px] text-bad">{err}</p>}
      {pred && (
        <>
          <p className={`mt-2 text-[12.5px] ${pred.envelope.inside ? "text-ok" : "font-semibold text-warn"}`} data-testid="surrogate-envelope">{pred.envelope.message}</p>
          <table className="mt-1 w-full max-w-[760px] text-[12.5px]" data-testid="surrogate-prediction">
            <thead className="text-left text-dim"><tr><th className="font-medium">Output</th><th className="text-right font-medium">Surrogate</th><th className="text-right font-medium">95 % interval</th>{check && <><th className="text-right font-medium">Simulator</th><th className="text-right font-medium">Within 95 %</th></>}</tr></thead>
            <tbody>
              {Object.entries(pred.outputs).map(([k, o]) => (
                <tr key={k} className="border-t border-line">
                  <td className="py-0.5">{o.label}</td>
                  <td className="num py-0.5 text-right">{fmt(o.mean, 3)} {o.unit}</td>
                  <td className="num py-0.5 text-right">{fmt(o.p2_5, 3)} – {fmt(o.p97_5, 3)}</td>
                  {check && <>
                    <td className="num py-0.5 text-right" data-testid={`check-${k}`}>{check.outputs[k]?.simulator == null ? "—" : fmt(check.outputs[k].simulator!, 3)}</td>
                    <td className={`py-0.5 text-right ${check.outputs[k]?.within_95 ? "text-ok" : "text-bad"}`}>{check.outputs[k]?.within_95 == null ? "—" : check.outputs[k].within_95 ? "yes" : "no"}</td>
                  </>}
                </tr>
              ))}
            </tbody>
          </table>
          {check && <p className="mt-1 text-[11.5px] text-dim">{check.simulator}</p>}
        </>
      )}
      <ul className="mt-3 list-disc pl-5 text-[11.5px] text-dim">{card.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
    </Panel>
  );
}

function ImportPanel({ onDone, setErr }: { onDone: (id: string) => void; setErr: (e: string | null) => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("Imported cases");
  const [method, setMethod] = useState<"gp" | "poly">("gp");
  const [ins, setIns] = useState<string[]>(["choke_pct"]);
  const [outs, setOuts] = useState<string[]>(["hole_rate_mm_y"]);
  const read = (f: Blob) => new Promise<string>((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result ?? "")); r.onerror = () => rej(r.error); r.readAsText(f); });
  return (
    <Panel title="Train on imported cases" icon={<FileUp size={16} />} className="xl:col-span-3"
      subtitle="CFD, experiment, vendor or field results you hold. SubseaSim does not generate such data. CSV columns: the input and output keys below, source, reference.">
      <div className="flex flex-wrap items-center gap-3 text-[12.5px]">
        <Input aria-label="Imported surrogate name" className="w-56" value={name} onChange={(e) => setName(e.target.value)} />
        <Select aria-label="Imported surrogate method" value={method} onChange={(e) => setMethod(e.target.value as "gp" | "poly")}><option value="gp">Gaussian process</option><option value="poly">Quadratic surface</option></Select>
        <span className="text-muted">Inputs:</span>
        {SURROGATE_INPUTS.map((f) => <label key={f.key} className="flex items-center gap-1"><input type="checkbox" checked={ins.includes(f.key)} onChange={(e) => setIns(e.target.checked ? [...ins, f.key] : ins.filter((x) => x !== f.key))} /><code>{f.key}</code></label>)}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-3 text-[12.5px]">
        <span className="text-muted">Outputs:</span>
        {SURROGATE_OUTPUTS.map((o) => <label key={o.key} className="flex items-center gap-1"><input type="checkbox" checked={outs.includes(o.key)} onChange={(e) => setOuts(e.target.checked ? [...outs, o.key] : outs.filter((x) => x !== o.key))} /><code>{o.key}</code></label>)}
      </div>
      <Button size="sm" className="mt-2" disabled={!ins.length || !outs.length || !name.trim()} onClick={() => fileRef.current?.click()} data-testid="surrogate-import">Choose CSV and train</Button>
      <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" data-testid="surrogate-import-file"
        onChange={async (e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (!f) return;
          try {
            const r = await api.importSurrogate({ name: name.trim(), method, inputs: ins, outputs: outs, csv: await read(f) });
            setErr(null);
            onDone(r.id);
          } catch (err) { setErr((err as Error).message); }
        }} />
      <p className="mt-1 text-[11.5px] text-dim">Water cut is a fraction (0–1) in the file. Every case needs a value for every chosen column; source is one of simulator, cfd, experiment, vendor, field.</p>
    </Panel>
  );
}
