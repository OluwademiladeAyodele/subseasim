import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { TrainingPanel } from "@/training/TrainingPanel";

export function TrainingPage() {
  const { sim, exercises, actions, select } = useWorkstation();
  return (
    <PageBody intro="Guided exercises teach you to operate the workstation. Each task is judged from the simulation state, and every explanation uses the values your own run produced.">
      <div className={`mx-auto overflow-hidden rounded-xl border border-line bg-panel-2 shadow-[var(--shadow-card)] ${sim.training ? "max-w-3xl bg-panel" : "max-w-6xl"}`}>
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
