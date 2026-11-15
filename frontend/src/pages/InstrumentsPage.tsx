import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { Segmented } from "@/components/ui/primitives";
import { InstrumentTable } from "@/instrumentation/InstrumentTable";

type Filter = "all" | "pressure" | "temperature" | "flow" | "concentration" | "attention";

export function InstrumentsPage() {
  const { state, prefs, selectTag } = useWorkstation();
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    const instruments = state.instruments.filter((i) => {
      if (filter === "attention" && i.status === "GOOD") return false;
      if (filter === "pressure" && i.type !== "pressure" && i.type !== "differential_pressure") return false;
      if (filter !== "all" && filter !== "attention" && filter !== "pressure" && i.type !== filter) return false;
      return !t || `${i.tag} ${i.description} ${i.node ?? ""} ${i.element ?? ""}`.toLowerCase().includes(t);
    });
    return { ...state, instruments };
  }, [state, q, filter]);
  const attention = state.instruments.filter((i) => i.status !== "GOOD").length;

  return (
    <PageBody
      actions={
        <>
          <label className="flex h-9 items-center gap-2 rounded-lg border border-line-strong bg-panel px-3 focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20">
            <Search size={15} className="text-dim" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Filter by tag or description"
              aria-label="Filter instruments"
              className="w-56 bg-transparent text-[13px] outline-none placeholder:text-dim"
            />
          </label>
          <Segmented<Filter>
            label="Instrument type"
            value={filter}
            onChange={setFilter}
            options={[
              { value: "all", label: `All ${state.instruments.length}` },
              { value: "pressure", label: "Pressure" },
              { value: "temperature", label: "Temperature" },
              { value: "flow", label: "Flow" },
              { value: "concentration", label: "Analysers" },
              { value: "attention", label: `Attention ${attention}` },
            ]}
          />
        </>
      }
      intro="Measured values as the transmitters report them (after sensor lag, update interval and resolution). Select a row to see the model value alongside."
    >
      <div className="overflow-hidden rounded-xl border border-line bg-panel shadow-[var(--shadow-card)]">
        {filtered.instruments.length ? (
          <InstrumentTable state={filtered} prefs={prefs} onSelect={selectTag} />
        ) : (
          <p className="px-4 py-10 text-center text-[13px] text-dim">No transmitters match this filter.</p>
        )}
      </div>
    </PageBody>
  );
}
