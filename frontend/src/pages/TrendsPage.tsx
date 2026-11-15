import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { TrendsView } from "@/charts/TrendsView";

export function TrendsPage() {
  const { state, sim, prefs } = useWorkstation();
  return (
    <PageBody wide>
      <div className="overflow-hidden rounded-xl border border-line bg-panel shadow-[var(--shadow-card)]">
        <TrendsView state={state} samples={sim.samples} prefs={prefs} events={sim.events} />
      </div>
    </PageBody>
  );
}
