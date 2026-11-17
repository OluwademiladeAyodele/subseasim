import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { ConditionsPanel } from "@/controls/ConditionsPanel";

export function ConditionsPage() {
  const { state, prefs, actions } = useWorkstation();
  return (
    <PageBody
      intro={
        state.mode === "dynamic"
          ? "Boundary changes act at the ends of the system; in the dynamic model the interior responds over simulated time, so start the simulation to watch the effect."
          : "In the steady model the operating point is recalculated immediately after each change."
      }
    >
      <ConditionsPanel state={state} prefs={prefs} onBoundary={actions.boundary} onFluid={actions.fluid} onBlackOil={actions.blackOil}
        onFluidModel={actions.fluidModel} />
    </PageBody>
  );
}
