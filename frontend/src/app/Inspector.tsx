import { X } from "lucide-react";
import { useEffect, useRef } from "react";

import { ChemicalCard } from "@/controls/ChemicalsPanel";
import { ComponentPanel } from "@/controls/ComponentPanel";
import { HydraulicsPanel } from "@/controls/HydraulicsPanel";

import { useWorkstation } from "./context";

/**
 * Non-modal inspector sheet. Opens from the right whenever a component is
 * selected anywhere (schematic, tables, palette) and closes back to the
 * right (symmetric path). No scrim: the process stays visible and usable.
 */
export function Inspector() {
  const { state, selection, select, selectTag, prefs, actions } = useWorkstation();
  const open = selection !== null;
  // keep rendering the last selection while the sheet animates out
  const last = useRef(selection);
  if (selection) last.current = selection;
  const sheet = useRef<HTMLElement>(null);
  // closed sheet: remove from tab order and accessibility tree
  useEffect(() => {
    sheet.current?.toggleAttribute("inert", !open);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !(e.target as HTMLElement)?.closest("[role=dialog]")) select(null);
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [open, select]);

  const shown = last.current;
  const title =
    shown?.type === "instrument"
      ? "Transmitter"
      : shown?.type === "selector" || shown?.type === "hydraulic"
        ? "Control hydraulics"
        : shown?.type === "chemical"
          ? "Chemical injection"
      : shown?.type === "element"
        ? ({ valve: "Valve", choke: "Choke", pipe: "Pipe", check_valve: "Check valve", inflow: "Reservoir" } as Record<string, string>)[
            state.elements.find((e) => e.id === shown.id)?.kind ?? ""
          ] ?? "Component"
        : "";

  return (
    <aside
      ref={sheet}
      aria-label="Component inspector"
      aria-hidden={!open}
      data-open={open}
      className="sheet fixed bottom-3 right-3 top-[68px] z-30 flex w-[min(420px,calc(100vw-24px))] flex-col overflow-hidden rounded-2xl border border-line bg-panel shadow-[var(--shadow-float)]"
    >
      <header className="flex h-11 shrink-0 items-center justify-between border-b border-line px-4">
        <span className="t-eyebrow">{title} inspector</span>
        <button
          type="button"
          onClick={() => select(null)}
          className="pressable rounded-md p-1 text-dim hover:bg-panel-3 hover:text-fg"
          aria-label="Close inspector"
          title="Close (Esc)"
          tabIndex={open ? 0 : -1}
        >
          <X size={16} />
        </button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {shown && (shown.type === "selector" || shown.type === "hydraulic") ? (
          <HydraulicsPanel state={state} prefs={prefs} focus={shown.type === "selector" ? shown.tag : shown.id}
            onSelector={actions.selector} onSupply={actions.supply} onSelect={selectTag} />
        ) : shown?.type === "chemical" ? (
          (() => {
            const c = state.chemicals?.find((x) => x.id === shown.id);
            return c ? (
              <div className="p-3">
                <ChemicalCard c={c} state={state} prefs={prefs} onPump={actions.pump} onValve={actions.valve} onSelect={selectTag} />
              </div>
            ) : (
              <p className="p-3 text-dim">Chemical injection is modelled in the dynamic mode only.</p>
            );
          })()
        ) : (
          shown && <ComponentPanel state={state} selection={shown} prefs={prefs} onCommand={(tag, c, p) => actions.valve(tag, c, p)} />
        )}
      </div>
    </aside>
  );
}
