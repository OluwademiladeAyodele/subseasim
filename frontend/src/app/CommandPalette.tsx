/**
 * Command palette (Ctrl/Cmd + K): one keyboard path to every workspace,
 * component, valve operation, simulation control and scenario.
 */
import { ArrowRight, CornerDownLeft, Gauge, Layers, Play, Search, ToggleRight } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Kbd } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
import type { RestrictionSnapshot } from "@/types/simulation";

import { useWorkstation } from "./context";
import { ROUTES } from "./routes";

interface Cmd {
  id: string;
  group: "Go to" | "Simulation" | "Operate" | "Inspect" | "Scenario";
  label: string;
  hint?: string;
  icon: React.ReactNode;
  run: () => void;
  keywords?: string;
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const w = useWorkstation();
  const { state, actions, go, selectTag, scenarios } = w;
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (open) {
      setQ("");
      setIdx(0);
      requestAnimationFrame(() => input.current?.focus());
    }
  }, [open]);

  const commands = useMemo<Cmd[]>(() => {
    const out: Cmd[] = ROUTES.map((r) => ({
      id: `go-${r.id}`,
      group: "Go to",
      label: r.label,
      hint: r.description,
      icon: <r.icon size={16} />,
      run: () => go(r.id),
      keywords: r.group,
    }));
    const s = state.status;
    if (s === "ready") out.push({ id: "start", group: "Simulation", label: "Start simulation", icon: <Play size={16} />, run: () => actions.lifecycle("start") });
    if (s === "running") out.push({ id: "pause", group: "Simulation", label: "Pause simulation", icon: <Play size={16} />, run: () => actions.lifecycle("pause") });
    if (s === "paused") out.push({ id: "resume", group: "Simulation", label: "Resume simulation", icon: <Play size={16} />, run: () => actions.lifecycle("resume") });
    out.push({ id: "reset", group: "Simulation", label: "Reset to initial conditions", icon: <Play size={16} />, run: () => actions.lifecycle("reset") });
    for (const sp of state.clock?.allowed_speeds ?? [1, 10, 60, 300]) {
      out.push({ id: `speed-${sp}`, group: "Simulation", label: `Speed ${sp}×`, icon: <Gauge size={16} />, run: () => actions.speed(sp), keywords: "speed fast" });
    }
    out.push({
      id: "mode",
      group: "Simulation",
      label: state.mode === "dynamic" ? "Switch to steady model" : "Switch to dynamic model",
      hint: "Restarts from the scenario's initial conditions",
      icon: <Layers size={16} />,
      run: () => actions.mode(state.mode === "dynamic" ? "steady" : "dynamic"),
    });
    for (const e of state.elements) {
      if (e.kind !== "valve" && e.kind !== "choke") continue;
      const v = e as RestrictionSnapshot;
      if (!v.available) continue;
      out.push({ id: `open-${v.tag}`, group: "Operate", label: `Open ${v.tag}`, hint: v.name, icon: <ToggleRight size={16} />, run: () => actions.valve(v.tag, "open") });
      out.push({ id: `close-${v.tag}`, group: "Operate", label: `Close ${v.tag}`, hint: v.name, icon: <ToggleRight size={16} />, run: () => actions.valve(v.tag, "close") });
      out.push({ id: `insp-${v.tag}`, group: "Inspect", label: v.tag, hint: v.name, icon: <Search size={16} />, run: () => selectTag(v.tag) });
    }
    for (const i of state.instruments) {
      out.push({ id: `insp-${i.tag}`, group: "Inspect", label: i.tag, hint: i.description, icon: <Search size={16} />, run: () => selectTag(i.tag) });
    }
    for (const sc of scenarios) {
      if (sc.id === state.scenario.id) continue;
      out.push({ id: `sc-${sc.id}`, group: "Scenario", label: `Load: ${sc.name}`, icon: <Layers size={16} />, run: () => actions.scenario(sc.id) });
    }
    return out;
  }, [state, actions, go, selectTag, scenarios]);

  const filtered = useMemo(() => {
    const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
    const hits = terms.length
      ? commands.filter((c) => {
          const hay = `${c.label} ${c.hint ?? ""} ${c.group} ${c.keywords ?? ""}`.toLowerCase();
          return terms.every((t) => hay.includes(t));
        })
      : commands.filter((c) => c.group === "Go to" || c.group === "Simulation");
    return hits.slice(0, 60);
  }, [q, commands]);

  useEffect(() => setIdx(0), [q]);
  useEffect(() => {
    listRef.current?.querySelector(`[data-idx="${idx}"]`)?.scrollIntoView({ block: "nearest" });
  }, [idx]);

  if (!open) return null;
  const exec = (c: Cmd | undefined) => {
    if (!c) return;
    onClose();
    c.run();
  };
  let lastGroup = "";

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[12vh]" role="dialog" aria-modal="true" aria-label="Command palette">
      <div className="scrim-in absolute inset-0 bg-navy/25 backdrop-blur-[2px]" onClick={onClose} />
      <div className="palette-in relative w-full max-w-[620px] overflow-hidden rounded-2xl border border-line bg-panel shadow-[var(--shadow-float)]">
        <div className="flex items-center gap-2.5 border-b border-line px-4">
          <Search size={18} className="text-dim" />
          <input
            ref={input}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setIdx((i) => Math.min(filtered.length - 1, i + 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setIdx((i) => Math.max(0, i - 1));
              } else if (e.key === "Enter") {
                e.preventDefault();
                exec(filtered[idx]);
              } else if (e.key === "Escape") {
                e.preventDefault();
                onClose();
              }
            }}
            placeholder="Search workspaces, valves, transmitters, actions…"
            aria-label="Search commands"
            className="h-13 flex-1 bg-transparent text-[15px] text-fg outline-none placeholder:text-dim focus-visible:outline-none"
          />
          <Kbd>Esc</Kbd>
        </div>
        <ul ref={listRef} className="max-h-[52vh] overflow-y-auto p-2" role="listbox" aria-label="Commands">
          {filtered.length === 0 && <li className="px-3 py-8 text-center text-sm text-dim">No matches for “{q}”.</li>}
          {filtered.map((c, i) => {
            const header = c.group !== lastGroup ? c.group : null;
            lastGroup = c.group;
            return (
              <li key={c.id} role="presentation">
                {header && <div className="t-eyebrow px-3 pb-1 pt-2.5">{header}</div>}
                <button
                  type="button"
                  role="option"
                  aria-selected={i === idx}
                  data-idx={i}
                  onMouseMove={() => setIdx(i)}
                  onClick={() => exec(c)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left",
                    i === idx ? "bg-navy text-white" : "text-fg hover:bg-panel-2",
                  )}
                >
                  <span className={i === idx ? "text-cyan" : "text-dim"}>{c.icon}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13.5px] font-medium">{c.label}</span>
                    {c.hint && <span className={cn("block truncate text-xs", i === idx ? "text-white/60" : "text-dim")}>{c.hint}</span>}
                  </span>
                  {i === idx ? <CornerDownLeft size={14} className="text-white/60" /> : <ArrowRight size={14} className="text-line-strong" />}
                </button>
              </li>
            );
          })}
        </ul>
        <div className="flex items-center gap-4 border-t border-line bg-panel-2 px-4 py-2 text-[11.5px] text-dim">
          <span className="flex items-center gap-1">
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd> navigate
          </span>
          <span className="flex items-center gap-1">
            <Kbd>Enter</Kbd> run
          </span>
          <span className="flex items-center gap-1">
            <Kbd>Alt</Kbd>+<Kbd>1–9</Kbd> jump to workspace
          </span>
        </div>
      </div>
    </div>
  );
}
