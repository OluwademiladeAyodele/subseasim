/**
 * Sand monitoring: sanding onset (critical drawdown), sand rates from the
 * formation through the screens to the choke, the XT3001 detector, particle
 * size and transport. All values from the backend sand model.
 */
import { Activity, AlertTriangle, Mountain, Radar, Route } from "lucide-react";

import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { Badge, Button, Panel, Stat } from "@/components/ui/primitives";
import { fmt } from "@/lib/units";
import type { SandChokeResults } from "@/types/sand";

export function Unavailable({ items, onInputs }: { items: string[]; onInputs?: () => void }) {
  return (
    <div className="rounded-lg border border-warn/40 bg-warn/[0.06] px-3 py-2 text-[12.5px]" data-testid="unavailable">
      <div className="font-semibold text-warn">Prediction unavailable — missing inputs</div>
      <ul className="mt-1 list-disc pl-5 text-muted">{items.map((m) => <li key={m}>{m}</li>)}</ul>
      {onInputs && <Button size="xs" className="mt-2" onClick={onInputs}>Enter inputs</Button>}
    </div>
  );
}

export function Trend({ samples, keys, labels, unit, scale = 1 }: { samples: Record<string, number | null>[]; keys: string[]; labels: string[]; unit: string; scale?: number }) {
  const pts = samples.filter((s) => keys.some((k) => s[k] != null)).slice(-300);
  if (pts.length < 2) return <p className="text-[12px] text-dim">Collecting data…</p>;
  const ts = pts.map((s) => s.t as number);
  const vals = pts.flatMap((s) => keys.map((k) => s[k])).filter((v): v is number => v != null).map((v) => v * scale);
  const lo = Math.min(0, ...vals);
  const hi = Math.max(...vals, lo + 1e-9);
  const W = 400, H = 90;
  const x = (t: number) => ((t - ts[0]) / (ts[ts.length - 1] - ts[0] || 1)) * W;
  const y = (v: number) => H - 4 - ((v * scale - lo) / (hi - lo)) * (H - 8);
  const colors = ["#0369a1", "#94a3b8", "#d97706"];
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-[90px] w-full" preserveAspectRatio="none">
        {keys.map((k, i) => (
          <path key={k} fill="none" stroke={colors[i]} strokeWidth={i === 1 ? 2 : 1.6} strokeDasharray={i === 1 ? "4 3" : undefined} vectorEffect="non-scaling-stroke"
            d={pts.filter((s) => s[k] != null).map((s, j) => `${j ? "L" : "M"}${x(s.t as number).toFixed(1)} ${y(s[k] as number).toFixed(1)}`).join(" ")} />
        ))}
      </svg>
      <div className="flex flex-wrap gap-3 text-[11.5px] text-muted">
        {labels.map((l, i) => <span key={l}><span className="mr-1 inline-block h-0.5 w-4 align-middle" style={{ background: colors[i] }} />{l}</span>)}
        <span className="ml-auto num">{fmt(lo, 2)} – {fmt(hi, 2)} {unit}</span>
      </div>
    </div>
  );
}

function RiskBar({ index }: { index: number }) {
  const pct = Math.min(index / 2, 1) * 100;
  return (
    <div className="mt-2" data-testid="risk-bar">
      <div className="relative h-3 overflow-hidden rounded-full bg-gradient-to-r from-ok/30 via-warn/40 to-bad/50">
        <div className="absolute inset-y-0 w-0.5 bg-fg" style={{ left: "50%" }} title="onset (index 1)" />
        <div className="absolute -top-0.5 h-4 w-1.5 rounded bg-accent" style={{ left: `calc(${pct}% - 3px)` }} />
      </div>
      <div className="mt-0.5 flex justify-between text-[11px] text-dim"><span>0</span><span>onset = 1</span><span>2+</span></div>
    </div>
  );
}

export function SandPage() {
  const { state, sim, go } = useWorkstation();
  const r = state.sand_choke as SandChokeResults | null | undefined;
  if (!r || !r.available || !r.sand) {
    return <PageBody><Panel title="Sand monitoring"><p className="text-[13px] text-muted">{r?.reason ?? "No sand model in this scenario."}</p></Panel></PageBody>;
  }
  const s = r.sand;
  const on = s.onset;
  const det = r.detector!;
  const samples = sim.samples as unknown as Record<string, number | null>[];
  const missing = s.missing;
  return (
    <PageBody intro="Sand is followed from the formation, through the sand screens, up the well to the choke and on to the manifold. It moves only with the simulated flow.">
      <div className="grid items-start gap-4 xl:grid-cols-3" data-testid="sand-page">
        <Panel title="Sanding onset" icon={<Mountain size={16} />} subtitle="Critical drawdown, perforation-tunnel failure (TWC-based)"
          right={on?.available ? <Badge tone={(on.risk_index ?? 0) > 1 ? "bad" : (on.risk_index ?? 0) > 0.8 ? "warn" : "ok"} data-testid="risk-badge">{(on.risk_index ?? 0) > 1 ? "SANDING" : "below onset"}</Badge> : undefined}>
          {on?.available ? (
            <div className="space-y-2 text-[13px]">
              <div className="grid grid-cols-2 gap-3">
                <Stat label="Drawdown" value={fmt(on.drawdown_bar, 1)} unit="bar" />
                <Stat label="Critical drawdown" value={fmt(on.critical_drawdown_bar, 1)} unit="bar" />
              </div>
              <div className="text-muted">Risk index (drawdown / critical): <span className="num font-semibold text-fg" data-testid="risk-index">{fmt(on.risk_index, 2)}</span></div>
              <RiskBar index={on.risk_index ?? 0} />
              <div className="num text-[12px] text-dim">σv {fmt(on.sigma_v_bar, 0)} bar · σh {fmt(on.sigma_h_bar, 0)} bar · effective strength {fmt(on.effective_strength_bar, 0)} bar · critical BHFP {fmt(on.critical_bhfp_bara, 1)} bara</div>
              {[...on.notes, ...on.assumed.map((a) => `ASSUMED: ${a}`)].map((n) => <p key={n} className={`text-[12px] ${n.startsWith("ASSUMED") ? "text-warn" : "text-dim"}`}>{n}</p>)}
            </div>
          ) : <Unavailable items={on?.missing ?? []} onInputs={() => go("sandinputs")} />}
        </Panel>

        <Panel title="Sand rates" icon={<Activity size={16} />} subtitle={s.mode === "measured" ? "Measured / configured input" : "Predictive (calibrated empirical rate)"} className="xl:col-span-2">
          {missing.length > 0 && <div className="mb-3"><Unavailable items={missing} onInputs={() => go("sandinputs")} /></div>}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat testId="sand-formation" label="Formation (sandface)" value={fmt(s.formation_kg_d, 2)} unit="kg/d" />
            <Stat testId="sand-produced" label="Through the screens" value={fmt(s.produced_kg_d, 2)} unit="kg/d" tone="accent" />
            <Stat testId="sand-choke" label="Arriving at the choke" value={fmt(s.at_choke_kg_d, 2)} unit="kg/d" tone="warn" />
            <Stat label="Retained behind screens" value={fmt(r.cumulative?.retained_kg, 1)} unit="kg total" />
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <div className="text-[12.5px]">
              <h3 className="mb-1 t-eyebrow">Screens & particle size</h3>
              {s.screen.available ? (
                <>
                  <div>Passing fraction: <span className="num font-semibold">{fmt((s.screen.passing_fraction ?? 0) * 100, 1)} %</span> · produced D50 <span className="num">{fmt(s.screen.produced_d50_um, 0)} µm</span></div>
                  {s.screen.notes.map((n) => <p key={n} className="text-[12px] text-dim">{n}</p>)}
                </>
              ) : <p className="text-warn">Unavailable: {s.screen.missing.join(", ")}</p>}
              {s.psd && <p className="text-[12px] text-dim">Formation PSD log-normal fit: D50 {fmt(s.psd.d50_um, 0)} µm, σ(ln d) {fmt(s.psd.sigma_ln, 2)}</p>}
            </div>
            <div>
              <h3 className="mb-1 t-eyebrow">Sand at the choke vs detector</h3>
              <Trend samples={samples} keys={["sand:detector_g_s", "sand:choke_g_s"]} labels={[`${det.tag} reading`, "true sand at choke"]} unit="g/s" />
            </div>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-3 md:grid-cols-4 text-[12.5px]">
            <div>Cumulative at choke <span className="num font-semibold">{fmt(r.cumulative?.choke_kg, 1)} kg</span></div>
            <div>Produced <span className="num font-semibold">{fmt(r.cumulative?.produced_kg, 1)} kg</span></div>
            <div>Liquid produced <span className="num font-semibold">{fmt(r.cumulative?.liquid_sm3, 0)} Sm³</span></div>
            <div>Trim service <span className="num font-semibold">{fmt(r.service_days, 1)} d</span></div>
          </div>
        </Panel>

        <Panel title={`Sand detector ${det.tag}`} icon={<Radar size={16} />} subtitle={`${det.type.replace(/_/g, " ")} · ${det.location}`}
          right={<Badge tone={det.alarm ? "bad" : det.status === "OK" || det.status === "BELOW_DETECTION" ? "ok" : "warn"} data-testid="detector-status">{det.alarm ? "ALARM" : det.status}</Badge>}>
          <div className="grid grid-cols-2 gap-3">
            <Stat testId="detector-reading" label="Reading" value={det.reading_g_s == null ? "—" : fmt(det.reading_g_s, 3)} unit="g/s" tone={det.alarm ? "bad" : "accent"}
              sub={`≈ ${det.reading_g_s == null ? "—" : fmt(det.reading_g_s * 86.4, 2)} kg/d · ±${fmt(det.uncertainty_pct, 0)} % (k=2)`} />
            <Stat label="True at detector" value={fmt(det.true_g_s, 3)} unit="g/s" sub={`alarm at ${det.alarm_threshold_g_s} g/s`} />
          </div>
          <p className="mt-2 text-[12px] text-dim">
            Velocity at the detector {fmt(det.velocity_m_s, 2)} m/s. Acoustic detectors need flow velocity to hear the impacts and carry a calibration uncertainty; the reading is not the
            true sand rate. Cumulative measured {fmt(det.cumulative_measured_kg, 2)} kg.
          </p>
        </Panel>

        <Panel title="Sand transport" icon={<Route size={16} />} className="xl:col-span-2">
          <p className="text-[12.5px] text-muted">{r.transport?.model}</p>
          {!!r.transport?.deposition?.length && (
            <>
              <div className="mt-2 flex h-6 overflow-hidden rounded border border-line" title="flowline segments: red = liquid velocity below the sand transport velocity (deposition risk)">
                {r.transport.deposition.map((x) => (
                  <div key={x.segment} className="flex-1 border-r border-white/70" style={{ background: x.risk ? "#fecaca" : "#bbf7d0" }} />
                ))}
              </div>
              <p className="mt-1 text-[12px] text-dim">
                Flowline: {r.transport.deposition_risk_segments} of {r.transport.deposition.length} segments with deposition risk. {r.transport.deposition_note}
              </p>
            </>
          )}
          <p className="mt-2 flex items-start gap-1.5 text-[12px] text-dim"><AlertTriangle size={13} className="mt-0.5 shrink-0" />Sand concentration is carried with the production flow and stops when the flow stops.</p>
        </Panel>
      </div>
    </PageBody>
  );
}
