import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { IntegrityPanel } from "@/controls/IntegrityPanel";

export function IntegrityPage() {
  const { state, actions } = useWorkstation();
  return (
    <PageBody intro="Every test first verifies that the test volume is isolated, then follows the evolving pressure in simulated time. Results separate the equivalent leak rate from thermal expansion effects. Acceptance limits are illustrative training values.">
      <IntegrityPanel state={state} onStart={actions.integrityStart} onAbort={actions.integrityAbort} />
    </PageBody>
  );
}
