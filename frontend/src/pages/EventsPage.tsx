import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { EVENT_STYLE, EventLog } from "@/dashboard/EventLog";
import { cn } from "@/lib/utils";

export function EventsPage() {
  const { sim, selectTag, state } = useWorkstation();
  const [q, setQ] = useState("");
  const [cats, setCats] = useState<Set<string>>(new Set());
  const present = useMemo(() => [...new Set(sim.events.map((e) => e.category))], [sim.events]);
  const list = useMemo(() => {
    const t = q.trim().toLowerCase();
    return sim.events.filter(
      (e) => (cats.size === 0 || cats.has(e.category)) && (!t || `${e.message} ${e.component ?? ""}`.toLowerCase().includes(t)),
    );
  }, [sim.events, q, cats]);
  const toggle = (c: string) =>
    setCats((s) => {
      const n = new Set(s);
      if (n.has(c)) n.delete(c);
      else n.add(c);
      return n;
    });

  return (
    <PageBody intro="Everything that happened, stamped with simulated time: your operations, valve end-of-travel, calculated outcomes, process settling, chemical and integrity events.">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <label className="flex h-9 items-center gap-2 rounded-lg border border-line-strong bg-panel px-3 focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20">
          <Search size={15} className="text-dim" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search events" aria-label="Search events" className="w-56 bg-transparent text-[13px] outline-none placeholder:text-dim" />
        </label>
        {present.map((c) => {
          const st = EVENT_STYLE[c] ?? { label: c, color: "#94a3b8" };
          const on = cats.has(c);
          return (
            <button
              key={c}
              type="button"
              aria-pressed={on}
              onClick={() => toggle(c)}
              className={cn(
                "pressable flex h-8 items-center gap-1.5 rounded-full border px-3 text-[12.5px] font-medium",
                on ? "border-navy bg-navy text-white" : "border-line-strong bg-panel text-muted hover:text-fg",
              )}
            >
              <span className="h-2 w-2 rounded-full" style={{ background: st.color }} />
              {st.label}
            </button>
          );
        })}
        {cats.size > 0 && (
          <button type="button" onClick={() => setCats(new Set())} className="text-[12.5px] font-medium text-accent hover:underline">
            Clear
          </button>
        )}
      </div>
      <div className="overflow-hidden rounded-xl border border-line bg-panel shadow-[var(--shadow-card)]">
        <EventLog events={list} onTag={selectTag} aliases={state.tag_aliases} />
      </div>
    </PageBody>
  );
}
