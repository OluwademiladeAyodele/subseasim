/**
 * Sand source for the choke health page: sanding onset (critical drawdown),
 * sand rates from the formation through the screens to the choke, particle
 * size and transport. All values from the backend sand model.
 */
import { Activity, AlertTriangle, Mountain } from "lucide-react";

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

export function SandSourcePanel({ r, samples, onInputs }: { r: SandChokeResults; samples: Record<string, number | null>[]; onInputs: () => void }) {
  const s = r.sand;
  if (!s) return null;
  const on = s.onset;
  return (
    <Panel title="Sand source" icon={<Mountain size={16} />} className="xl:col-span-3"
      subtitle={`${s.mode === "measured" ? "Measured / configured sand rate" : "Predictive: critical drawdown (TWC) + calibrated empirical rate"} · drives the erosion below`}
      right={on?.available ? <Badge tone={(on.risk_index ?? 0) > 1 ? "bad" : (on.risk_index ?? 0) > 0.8 ? "warn" : "ok"} data-testid="risk-badge">{(on.risk_index ?? 0) > 1 ? "SANDING" : "below onset"}</Badge> : undefined}>
      <div className="grid gap-4 lg:grid-cols-3" data-testid="sand-source">
        <div className="text-[13px]">
          <h3 className="mb-1 t-eyebrow">Sanding onset</h3>
          {on?.available ? (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-3">
                <Stat label="Drawdown" value={fmt(on.drawdown_bar, 1)} unit="bar" />
                <Stat label="Critical drawdown" value={fmt(on.critical_drawdown_bar, 1)} unit="bar" />
              </div>
              <div className="text-muted">Risk index (drawdown / critical): <span className="num font-semibold text-fg" data-testid="risk-index">{fmt(on.risk_index, 2)}</span></div>
              <RiskBar index={on.risk_index ?? 0} />
              <div className="num text-[12px] text-dim">σv {fmt(on.sigma_v_bar, 0)} bar · σh {fmt(on.sigma_h_bar, 0)} bar · effective strength {fmt(on.effective_strength_bar, 0)} bar · critical BHFP {fmt(on.critical_bhfp_bara, 1)} bara</div>
              {[...on.notes, ...on.assumed.map((a) => `ASSUMED: ${a}`)].map((n) => <p key={n} className={`text-[12px] ${n.startsWith("ASSUMED") ? "text-warn" : "text-dim"}`}>{n}</p>)}
            </div>
          ) : <Unavailable items={on?.missing ?? []} onInputs={onInputs} />}
        </div>
        <div className="lg:col-span-2">
          {s.missing.length > 0 && <div className="mb-3"><Unavailable items={s.missing} onInputs={onInputs} /></div>}
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
              <h3 className="mb-1 flex items-center gap-1 t-eyebrow"><Activity size={12} />Sand arriving at the choke</h3>
              <Trend samples={samples} keys={["sand:choke_g_s"]} labels={["sand at choke"]} unit="g/s" />
            </div>
          </div>
          <p className="mt-2 text-[12.5px] text-muted">{r.transport?.model}</p>
          {!!r.transport?.deposition?.length && (
            <p className="mt-1 text-[12px] text-dim">
              Flowline: {r.transport.deposition_risk_segments} of {r.transport.deposition.length} segments with deposition risk. {r.transport.deposition_note}
            </p>
          )}
          <p className="mt-1 flex items-start gap-1.5 text-[12px] text-dim"><AlertTriangle size={13} className="mt-0.5 shrink-0" />Sand is carried with the production flow: it reaches the choke after the transit time and stops when the flow stops.</p>
        </div>
      </div>
    </Panel>
  );
}
