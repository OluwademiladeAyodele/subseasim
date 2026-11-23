/**
 * API RP 14E erosional-velocity screening at the gallery, the choke outlet
 * bore and the flowline (Choke health page). A supplementary indicator for
 * clean service; the DNV-RP-O501 sand-erosion results govern.
 */
import { Gauge } from "lucide-react";

import { Badge, Panel } from "@/components/ui/primitives";
import { fmt } from "@/lib/units";
import type { ErosionalVelocityResult } from "@/types/sand";

export function ErosionalVelocityPanel({ ev }: { ev: ErosionalVelocityResult | undefined }) {
  if (!ev) return null;
  if (!ev.available) {
    return (
      <Panel title="Erosional velocity (API RP 14E)" icon={<Gauge size={16} />} className="xl:col-span-3">
        <p className="text-[13px] text-muted">{ev.reason}</p>
      </Panel>
    );
  }
  return (
    <Panel title="Erosional velocity (API RP 14E)" icon={<Gauge size={16} />} className="xl:col-span-3"
      subtitle={`${ev.status} · C = ${fmt(ev.c_factor, 0)} (${ev.c_source ?? "source not given"})`}
      right={<Badge tone={ev.any_exceeded ? "warn" : "ok"} data-testid="api14e-status">{ev.any_exceeded ? "Above Ve" : "Below Ve"}</Badge>}>
      <div className="overflow-x-auto" data-testid="api14e">
        <table className="w-full min-w-[620px] text-[12.5px]">
          <thead>
            <tr className="text-left text-dim">
              <th className="py-1 font-medium">Location</th>
              <th className="py-1 text-right font-medium">Mixture velocity</th>
              <th className="py-1 text-right font-medium">Mixture density</th>
              <th className="py-1 text-right font-medium">Ve</th>
              <th className="py-1 text-right font-medium">u / Ve</th>
            </tr>
          </thead>
          <tbody>
            {ev.locations?.map((r) => (
              <tr key={r.key} className="border-t border-line" data-testid={`api14e-${r.key}`}>
                <td className="py-1">{r.label}</td>
                {r.available ? (
                  <>
                    <td className="num py-1 text-right">{fmt(r.u_mix_m_s, 2)} m/s</td>
                    <td className="num py-1 text-right">{fmt(r.rho_mix_kg_m3, 0)} kg/m³</td>
                    <td className="num py-1 text-right">{fmt(r.ve_m_s, 2)} m/s</td>
                    <td className={`num py-1 text-right font-semibold ${r.exceeded ? "text-warn" : ""}`}>{fmt(r.ratio, 2)}</td>
                  </>
                ) : (
                  <td colSpan={4} className="py-1 text-right text-warn">Unavailable: {r.missing} not entered</td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[12px] text-dim">{ev.method}.</p>
      {ev.notes?.map((n) => <p key={n} className={`mt-1 text-[12px] ${n.startsWith("Sand is present") ? "text-warn" : "text-dim"}`}>{n}</p>)}
    </Panel>
  );
}
