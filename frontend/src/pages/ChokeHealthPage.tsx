/**
 * Choke health & erosion: wear per criterion against the site allowances,
 * remaining life (P10 / P50 / P90) in days, sand and liquid produced,
 * measured Cv tracking, calibration from inspections, confidence and a
 * reasoned recommendation. All values from the backend erosion model.
 */
import { Activity, Gauge, Lightbulb, ListChecks, ShieldAlert, Wrench } from "lucide-react";
import { useState } from "react";

import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { Badge, Button, Input, Panel, Stat } from "@/components/ui/primitives";
import { fmt } from "@/lib/units";
import type { SandChokeResults, WearCriterion } from "@/types/sand";

import { Unavailable } from "./SandPage";

export const HEALTH_TONE: Record<string, "ok" | "info" | "warn" | "bad" | "fault" | "neutral"> = {
  Normal: "ok",
  "Elevated erosion risk": "info",
  "Increased wear": "warn",
  "Inspection recommended": "warn",
  "Changeout assessment required": "bad",
  "Critical condition": "fault",
  Unavailable: "neutral",
};

function life(c: WearCriterion) {
  if (!c.life_days) return c.allowance ? "no wear at present conditions" : "no allowance entered";
  const l = c.life_days;
  const f = (d: number) => (d > 3650 ? `${fmt(d / 365.25, 0)} y` : `${fmt(d, 0)} d`);
  return `${f(l.p10)} – ${f(l.p90)} (P50 ${f(l.p50)})`;
}

function Chart({ xs, ys, xl, yl, limit }: { xs: number[]; ys: number[]; xl: string; yl: string; limit?: number | null }) {
  if (xs.length < 2) return <p className="text-[12px] text-dim">No wear history yet.</p>;
  const W = 420, H = 140;
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const y1 = Math.max(...ys, limit ?? 0, 1e-9);
  const X = (v: number) => 34 + ((v - x0) / (x1 - x0 || 1)) * (W - 40);
  const Y = (v: number) => H - 18 - (v / y1) * (H - 26);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-[140px] w-full" aria-label={`${yl} vs ${xl}`}>
      <line x1={34} y1={H - 18} x2={W - 4} y2={H - 18} stroke="#cbd5e1" />
      <line x1={34} y1={6} x2={34} y2={H - 18} stroke="#cbd5e1" />
      {limit != null && <><line x1={34} x2={W - 4} y1={Y(limit)} y2={Y(limit)} stroke="#dc2626" strokeDasharray="5 3" /><text x={W - 6} y={Y(limit) - 3} textAnchor="end" fontSize={9} fill="#dc2626">allowance</text></>}
      <path d={xs.map((v, i) => `${i ? "L" : "M"}${X(v).toFixed(1)} ${Y(ys[i]).toFixed(1)}`).join(" ")} fill="none" stroke="#0369a1" strokeWidth={1.8} />
      <text x={34} y={H - 4} fontSize={9} fill="#64748b">{fmt(x0, 0)}</text>
      <text x={W - 4} y={H - 4} fontSize={9} fill="#64748b" textAnchor="end">{fmt(x1, 0)} {xl}</text>
      <text x={2} y={12} fontSize={9} fill="#64748b">{fmt(y1, 2)}</text>
      <text x={38} y={14} fontSize={9.5} fill="#0f172a">{yl}</text>
    </svg>
  );
}

export function ChokeHealthPage() {
  const { state, actions, go } = useWorkstation();
  const r = state.sand_choke as SandChokeResults | null | undefined;
  const [days, setDays] = useState("90");
  const [xAxis, setXAxis] = useState<"days" | "sand" | "liquid">("days");
  if (!r || !r.available || !r.health) {
    return <PageBody><Panel title="Choke health"><p className="text-[13px] text-muted">{r?.reason ?? "No choke erosion model in this scenario."}</p></Panel></PageBody>;
  }
  const h = r.health;
  const rec = r.recommendation!;
  const conf = r.confidence!;
  const crit = r.criteria ?? [];
  const gov = crit.find((c) => c.key === r.governing);
  const cvt = r.cv_tracking;
  const wh = r.wear_history!;
  const hole = crit.find((c) => c.key === "hole");
  const v = r.velocities ?? {};
  const missingAll = Object.entries(r.inputs_status ?? {}).flatMap(([k, s]) => s.missing.map((m) => `${k}: ${m}`));
  const daysNum = Number(days);
  return (
    <PageBody intro="Decision support for choke inspection and changeout. Wear is integrated from the simulated operating history; the forecast is a range, not a date.">
      <div className="grid items-start gap-4 xl:grid-cols-3" data-testid="choke-health-page">
        <Panel title="Choke health" icon={<ShieldAlert size={16} />} className="xl:col-span-2"
          right={<Badge tone={HEALTH_TONE[h.category] ?? "neutral"} data-testid="health-category">{h.category}</Badge>}>
          <div className="rounded-lg border border-line bg-panel-2 px-4 py-3" data-testid="recommendation">
            <div className="flex items-center gap-2 text-[14px] font-semibold"><Lightbulb size={15} className="text-accent" />{rec.title}</div>
            <p className="mt-1 text-[13px] leading-relaxed text-fg">{rec.text}</p>
            <h3 className="mb-1 mt-3 t-eyebrow">Why</h3>
            <ul className="list-disc space-y-0.5 pl-5 text-[12.5px] text-muted">{rec.reasons.map((x) => <li key={x}>{x}</li>)}</ul>
            <h3 className="mb-1 mt-3 t-eyebrow">Suggested actions</h3>
            <ul className="list-disc space-y-0.5 pl-5 text-[12.5px] text-muted">{rec.actions.map((x) => <li key={x}>{x}</li>)}</ul>
            <p className="mt-2 text-[11.5px] text-dim">{rec.disclaimer} {h.note}</p>
          </div>
          {h.category === "Unavailable" && missingAll.length > 0 && <div className="mt-3"><Unavailable items={missingAll} onInputs={() => go("sandinputs")} /></div>}
          <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Sand at the choke" value={fmt(r.sand?.at_choke_kg_d, 2)} unit="kg/d" tone="warn" />
            <Stat label="Jet velocity (vena contracta)" value={fmt(v.u_jet as number, 1)} unit="m/s" sub={v.critical_flow ? "critical (choked) flow" : "sub-critical"} />
            <Stat label="Trim service time" value={fmt(r.service_days, 1)} unit="days" />
            <Stat label="Most-consumed allowance" value={gov ? fmt((gov.consumed ?? 0) * 100, 1) : "—"} unit="%" sub={gov?.label} />
          </div>
        </Panel>

        <Panel title="Confidence" icon={<ListChecks size={16} />}>
          <Badge tone={conf.category.startsWith("validated") ? "ok" : conf.category.startsWith("calibrated") ? "info" : "warn"} data-testid="confidence">{conf.category}</Badge>
          <ul className="mt-2 list-disc space-y-0.5 pl-5 text-[12.5px] text-muted">{conf.factors.map((f) => <li key={f}>{f}</li>)}</ul>
          <h3 className="mb-1 mt-3 t-eyebrow">Uncertainty (1σ, log space)</h3>
          <ul className="text-[12.5px]">
            {Object.entries(r.uncertainty_components ?? {}).map(([k, s]) => (
              <li key={k} className="flex justify-between"><span className="text-muted">{k}</span><span className="num">× {fmt(Math.exp(s), 2)}</span></li>
            ))}
          </ul>
          <p className="mt-2 text-[12px] text-dim">P10–P90 life range = central estimate ÷/× exp(1.28 σ). Inspections narrow the erosion-model term; a measured sand rate narrows the sand term.</p>
        </Panel>

        <Panel title="Wear against allowances" icon={<Gauge size={16} />} className="xl:col-span-3" bodyClassName="overflow-x-auto">
          <table className="w-full min-w-[980px] text-[12.5px]" data-testid="criteria-table">
            <thead className="text-left text-muted">
              <tr className="border-b border-line">
                {["Criterion", "Used", "Allowance", "Consumed", "Rate now", "Remaining life (P10–P90)", "… in sand to the choke", "… in liquid produced"].map((x) => <th key={x} className="px-2 py-1.5 font-medium">{x}</th>)}
              </tr>
            </thead>
            <tbody className="num">
              {crit.map((c) => (
                <tr key={c.key} className={`border-b border-line/60 ${c.key === r.first_limit ? "bg-warn/[0.06]" : ""}`} data-testid={`criterion-${c.key}`}>
                  <td className="px-2 py-1 font-sans">{c.label}{c.key === r.first_limit && <Badge tone="warn" className="ml-2">first limit</Badge>}</td>
                  <td className="px-2 py-1">{fmt(c.used, 3)} {c.unit}</td>
                  <td className="px-2 py-1">{c.allowance == null ? "—" : `${c.allowance} ${c.unit}`}</td>
                  <td className="px-2 py-1">
                    {c.consumed == null ? "—" : (
                      <span className="flex items-center gap-2">
                        <span className="relative h-2 w-24 overflow-hidden rounded-full bg-panel-3">
                          <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${Math.min(100, c.consumed * 100)}%`, background: c.consumed > 0.75 ? "#dc2626" : c.consumed > 0.5 ? "#d97706" : "#0369a1" }} />
                        </span>
                        {fmt(c.consumed * 100, 1)} %
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-1">{fmt(c.rate_per_year, 3)} {c.unit}/yr</td>
                  <td className="px-2 py-1">{life(c)}</td>
                  <td className="px-2 py-1">{c.life_sand_kg == null ? "—" : `${fmt(c.life_sand_kg, 0)} kg`}</td>
                  <td className="px-2 py-1">{c.life_liquid_sm3 == null ? "—" : `${fmt(c.life_liquid_sm3 / 1000, 1)} kSm³`}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[12px] text-dim">Remaining life assumes the CURRENT sand rate, opening and differential continue; the "sand" and "liquid" columns remove the time assumption.</p>
        </Panel>

        <Panel title="Wear history" icon={<Activity size={16} />} className="xl:col-span-2"
          right={
            <div className="flex overflow-hidden rounded-md border border-line text-[12px]">
              {([["days", "service days"], ["sand", "sand kg"], ["liquid", "liquid Sm³"]] as const).map(([k, l]) => (
                <button key={k} type="button" onClick={() => setXAxis(k)} className={xAxis === k ? "bg-accent px-2 py-0.5 text-white" : "px-2 py-0.5 text-muted"}>{l}</button>
              ))}
            </div>
          }>
          <Chart xs={xAxis === "days" ? wh.service_days : xAxis === "sand" ? wh.sand_kg : wh.liquid_sm3} ys={wh.max_hole_mm}
            xl={xAxis === "days" ? "days" : xAxis === "sand" ? "kg sand" : "Sm³ liquid"} yl="max cage-hole increase (mm)" limit={hole?.allowance} />
          {r.erosion && r.erosion.rows.length > 0 && (
            <table className="mt-2 w-full text-[12.5px]">
              <thead className="text-left text-muted"><tr><th>Hole row (axial mm)</th><th>Ø new mm</th><th>Count</th><th>Increase mm</th><th>Rate mm/yr</th></tr></thead>
              <tbody className="num">
                {r.erosion.rows.map((x) => (
                  <tr key={x.axial_position_mm}><td>{x.axial_position_mm}</td><td>{x.diameter_mm}</td><td>{x.count}</td><td>{fmt(x.increase_mm, 4)}</td><td>{x.rate_mm_y == null ? "—" : fmt(x.rate_mm_y, 3)}</td></tr>
                ))}
              </tbody>
            </table>
          )}
          {r.erosion?.trim_material && (
            <p className="mt-2 text-[12px] text-dim">
              Trim {r.erosion.trim_material.name}: K {r.erosion.trim_material.k.toExponential(2)}, n {r.erosion.trim_material.n} ({r.erosion.trim_material.behaviour}; {r.erosion.trim_material.source}).
              Erosion ratio {r.erosion.erosion_ratio_kg_kg == null ? "—" : r.erosion.erosion_ratio_kg_kg.toExponential(2)} kg/kg sand; material loss {fmt(r.erosion.trim_volume_rate_mm3_d, 2)} mm³/day.
            </p>
          )}
        </Panel>

        <Panel title="Measured Cv tracking" icon={<Activity size={16} />} subtitle="MPFM flow & choke ΔP vs new-trim Cv at the same step">
          {cvt?.available ? (
            <div className="text-[12.5px]" data-testid="cv-tracking">
              <div className="flex items-baseline justify-between">
                <span className="num text-[22px] font-semibold">{(cvt.deviation_pct ?? 0) >= 0 ? "+" : ""}{fmt(cvt.deviation_pct, 1)} %</span>
                <Badge tone={cvt.significant ? "warn" : "ok"}>{cvt.significant ? "significant" : "within uncertainty"}</Badge>
              </div>
              <div className="text-muted">measurement uncertainty ± {fmt(cvt.uncertainty_pct, 1)} % (k=2)</div>
              {!!cvt.possible_causes?.length && (
                <>
                  <h3 className="mb-1 mt-2 t-eyebrow">Possible causes — check before concluding erosion</h3>
                  <ul className="list-disc space-y-0.5 pl-5 text-muted">{cvt.possible_causes.map((x) => <li key={x}>{x}</li>)}</ul>
                </>
              )}
              <p className="mt-2 text-[12px] text-dim">{cvt.note}</p>
            </div>
          ) : <p className="text-[12.5px] text-dim">{cvt?.note}</p>}
        </Panel>

        <Panel title="Calibration from inspections" icon={<Wrench size={16} />} className="xl:col-span-2">
          <div className="text-[12.5px]">
            Trim erosion factor: <span className="num font-semibold">× {fmt(r.calibration?.factor_median, 2)}</span>, uncertainty ×÷ {fmt(Math.exp((r.calibration?.sigma_ln ?? 0) * 1.28), 2)} (P10–P90)
            {" "}(prior ×÷ {fmt(Math.exp((r.calibration?.prior_sigma_ln ?? 0) * 1.28), 2)}).
          </div>
          {r.calibration?.points.length ? (
            <table className="mt-2 w-full text-[12.5px]">
              <thead className="text-left text-muted"><tr><th>Inspection</th><th>Service days</th><th>Used</th><th>Measured / predicted</th><th>Note</th></tr></thead>
              <tbody>
                {r.calibration.points.map((p) => (
                  <tr key={p.label + p.service_days}><td>{p.label}</td><td className="num">{fmt(p.service_days, 0)}</td><td>{p.used ? "yes" : "no"}</td><td className="num">{p.ratio == null ? "—" : fmt(p.ratio, 2)}</td><td className="text-dim">{p.note}</td></tr>
                ))}
              </tbody>
            </table>
          ) : <p className="mt-2 text-[12.5px] text-dim">No inspections recorded. Add measured hole sizes, Cv change or plug loss on the inputs page to calibrate the model to your choke.</p>}
          <Button size="xs" className="mt-2" onClick={() => go("sandinputs")}>Edit inputs / inspections</Button>
        </Panel>

        <Panel title="Project operating time" icon={<Activity size={16} />}>
          <p className="text-[12.5px] text-muted">Integrate wear and cumulative sand for a period at the CURRENT operating point (quasi-steady: sand rate, opening and differential held constant).</p>
          <div className="mt-2 flex items-center gap-2">
            <Input aria-label="Fast-forward days" inputMode="decimal" value={days} onChange={(e) => setDays(e.target.value)} className="w-24" />
            <span className="text-[12.5px] text-dim">days</span>
            <Button size="sm" variant="primary" disabled={!(daysNum > 0 && daysNum <= 3650)} onClick={() => actions.sandFastForward(daysNum)} data-testid="fast-forward">Fast-forward</Button>
          </div>
          <h3 className="mb-1 mt-3 t-eyebrow">Model limitations</h3>
          <ul className="list-disc space-y-0.5 pl-5 text-[12px] text-dim">{r.limitations?.map((x) => <li key={x}>{x}</li>)}</ul>
        </Panel>
      </div>
    </PageBody>
  );
}
