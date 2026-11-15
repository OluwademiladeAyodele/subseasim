import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { TrainingPanel } from "@/training/TrainingPanel";

export function TrainingPage() {
  const { sim, exercises, actions, select } = useWorkstation();
  return (
    <PageBody intro="Guided exercises load their own scenario, judge each task from the simulation state, and explain the results using the values your run produced.">
      <div className="mx-auto max-w-3xl overflow-hidden rounded-xl border border-line bg-panel shadow-[var(--shadow-card)]">
        <TrainingPanel
          training={sim.training}
          exercises={exercises}
          onStart={(id) => {
            select(null);
            actions.trainingStart(id);
          }}
          onAnswer={actions.trainingAnswer}
          onAdvance={actions.trainingAdvance}
          onStop={actions.trainingStop}
        />
      </div>
    </PageBody>
  );
}
