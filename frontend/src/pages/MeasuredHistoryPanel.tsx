/**
 * Measured sand history trend (Sand monitoring page): records converted to
 * kg/d by the backend, the abnormal-increase review trigger and which record
 * drives the erosion model.
 */
import { History } from "lucide-react";

import { Badge, Button, Panel } from "@/components/ui/primitives";
import { fmt } from "@/lib/units";
import type { MeasuredHistory } from "@/types/sand";

const METHOD_LABEL: Record<string, string> = {
  sand_trap: "sand trap", acoustic_detector: "acoustic detector", intrusive_probe: "intrusive probe", well_test_sample: "well-test sample", other: "other",
};

function Chart({ pts, baseline }: { pts: { t: number; v: number }[]; baseline: number | null }) {
  const W = 600, H = 120;
  const t0 = pts[0].t, t1 = pts[pts.length - 1].t;
  const hi = Math.max(...pts.map((p) => p.v), baseline ?? 0) * 1.1 || 1;
  const x = (t: number) => 8 + ((t - t0) / (t1 - t0 || 1)) * (W - 16);
  const y = (v: number) => H - 6 - (v / hi) * (H - 14);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-[120px] w-full" preserveAspectRatio="none" role="img" aria-label="Measured sand rate history">
      {baseline != null && <line x1={0} x2={W} y1={y(baseline)} y2={y(baseline)} stroke="#94a3b8" strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />}
      <path fill="none" stroke="#0369a1" strokeWidth={1.6} vectorEffect="non-scaling-stroke" d={pts.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)} ${y(p.v).toFixed(1)}`).join(" ")} />
      {pts.map((p, i) => <circle key={i} cx={x(p.t)} cy={y(p.v)} r={2.5} fill={i === pts.length - 1 ? "#d97706" : "#0369a1"} />)}
    </svg>
  );
}

export function MeasuredHistoryPanel({ h, onInputs }: { h: MeasuredHistory | undefined; onInputs: () => void }) {
  if (!h) return null;
  const pts = h.series.filter((s) => s.kg_d != null).map((s) => ({ t: Date.parse(s.timestamp), v: s.kg_d as number }));
  const a = h.abnormal;
  return (
    <Panel title="Measured sand history" icon={<History size={16} />} className="xl:col-span-3"
      subtitle={h.drives_model && h.driving_record
        ? `Drives the erosion model: ${h.driving_record.value} ${h.driving_record.unit_label} (${METHOD_LABEL[h.driving_record.method] ?? h.driving_record.method}, ${h.driving_record.timestamp.slice(0, 10)})`
        : h.mode === "measured" ? "Measured mode without a history: the single measured value is used" : "Predictive mode: history trended and checked, not used by the model"}
      right={a.available ? <Badge tone={a.flag ? "bad" : "ok"} data-testid="abnormal-status">{a.flag ? "ABNORMAL INCREASE" : "No abnormal increase"}</Badge> : undefined}>
      {h.count === 0 ? (
        <div className="text-[13px] text-muted" data-testid="no-measurements">
          No measured sand records. Import sand-trap, detector or well-test data as CSV on the inputs page.
          <div><Button size="xs" className="mt-2" onClick={onInputs}>Enter measurements</Button></div>
        </div>
      ) : (
        <div data-testid="measured-history">
          {pts.length >= 2 ? <Chart pts={pts} baseline={a.baseline_kg_d} /> : <p className="text-[12px] text-dim">Need two records converted to kg/d for a trend.</p>}
          <div className="flex flex-wrap gap-4 text-[12px] text-muted">
            <span><span className="mr-1 inline-block h-0.5 w-4 bg-[#0369a1] align-middle" />measured, kg/d</span>
            {a.baseline_kg_d != null && <span><span className="mr-1 inline-block h-0.5 w-4 border-t border-dashed border-[#94a3b8] align-middle" />baseline median {fmt(a.baseline_kg_d, 2)} kg/d</span>}
            <span>{h.count} records</span>
          </div>
          <p className={`mt-2 text-[12.5px] ${a.flag ? "font-semibold text-bad" : "text-muted"}`} data-testid="abnormal-text">{a.text}</p>
          <p className="text-[12px] text-dim">{h.trigger_note} Trigger: {fmt(a.trigger_ratio, 1)} × median of the previous {a.baseline_count}{a.min_increase_kg_d != null ? `, at least +${fmt(a.min_increase_kg_d, 2)} kg/d` : ""}.</p>
          {h.notes.map((n) => <p key={n} className="text-[12px] text-warn">{n}</p>)}
        </div>
      )}
    </Panel>
  );
}
