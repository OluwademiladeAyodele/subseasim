/**
 * Valve integrity testing (stroke, pressure-hold, inflow). The backend
 * verifies isolation, follows the evolving dynamic state and applies the
 * acceptance criterion; this panel only starts tests and shows results.
 */
import { ShieldCheck, Square, Timer } from "lucide-react";
import { useState } from "react";

import { Badge, Button, Input, Select } from "@/components/ui/primitives";
import { fmt, formatDuration } from "@/lib/units";
import type { IntegrityRequest } from "@/controls/integrityTypes";
import type { IntegrityPreset, IntegrityTestSnapshot, IntegrityType, RestrictionSnapshot, SimulationState } from "@/types/simulation";

interface Props {
  state: SimulationState;
  onStart: (req: IntegrityRequest) => Promise<boolean>;
  onAbort: (id: number) => Promise<boolean>;
}

const PHASE_TONE: Record<IntegrityTestSnapshot["phase"], "info" | "warn" | "ok" | "bad" | "neutral"> = {
  stabilising: "info",
  holding: "warn",
  stroking: "warn",
  passed: "ok",
  failed: "bad",
  aborted: "neutral",
};

export function IntegrityPanel({ state, onStart, onAbort }: Props) {
  const [custom, setCustom] = useState<IntegrityRequest>({ type: "pressure_hold", transmitter: "", stabilisation_s: 300, duration_s: 900, max_change_bar: 2 });
  if (state.mode !== "dynamic" || !state.integrity) {
    return (
      <div className="p-3 text-muted" data-testid="integrity-panel">
        Integrity tests run on the <span className="text-accent">dynamic</span> model (pressure evolves from the isolated volume's mass balance). Switch the
        model in the top bar.
      </div>
    );
  }
  const tests = [...state.integrity.tests].reverse();
  const running = tests.find((t) => ["stabilising", "holding", "stroking"].includes(t.phase));
  const valves = state.elements.filter((e): e is RestrictionSnapshot => (e.kind === "valve" || e.kind === "choke") && (e as RestrictionSnapshot).available);
  const presetReq = (p: IntegrityPreset): IntegrityRequest => ({
    type: p.type,
    name: p.name,
    test_node: p.test_node,
    transmitter: p.pressure_transmitter,
    valve: p.valve,
    stabilisation_s: p.stabilisation_s,
    duration_s: p.duration_s,
    max_change_bar: p.max_change_bar,
    stroke_tolerance_pct: p.stroke_tolerance_pct,
  });

  return (
    <div className="grid items-start gap-4 lg:grid-cols-2" data-testid="integrity-panel">
      {running && (
        <div className="lg:col-span-2">
          <RunningTest t={running} now={state.time_s} onAbort={onAbort} />
        </div>
      )}

      <section className="rounded-xl border border-line bg-panel shadow-[var(--shadow-card)]">
        <h3 className="flex items-center gap-1.5 border-b border-line px-4 py-2.5 t-eyebrow">
          <ShieldCheck size={12} /> Test procedures (illustrative limits)
        </h3>
        <ul className="divide-y divide-line/60">
          {(state.integrity_presets ?? []).map((p) => (
            <li key={p.id} className="px-4 py-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-[13px] font-semibold text-fg">{p.name}</div>
                  <div className="text-[12px] text-dim">
                    {p.type === "stroke"
                      ? `${p.valve} · limit ±${p.stroke_tolerance_pct}% of nominal`
                      : `${p.pressure_transmitter} · stabilise ${formatDuration(p.stabilisation_s)}, hold ${formatDuration(p.duration_s)}, limit ${p.max_change_bar} bar`}
                  </div>
                </div>
                <Button size="xs" variant="primary" disabled={!!running || state.status !== "running"} onClick={() => onStart(presetReq(p))} data-testid={`start-${p.id}`}>
                  Start
                </Button>
              </div>
              {p.description && <p className="mt-0.5 text-[12px] leading-snug text-muted">{p.description}</p>}
            </li>
          ))}
        </ul>
        {state.status !== "running" && <p className="px-2.5 pb-1.5 text-[12px] text-warn">Start the simulation to run tests (they evolve in simulated time).</p>}
      </section>

      <section className="rounded-xl border border-line bg-panel shadow-[var(--shadow-card)] p-4">
        <h3 className="mb-1.5 t-eyebrow">Custom test</h3>
        <div className="grid grid-cols-2 gap-1.5 text-[12.5px]">
          <label className="col-span-2 flex items-center justify-between gap-2">
            <span className="text-dim">Type</span>
            <Select value={custom.type} onChange={(e) => setCustom({ ...custom, type: e.target.value as IntegrityType })} aria-label="Test type">
              <option value="pressure_hold">Pressure hold (decay)</option>
              <option value="inflow">Inflow (build-up across barrier)</option>
              <option value="stroke">Stroke time</option>
            </Select>
          </label>
          {custom.type === "stroke" ? (
            <label className="col-span-2 flex items-center justify-between gap-2">
              <span className="text-dim">Valve</span>
              <Select value={custom.valve ?? ""} onChange={(e) => setCustom({ ...custom, valve: e.target.value })} aria-label="Valve">
                <option value="">select…</option>
                {valves.map((v) => (
                  <option key={v.tag} value={v.tag}>
                    {v.tag}
                  </option>
                ))}
              </Select>
            </label>
          ) : (
            <>
              <label className="col-span-2 flex items-center justify-between gap-2">
                <span className="text-dim">Monitor</span>
                <Select className="min-w-0 max-w-[230px]" value={custom.transmitter ?? ""} onChange={(e) => setCustom({ ...custom, transmitter: e.target.value })} aria-label="Pressure transmitter">
                  <option value="">select…</option>
                  {state.integrity.test_points.map((p) => (
                    <option key={p.transmitter} value={p.transmitter}>
                      {p.transmitter} — {p.description}
                    </option>
                  ))}
                </Select>
              </label>
              <NumField label="Stabilise [s]" v={custom.stabilisation_s ?? 0} set={(x) => setCustom({ ...custom, stabilisation_s: x })} />
              <NumField label="Hold [s]" v={custom.duration_s ?? 900} set={(x) => setCustom({ ...custom, duration_s: x })} />
              <NumField label="Limit [bar]" v={custom.max_change_bar ?? 2} set={(x) => setCustom({ ...custom, max_change_bar: x })} />
            </>
          )}
        </div>
        <Button
          className="mt-2 w-full"
          size="sm"
          variant="primary"
          disabled={!!running || state.status !== "running" || (custom.type === "stroke" ? !custom.valve : !custom.transmitter)}
          onClick={() => onStart(custom)}
        >
          Verify isolation & start
        </Button>
      </section>

      {tests.filter((t) => t !== running).length > 0 && (
        <section className="rounded-xl border border-line bg-panel shadow-[var(--shadow-card)] lg:col-span-2">
          <h3 className="border-b border-line px-4 py-2.5 t-eyebrow">Results</h3>
          <ul className="divide-y divide-line/60">
            {tests
              .filter((t) => t !== running)
              .map((t) => (
                <li key={t.id} className="px-4 py-3" data-testid={`result-${t.id}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[13px] font-semibold">{t.name}</span>
                    <Badge tone={PHASE_TONE[t.phase]}>{t.phase}</Badge>
                  </div>
                  {t.trace.length > 2 && <Trace t={t} />}
                  <p className="mt-0.5 text-[12px] leading-snug text-muted">{t.message}</p>
                </li>
              ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function NumField({ label, v, set }: { label: string; v: number; set: (x: number) => void }) {
  return (
    <label className="flex items-center justify-between gap-1">
      <span className="text-dim">{label}</span>
      <Input type="number" className="h-6 w-20" value={Number.isFinite(v) ? v : ""} onChange={(e) => set(e.target.valueAsNumber)} />
    </label>
  );
}

function RunningTest({ t, now, onAbort }: { t: IntegrityTestSnapshot; now: number; onAbort: (id: number) => Promise<boolean> }) {
  const total = t.type === "stroke" ? null : t.stabilisation_s + t.duration_s;
  const elapsed = now - t.started_s;
  const frac = total ? Math.min(1, elapsed / total) : null;
  const dp = t.p_hold_start_pa != null && t.p_now_pa != null ? (t.p_now_pa - t.p_hold_start_pa) / 1e5 : null;
  return (
    <section className="rounded-xl border border-warn/30 bg-[#fffbeb] p-4" data-testid="running-test">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Timer size={13} className="text-warn" />
          <span className="text-[13px] font-bold">{t.name}</span>
        </div>
        <Badge tone={PHASE_TONE[t.phase]}>{t.phase}</Badge>
      </div>
      {frac !== null && (
        <div className="my-1.5 h-1.5 w-full overflow-hidden rounded-full bg-line">
          <div className="h-full bg-warn transition-[width]" style={{ width: `${frac * 100}%` }} />
        </div>
      )}
      <div className="grid grid-cols-3 gap-1 text-center text-[12px]">
        <div>
          <div className="text-dim">Elapsed</div>
          <div className="num">{formatDuration(elapsed)}</div>
        </div>
        <div>
          <div className="text-dim">{t.transmitter ?? t.valve}</div>
          <div className="num">{t.p_now_pa != null ? `${fmt(t.p_now_pa / 1e5, 2)} bara` : "—"}</div>
        </div>
        <div>
          <div className="text-dim">ΔP in hold</div>
          <div className={`num ${dp !== null && Math.abs(dp) > t.max_change_bar ? "text-bad" : ""}`}>{dp !== null ? `${dp >= 0 ? "+" : ""}${fmt(dp, 2)} bar` : "—"}</div>
        </div>
      </div>
      {t.trace.length > 2 && <Trace t={t} />}
      <p className="mt-1 text-[12px] text-muted">{t.message}</p>
      <Button size="xs" variant="bad" className="mt-1" onClick={() => onAbort(t.id)}>
        <Square size={10} /> Abort
      </Button>
    </section>
  );
}

/** Pressure trace recorded by the backend during the test, with the acceptance band. */
function Trace({ t }: { t: IntegrityTestSnapshot }) {
  const W = 300;
  const H = 70;
  const pts = t.trace;
  const t0 = pts[0][0];
  const t1 = Math.max(pts[pts.length - 1][0], t0 + 1);
  const ps = pts.map((p) => p[1]);
  const ref = t.p_hold_start_pa != null ? t.p_hold_start_pa / 1e5 : null;
  const lo = Math.min(...ps, ...(ref !== null ? [ref - t.max_change_bar] : []));
  const hi = Math.max(...ps, ...(ref !== null ? [ref + t.max_change_bar] : []));
  const span = Math.max(hi - lo, 0.1);
  const X = (x: number) => ((x - t0) / (t1 - t0)) * W;
  const Y = (y: number) => H - 4 - ((y - lo) / span) * (H - 8);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(" ");
  const limit = ref !== null ? (t.type === "pressure_hold" ? ref - t.max_change_bar : ref + t.max_change_bar) : null;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mt-1 h-[70px] w-full rounded-md bg-bg" aria-label="test pressure trace">
      {t.hold_start_s != null && <line x1={X(t.hold_start_s)} x2={X(t.hold_start_s)} y1={0} y2={H} stroke="#56667a" strokeDasharray="3 3" />}
      {limit !== null && <line x1={0} x2={W} y1={Y(limit)} y2={Y(limit)} stroke="#ef4444" strokeOpacity={0.7} strokeDasharray="5 3" />}
      {ref !== null && <line x1={0} x2={W} y1={Y(ref)} y2={Y(ref)} stroke="#56667a" strokeOpacity={0.6} />}
      <path d={d} fill="none" stroke="#38bdf8" strokeWidth={1.6} />
      <text x={4} y={10} fontSize={8} fill="#7d8da1" className="num">
        {fmt(hi, 1)}
      </text>
      <text x={4} y={H - 2} fontSize={8} fill="#7d8da1" className="num">
        {fmt(lo, 1)} bara
      </text>
    </svg>
  );
}
