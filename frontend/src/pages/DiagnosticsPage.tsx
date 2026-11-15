import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { DiagnosticsPanel } from "@/dashboard/DiagnosticsPanel";

export function DiagnosticsPage() {
  const { state } = useWorkstation();
  return (
    <PageBody intro="Diagnostics never change results — they tell you when the current operating point lies outside the model's assumptions, so you know which numbers not to trust.">
      <DiagnosticsPanel state={state} />
    </PageBody>
  );
}
