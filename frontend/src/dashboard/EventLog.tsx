import { Badge } from "@/components/ui/primitives";
import { formatSimTime } from "@/lib/units";
import type { SimEvent } from "@/types/simulation";

const TONE: Record<string, "neutral" | "ok" | "bad" | "warn" | "info" | "fault" | "accent"> = {
  operation: "accent",
  outcome: "ok",
  lifecycle: "neutral",
  boundary: "info",
  fluid: "info",
  training_rule: "warn",
  rejected: "bad",
  training: "fault",
  scenario: "neutral",
};

export function EventLog({ events, compact = false, limit }: { events: SimEvent[]; compact?: boolean; limit?: number }) {
  const list = [...events].reverse().slice(0, limit ?? events.length);
  if (!list.length) return <p className="p-3 text-dim">No events yet.</p>;
  return (
    <ol className="divide-y divide-line/60" data-testid={compact ? "event-feed" : "event-log"}>
      {list.map((e) => (
        <li key={e.id} className={`grid grid-cols-[64px_92px_1fr] gap-2 px-2 ${compact ? "py-1" : "py-1.5"} ${e.severity === "warning" ? "bg-warn/5" : ""}`}>
          <span className="num text-dim" title={new Date(e.wall_time * 1000).toLocaleString()}>
            {formatSimTime(e.sim_time_s)}
          </span>
          <span>
            <Badge tone={TONE[e.category] ?? "neutral"}>{e.category.replace("_", " ")}</Badge>
          </span>
          <span className={compact ? "line-clamp-2 text-fg" : "text-fg"}>
            {e.component && !e.message.startsWith(e.component) && <span className="num mr-1 font-bold text-accent">{e.component}</span>}
            {e.message}
            {!compact && e.detail && <span className="block text-[11px] text-dim">{e.detail}</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}
