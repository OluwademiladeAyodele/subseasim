import { formatSimTime } from "@/lib/units";
import { aliasText } from "@/lib/tags";
import type { TagAlias } from "@/types/simulation";
import { cn } from "@/lib/utils";
import type { SimEvent } from "@/types/simulation";

export const EVENT_STYLE: Record<string, { label: string; color: string }> = {
  operation: { label: "Operation", color: "#0369a1" },
  valve: { label: "Valve", color: "#16a34a" },
  outcome: { label: "Outcome", color: "#0d9488" },
  process: { label: "Process", color: "#64748b" },
  chemical: { label: "Chemical", color: "#c026d3" },
  integrity: { label: "Integrity", color: "#d97706" },
  lifecycle: { label: "Lifecycle", color: "#94a3b8" },
  boundary: { label: "Boundary", color: "#2563eb" },
  fluid: { label: "Fluid", color: "#2563eb" },
  training_rule: { label: "Training rule", color: "#d97706" },
  rejected: { label: "Rejected", color: "#dc2626" },
  training: { label: "Training", color: "#7c3aed" },
  scenario: { label: "Scenario", color: "#94a3b8" },
};

export function EventLog({
  events,
  compact = false,
  limit,
  onTag,
  aliases,
}: {
  events: SimEvent[];
  /** engineering tag -> display tag (reference numbering) */
  aliases?: Record<string, TagAlias>;
  compact?: boolean;
  limit?: number;
  onTag?: (tag: string) => void;
}) {
  const list = [...events].reverse().slice(0, limit ?? events.length);
  if (!list.length) return <p className="px-4 py-6 text-center text-[13px] text-dim">No events yet. Operations and system responses will appear here.</p>;
  return (
    <ol className="divide-y divide-line/70" data-testid={compact ? "event-feed" : "event-log"}>
      {list.map((e) => {
        const st = EVENT_STYLE[e.category] ?? { label: e.category, color: "#94a3b8" };
        return (
          <li
            key={e.id}
            className={cn(
              "relative grid gap-x-3 px-4",
              compact ? "grid-cols-[58px_1fr] py-2" : "grid-cols-[76px_120px_1fr] py-2.5",
              e.severity === "warning" && "bg-warn/[0.05]",
              e.severity === "error" && "bg-bad/[0.05]",
            )}
          >
            {e.severity !== "info" && <span aria-hidden className={cn("absolute inset-y-0 left-0 w-[3px]", e.severity === "error" ? "bg-bad" : "bg-warn")} />}
            <span className="num pt-px text-[12px] text-dim" title={`Simulated time · wall clock ${new Date(e.wall_time * 1000).toLocaleTimeString()}`}>
              {formatSimTime(e.sim_time_s)}
            </span>
            {!compact && (
              <span className="flex items-start gap-1.5 pt-px text-[12px] font-medium text-muted">
                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: st.color }} />
                {st.label}
              </span>
            )}
            <span className={cn("text-[13px] leading-snug text-fg", compact && "line-clamp-3")}>
              {compact && <span className="mr-1.5 inline-block h-2 w-2 rounded-full align-middle" style={{ background: st.color }} title={st.label} />}
              {e.component && !e.message.startsWith(e.component) && (
                <button
                  type="button"
                  onClick={onTag ? () => onTag(e.component!) : undefined}
                  className={cn("num mr-1.5 rounded bg-panel-3 px-1 text-[11.5px] font-semibold text-fg", onTag ? "hover:bg-accent/10 hover:text-accent" : "cursor-default")}
                >
                  {aliases?.[e.component]?.tag ?? e.component}
                </button>
              )}
              {aliases ? aliasText({ tag_aliases: aliases }, e.message) : e.message}
              {!compact && e.detail && <span className="mt-0.5 block text-[12px] text-dim">{e.detail}</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
