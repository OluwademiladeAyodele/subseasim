/**
 * Sand monitoring: the SDT-101 sand detector on the choke outlet (reading
 * against the simulated sand at the choke), and the sand source from the
 * formation through the screens to the choke. All values from the backend
 * sand model.
 */
import { Radar } from "lucide-react";

import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { Badge, Panel, Stat } from "@/components/ui/primitives";
import { fmt } from "@/lib/units";
import type { SandChokeResults } from "@/types/sand";

import { SandSourcePanel, Trend } from "./SandSource";

export function SandPage() {
  const { state, sim, go } = useWorkstation();
  const r = state.sand_choke as SandChokeResults | null | undefined;
  if (!r || !r.available || !r.sand) {
    return <PageBody><Panel title="Sand monitoring"><p className="text-[13px] text-muted">{r?.reason ?? "No sand model in this scenario."}</p></Panel></PageBody>;
  }
  const det = r.detector;
  const samples = sim.samples as unknown as Record<string, number | null>[];
  return (
    <PageBody intro="Sand is followed from the formation, through the sand screens, up the well to the choke, where SDT-101 measures it. It moves only with the simulated flow.">
      <div className="grid items-start gap-4 xl:grid-cols-3" data-testid="sand-page">
        {det && (
          <Panel title={`Sand detector ${det.tag}`} icon={<Radar size={16} />} subtitle={`${det.type.replace(/_/g, " ")} · ${det.location}`}
            right={<Badge tone={det.alarm ? "bad" : det.status === "OK" || det.status === "BELOW_DETECTION" ? "ok" : "warn"} data-testid="detector-status">{det.alarm ? "ALARM" : det.status}</Badge>}>
            <div className="grid grid-cols-2 gap-3">
              <Stat testId="detector-reading" label="Reading" value={det.reading_g_s == null ? "—" : fmt(det.reading_g_s, 3)} unit="g/s" tone={det.alarm ? "bad" : "accent"}
                sub={`≈ ${det.reading_g_s == null ? "—" : fmt(det.reading_g_s * 86.4, 2)} kg/d · ±${fmt(det.uncertainty_pct, 0)} % (k=2)`} />
              <Stat label="True at detector" value={fmt(det.true_g_s, 3)} unit="g/s" sub={`alarm at ${det.alarm_threshold_g_s} g/s`} />
            </div>
            <p className="mt-2 text-[12px] text-dim">
              Velocity at the detector {fmt(det.velocity_m_s, 2)} m/s. An acoustic detector needs flow velocity to hear the impacts and carries a calibration uncertainty, so
              its reading is not the true sand rate. Cumulative measured {fmt(det.cumulative_measured_kg, 2)} kg.
            </p>
          </Panel>
        )}
        {det && (
          <Panel title="Detector reading vs sand at the choke" className="xl:col-span-2">
            <Trend samples={samples} keys={["sand:detector_g_s", "sand:choke_g_s"]} labels={[`${det.tag} reading`, "simulated sand at choke"]} unit="g/s" />
          </Panel>
        )}
        <SandSourcePanel r={r} samples={samples} onInputs={() => go("sandinputs")} />
      </div>
    </PageBody>
  );
}
