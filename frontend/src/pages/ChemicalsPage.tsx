import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { ChemicalsPanel } from "@/controls/ChemicalsPanel";

export function ChemicalsPage() {
  const { state, prefs, actions, selectTag } = useWorkstation();
  return (
    <PageBody>
      <ChemicalsPanel state={state} prefs={prefs} onPump={actions.pump} onValve={actions.valve} onSelect={selectTag} />
    </PageBody>
  );
}
