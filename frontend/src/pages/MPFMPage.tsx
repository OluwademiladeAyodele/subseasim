/**
 * MPFM monitoring: measured vs true (simulated) phase rates, measurement
 * uncertainty, raw signals, diagnostics, calibration and instructor faults.
 * The meter's readings come from the backend measurement model; the "true"
 * column is the simulated process value at the meter - shown so interns see
 * that an instrument reading is not the process value.
 */
import { Activity, FlaskConical, Gauge, Settings2, ShieldAlert, Wrench } from "lucide-react";
import { useState } from "react";

import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { Badge, Button, Input, Panel } from "@/components/ui/primitives";
import { fmt, kToC, paToBara } from "@/lib/units";
import type { MPFMSnapshot, MPFMValues } from "@/types/simulation";

export const QUALITY_TONE = { GOOD: "ok", DEGRADED: "warn", BAD: "bad", NOT_READY: "neutral", NOT_MODELLED: "neutral" } as const;

type Row = { key: keyof MPFMValues; label: string; unit: string; digits: number; scale?: number; ukey?: string; abs?: boolean };

const STD_ROWS: Row[] = [
  { key: "oil_sm3_d", label: "Oil", unit: "Sm³/d", digits: 1, ukey: "oil_sm3_d" },
  { key: "gas_sm3_d", label: "Gas", unit: "kSm³/d", digits: 2, scale: 1e-3, ukey: "gas_sm3_d" },
  { key: "water_sm3_d", label: "Water", unit: "Sm³/d", digits: 1, ukey: "water_sm3_d" },
  { key: "liquid_sm3_d", label: "Total liquid", unit: "Sm³/d", digits: 1, ukey: "liquid_sm3_d" },
];
const LINE_ROWS: Row[] = [
  { key: "oil_m3_d", label: "Oil", unit: "m³/d", digits: 1 },
  { key: "gas_m3_d", label: "Gas", unit: "m³/d", digits: 1 },
  { key: "water_m3_d", label: "Water", unit: "m³/d", digits: 1 },
  { key: "liquid_m3_d", label: "Total liquid", unit: "m³/d", digits: 1 },
];
const MIX_ROWS: Row[] = [
  { key: "mass_kg_s", label: "Total mass flow", unit: "kg/s", digits: 3, ukey: "mass_kg_s" },
  { key: "mixture_density_kg_m3", label: "Mixture density (in-situ)", unit: "kg/m³", digits: 1 },
  { key: "water_cut", label: "Water cut", unit: "%", digits: 2, scale: 100, ukey: "water_cut_abs_pct", abs: true },
  { key: "gor_sm3_sm3", label: "Gas-oil ratio", unit: "Sm³/Sm³", digits: 1 },
  { key: "gvf", label: "Gas volume fraction", unit: "%", digits: 2, scale: 100 },
  { key: "lvf", label: "Liquid volume fraction", unit: "%", digits: 2, scale: 100 },
];

function CompareTable({ m, rows, title, testId }: { m: MPFMSnapshot; rows: Row[]; title: string; testId?: string }) {
  return (
    <div>
      <h3 className="mb-1 t-eyebrow">{title}</h3>
      <table className="w-full text-[12.5px]" data-testid={testId}>
        <thead className="text-left text-muted">
          <tr className="border-b border-line">
            {["", "Measured (MPFM)", "True (simulated)", "Difference", "Uncertainty (k=2)"].map((h) => (
              <th key={h} className="px-2 py-1.5 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="num">
          {rows.map((r) => {
            const sc = r.scale ?? 1;
            const meas = m.measured?.[r.key];
            const tru = m.true?.[r.key];
            const d = meas != null && tru != null ? meas - tru : null;
            const rel = d != null && tru ? (d / tru) * 100 : null;
            const u = r.ukey ? m.uncertainty_pct?.[r.ukey] : undefined;
            const outside = u != null && (r.abs ? d != null && Math.abs(d * 100) > u : rel != null && Math.abs(rel) > u);
            return (
              <tr key={r.key} className="border-b border-line/60" data-testid={testId ? `${testId}-${r.key}` : undefined}>
                <td className="px-2 py-1 font-sans text-fg">
                  {r.label} <span className="text-dim">{r.unit}</span>
                </td>
                <td className="px-2 py-1 font-semibold">{meas == null ? "—" : fmt(meas * sc, r.digits)}</td>
                <td className="px-2 py-1 text-muted">{tru == null ? "—" : fmt(tru * sc, r.digits)}</td>
                <td className={`px-2 py-1 ${outside ? "font-semibold text-bad" : "text-muted"}`}>
                  {d == null ? "—" : `${d >= 0 ? "+" : ""}${fmt(d * sc, r.digits)}`}
                  {!r.abs && rel != null && Math.abs(tru ?? 0) > 1e-9 ? ` (${rel >= 0 ? "+" : ""}${fmt(rel, 1)} %)` : ""}
                </td>
                <td className="px-2 py-1 text-muted">{u == null ? "—" : r.abs ? `± ${fmt(u, 2)} %-pts` : `± ${fmt(u, 1)} %`}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Spark({ samples, field, label, scale = 1, unit }: { samples: Record<string, number | null>[]; field: string; label: string; scale?: number; unit: string }) {
  const pts = samples.filter((s) => s[`mpfm_true:${field}`] != null).slice(-240);
  if (pts.length < 2) return <p className="text-[12px] text-dim">{label}: collecting data…</p>;
  const ts = pts.map((s) => s.t as number);
  const vals = pts.flatMap((s) => [s[`mpfm:${field}`], s[`mpfm_true:${field}`]]).filter((v): v is number => v != null).map((v) => v * scale);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const span = hi - lo || Math.max(Math.abs(hi), 1) * 0.01;
  const W = 300;
  const H = 54;
  const x = (t: number) => ((t - ts[0]) / (ts[ts.length - 1] - ts[0] || 1)) * W;
  const y = (v: number) => H - 4 - ((v * scale - lo) / span) * (H - 8);
  const line = (key: string) =>
    pts.filter((s) => s[key] != null).map((s, i) => `${i ? "L" : "M"}${x(s.t as number).toFixed(1)} ${y(s[key] as number).toFixed(1)}`).join(" ");
  return (
    <div>
      <div className="flex justify-between text-[12px]">
        <span className="font-medium text-fg">{label}</span>
        <span className="num text-dim">
          {fmt(lo, 1)} – {fmt(hi, 1)} {unit}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-[54px] w-full" preserveAspectRatio="none" aria-label={`${label} trend`}>
        <path d={line(`mpfm_true:${field}`)} fill="none" stroke="#94a3b8" strokeWidth={2} strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />
        <path d={line(`mpfm:${field}`)} fill="none" stroke="#0369a1" strokeWidth={1.6} vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  );
}

function Faults({ m }: { m: MPFMSnapshot }) {
  const { actions } = useWorkstation();
  const f = m.faults!;
  const [off, setOff] = useState(String(f.dp_offset_bar));
  const toggles: { key: "dp_stuck" | "gamma_failed" | "pt_failed"; label: string }[] = [
    { key: "dp_stuck", label: "dP transmitter stuck" },
    { key: "gamma_failed", label: "Gamma detector failed" },
    { key: "pt_failed", label: "P/T transmitter failed" },
  ];
  const offNum = Number(off);
  return (
    <div className="space-y-2" data-testid="mpfm-faults">
      {toggles.map((t) => (
        <label key={t.key} className="flex items-center justify-between gap-2">
          <span className="text-muted">{t.label}</span>
          <Button size="xs" variant={f[t.key] ? "bad" : "default"} aria-label={`${t.label} ${f[t.key] ? "clear" : "inject"}`}
            onClick={() => actions.mpfmFaults({ [t.key]: !f[t.key] })}>
            {f[t.key] ? "Active — clear" : "Inject"}
          </Button>
        </label>
      ))}
      <label className="grid grid-cols-[1fr_80px_auto] items-center gap-2">
        <span className="text-muted">dP zero offset</span>
        <Input aria-label="dP zero offset" inputMode="decimal" value={off} onChange={(e) => setOff(e.target.value)} aria-invalid={!Number.isFinite(offNum) || Math.abs(offNum) > 1} />
        <Button size="xs" disabled={!Number.isFinite(offNum) || Math.abs(offNum) > 1} onClick={() => actions.mpfmFaults({ dp_offset_bar: offNum })}>
          Set bar
        </Button>
      </label>
      <p className="text-[12px] text-dim">Instructor faults change only the SIGNALS the meter receives; the process is unaffected. Calibration re-zeros the dP transmitter.</p>
    </div>
  );
}

/** Compact MPFM summary (inspector). */
export function MPFMSummary({ m, onOpen }: { m: MPFMSnapshot; onOpen?: () => void }) {
  if (m.quality === "NOT_MODELLED")
    return <p className="p-3 text-[13px] text-muted">{m.tag}: {m.reason}</p>;
  const meas = m.measured;
  return (
    <div className="p-3" data-testid="mpfm-summary">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="num text-base font-bold">{m.tag}</div>
          <div className="text-muted">{m.name}</div>
        </div>
        <Badge tone={QUALITY_TONE[m.quality]}>{m.quality}</Badge>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        {(["oil_sm3_d", "gas_sm3_d", "water_sm3_d"] as const).map((k) => (
          <div key={k} className="rounded-lg border border-line px-2 py-1.5">
            <div className="text-[11px] text-muted">{k === "oil_sm3_d" ? "Oil Sm³/d" : k === "gas_sm3_d" ? "Gas kSm³/d" : "Water Sm³/d"}</div>
            <div className="num text-[15px] font-semibold">{meas ? fmt(k === "gas_sm3_d" ? meas[k] / 1000 : meas[k], k === "gas_sm3_d" ? 1 : 0) : "—"}</div>
            <div className="num text-[11px] text-dim">± {fmt(m.uncertainty_pct?.[k], 1)} %</div>
          </div>
        ))}
      </div>
      <div className="mt-2 text-[12.5px] text-muted">
        WC {meas ? fmt(meas.water_cut * 100, 1) : "—"} % · GOR {meas ? fmt(meas.gor_sm3_sm3, 0) : "—"} · GVF {meas ? fmt(meas.gvf * 100, 1) : "—"} %
      </div>
      {!!m.flags?.length && (
        <ul className="mt-2 space-y-1 text-[12px]">
          {m.flags.map((f) => <li key={f.code} className={f.severity === "error" ? "text-bad" : "text-warn"}>{f.message}</li>)}
        </ul>
      )}
      {onOpen && (
        <Button size="sm" className="mt-3 w-full" onClick={onOpen}>
          Open MPFM monitoring
        </Button>
      )}
    </div>
  );
}

export function MPFMPage() {
  const { state, sim, actions } = useWorkstation();
  const m = state.mpfm;
  if (!m) return <PageBody><p className="text-dim">This scenario has no multiphase flow meter configured.</p></PageBody>;
  if (m.quality === "NOT_MODELLED")
    return (
      <PageBody>
        <Panel title={m.tag} icon={<Gauge size={16} />}>
          <p className="text-[13px] text-muted">{m.reason} Switch the fluid model on the Conditions or Multiphase page.</p>
          <Button size="sm" className="mt-3" onClick={() => actions.fluidModel("black_oil")}>Switch to three-phase</Button>
        </Panel>
      </PageBody>
    );
  const sg = m.signals!;
  const samples = sim.samples as unknown as Record<string, number | null>[];
  const pvtMismatch = m.meter_pvt && m.true_fluid && (Math.abs(m.meter_pvt.water_salinity_wt_pct - m.true_fluid.water_salinity_wt_pct) > 0.05 ||
    Math.abs(m.meter_pvt.oil_api - m.true_fluid.oil_api) > 0.05 || Math.abs(m.meter_pvt.gas_specific_gravity - m.true_fluid.gas_specific_gravity) > 0.001);
  const budget = m.uncertainty_budget?.liquid_sm3_d;
  return (
    <PageBody intro={`${m.principle}. ${m.reference_conditions}`}>
      <div className="grid gap-4 xl:grid-cols-3" data-testid="mpfm-page">
        <Panel title={`${m.tag} — ${m.name}`} icon={<Gauge size={16} />} className="xl:col-span-2"
          right={<Badge tone={QUALITY_TONE[m.quality]} data-testid="mpfm-quality">{m.quality}</Badge>}>
          <div className="space-y-4">
            {!!m.flags?.length && (
              <ul className="space-y-1 rounded-lg border border-warn/40 bg-warn/[0.06] px-3 py-2 text-[12.5px]" data-testid="mpfm-flags">
                {m.flags.map((f) => (
                  <li key={f.code} className={f.severity === "error" ? "text-bad" : f.severity === "warning" ? "text-warn" : "text-muted"}>
                    <span className="num font-semibold">{f.code}</span> — {f.message}
                  </li>
                ))}
              </ul>
            )}
            <CompareTable m={m} rows={STD_ROWS} title="Production at standard conditions (15 °C, 1.01325 bar)" testId="mpfm-std" />
            <CompareTable m={m} rows={LINE_ROWS} title={`Actual volumes at meter conditions (${fmt(sg.p_pa != null ? paToBara(sg.p_pa) : null, 1)} bara, ${fmt(sg.t_k != null ? kToC(sg.t_k) : null, 1)} °C)`} />
            <CompareTable m={m} rows={MIX_ROWS} title="Mixture" />
            <p className="text-[12px] text-dim">
              Differences in <span className="font-semibold text-bad">red</span> exceed the meter's stated uncertainty — a systematic error (fault, calibration or
              PVT mismatch) rather than noise. Without a fault the meter reports GOOD even when its configuration no longer matches the fluid: it cannot know.
            </p>
          </div>
        </Panel>

        <div className="flex flex-col gap-4">
          <Panel title="Trend — measured vs true" icon={<Activity size={16} />} subtitle="solid: MPFM · dashed: simulated true value">
            <div className="space-y-3">
              <Spark samples={samples} field="oil_sm3_d" label="Oil" unit="Sm³/d" />
              <Spark samples={samples} field="gas_sm3_d" label="Gas" scale={1e-3} unit="kSm³/d" />
              <Spark samples={samples} field="water_sm3_d" label="Water" unit="Sm³/d" />
              <Spark samples={samples} field="water_cut" label="Water cut" scale={100} unit="%" />
            </div>
          </Panel>
          <Panel title="Calibration" icon={<Wrench size={16} />}>
            <div className="space-y-1 text-[12.5px]">
              <div className="flex justify-between"><span className="text-muted">Since last calibration</span><span className="num">{fmt(m.calibration?.days_since, 2)} d (interval {fmt(m.calibration?.interval_days, 0)} d)</span></div>
              <div className="flex justify-between"><span className="text-muted">Actual discharge coefficient</span><span className="num">{fmt(m.calibration?.cd_actual, 4)} (nominal {fmt(m.geometry?.discharge_coefficient, 4)})</span></div>
            </div>
            <Button size="sm" className="mt-3 w-full" variant="primary" onClick={() => actions.mpfmCalibrate()} data-testid="mpfm-calibrate">
              Calibrate (dP zero check + fluid sample)
            </Button>
          </Panel>
        </div>

        <Panel title="Raw signals and phase fractions" icon={<ShieldAlert size={16} />}>
          <table className="w-full text-[12.5px]">
            <tbody className="num">
              {[
                ["Venturi dP", sg.dp_pa != null ? `${fmt(sg.dp_pa / 100, 1)} mbar` : "—", sg.true_dp_pa != null ? `${fmt(sg.true_dp_pa / 100, 1)} mbar` : "—"],
                ["Pressure", sg.p_pa != null ? `${fmt(paToBara(sg.p_pa), 2)} bara` : "—", sg.true_p_pa != null ? `${fmt(paToBara(sg.true_p_pa), 2)} bara` : "—"],
                ["Temperature", sg.t_k != null ? `${fmt(kToC(sg.t_k), 2)} °C` : "—", sg.true_t_k != null ? `${fmt(kToC(sg.true_t_k), 2)} °C` : "—"],
                ["Gamma attenuation, low energy", fmt(sg.attenuation_low, 4), ""],
                ["Gamma attenuation, high energy", fmt(sg.attenuation_high, 4), ""],
              ].map(([k, a, b]) => (
                <tr key={k} className="border-b border-line/60">
                  <td className="py-1 font-sans text-muted">{k}</td>
                  <td className="py-1 text-right font-semibold">{a}</td>
                  <td className="py-1 pl-3 text-right text-dim">{b && `true ${b}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {m.phase_fractions && (
            <div className="mt-3 text-[12.5px]">
              <h3 className="mb-1 t-eyebrow">In-situ phase fractions (gamma)</h3>
              {(["oil", "gas", "water"] as const).map((k) => (
                <div key={k} className="flex items-center gap-2 py-0.5">
                  <span className="w-12 capitalize text-muted">{k}</span>
                  <span className="relative h-2 flex-1 overflow-hidden rounded-full bg-panel-3">
                    <span className="absolute inset-y-0 left-0 rounded-full bg-accent" style={{ width: `${(m.phase_fractions!.measured[k] ?? 0) * 100}%` }} />
                  </span>
                  <span className="num w-16 text-right">{fmt(m.phase_fractions!.measured[k] * 100, 1)} %</span>
                </div>
              ))}
              <p className="mt-1 text-[12px] text-dim">
                True in-situ gas fraction {fmt((m.phase_fractions.true_gas_void_fraction ?? 0) * 100, 1)} % (gas slips past the liquid: lower than the
                flowing gas volume fraction). Meter slip model: {m.meter_slip_model}.
              </p>
            </div>
          )}
        </Panel>

        <Panel title="Uncertainty budget — total liquid" icon={<Settings2 size={16} />} subtitle="1-sigma contribution of each input, % of reading">
          {budget ? (
            <ul className="space-y-1 text-[12.5px]">
              {Object.entries(budget).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                <li key={k} className="flex items-center gap-2">
                  <span className="w-36 text-muted">{k}</span>
                  <span className="relative h-2 flex-1 overflow-hidden rounded-full bg-panel-3">
                    <span className="absolute inset-y-0 left-0 rounded-full bg-warn" style={{ width: `${Math.min(100, (v / Math.max(...Object.values(budget), 1e-9)) * 100)}%` }} />
                  </span>
                  <span className="num w-14 text-right">{fmt(v, 2)}</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-dim">No valid measurement.</p>}
          <p className="mt-2 text-[12px] text-dim">First-order (GUM) propagation through the flow computer, plus a slip / flow-regime term that grows with GVF. Expanded with k = 2 in the tables.</p>
        </Panel>

        <Panel title="Meter configuration vs fluid" icon={<FlaskConical size={16} />}>
          <table className="w-full text-[12.5px]">
            <thead className="text-left text-muted"><tr><th></th><th className="py-1">Meter PVT</th><th className="py-1">Actual fluid</th></tr></thead>
            <tbody className="num">
              {[
                ["Oil gravity °API", m.meter_pvt?.oil_api, m.true_fluid?.oil_api, 1],
                ["Gas specific gravity", m.meter_pvt?.gas_specific_gravity, m.true_fluid?.gas_specific_gravity, 3],
                ["Water salinity wt%", m.meter_pvt?.water_salinity_wt_pct, m.true_fluid?.water_salinity_wt_pct, 2],
              ].map(([k, a, b, d]) => (
                <tr key={k as string} className="border-t border-line/60">
                  <td className="py-1 font-sans text-muted">{k}</td>
                  <td className={`py-1 ${Math.abs((a as number) - (b as number)) > 1e-3 ? "font-semibold text-bad" : ""}`}>{fmt(a as number, d as number)}</td>
                  <td className="py-1">{fmt(b as number, d as number)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {pvtMismatch && <p className="mt-2 text-[12px] text-bad" data-testid="mpfm-pvt-mismatch">The meter's PVT no longer matches the fluid — readings are biased. Calibrate with a fresh sample.</p>}
          <p className="mt-2 text-[12px] text-dim">{m.sand_effect}</p>
        </Panel>

        <Panel title="Instructor faults" icon={<ShieldAlert size={16} />}>
          <Faults m={m} />
        </Panel>
      </div>
    </PageBody>
  );
}
