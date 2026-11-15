import { ChevronsLeft, ChevronsRight, Search } from "lucide-react";

import { cn } from "@/lib/utils";

import { useWorkstation } from "./context";
import { GROUPS, ROUTES, type RouteId } from "./routes";

function Logo({ compact }: { compact: boolean }) {
  return (
    <div className="flex items-center gap-2.5 px-1">
      <svg viewBox="0 0 32 32" className="h-8 w-8 shrink-0" aria-hidden>
        <rect width="32" height="32" rx="9" fill="#ffffff" fillOpacity="0.08" />
        <path d="M16 6v20" stroke="#22d3ee" strokeWidth="2.6" strokeLinecap="round" />
        <path d="M9.5 11.5h13M11.5 17.5h9" stroke="#ffffff" strokeWidth="2.6" strokeLinecap="round" />
        <circle cx="16" cy="25" r="2.2" fill="#22d3ee" className="live-dot" />
      </svg>
      {!compact && (
        <div className="leading-tight">
          <div className="text-[15px] font-semibold tracking-[-0.01em] text-white">
            Subsea<span className="text-cyan">Sim</span>
          </div>
          <div className="text-[11px] text-white/50">Production workstation</div>
        </div>
      )}
    </div>
  );
}

export function Sidebar({ collapsed, onToggle, onSearch }: { collapsed: boolean; onToggle: () => void; onSearch: () => void }) {
  const { route, go, state, sim, training } = useSidebarData();
  const badge = (id: RouteId): { text: string; tone: "cyan" | "warn" | "bad" } | null => {
    if (id === "chemicals") {
      const n = state.chemicals?.filter((c) => c.status === "injecting").length ?? 0;
      return n ? { text: String(n), tone: "cyan" } : null;
    }
    if (id === "integrity") return state.integrity?.tests.some((t) => ["stabilising", "holding", "stroking"].includes(t.phase)) ? { text: "run", tone: "warn" } : null;
    if (id === "diagnostics") {
      const n = state.diagnostics.filter((d) => d.severity !== "info").length;
      return n ? { text: String(n), tone: state.diagnostics.some((d) => d.severity === "error") ? "bad" : "warn" } : null;
    }
    if (id === "training") return training ? { text: `${training.index + 1}/${training.steps.length}`, tone: "cyan" } : null;
    return null;
  };
  const conTone = sim.connection === "live" ? "bg-[#4ade80]" : sim.connection === "offline" ? "bg-[#f87171]" : "bg-[#fbbf24]";

  return (
    <nav
      aria-label="Workspaces"
      className={cn(
        "relative flex h-full shrink-0 flex-col bg-navy text-white transition-[width] duration-300 ease-[var(--ease-out)]",
        collapsed ? "w-[68px]" : "w-[244px]",
      )}
    >
      {/* soft organic glow: the "20 %" tactile accent */}
      <div aria-hidden className="blob pointer-events-none absolute -left-16 -top-20 h-56 w-56 bg-cyan/10 blur-2xl" />
      <div className="relative flex h-14 items-center justify-between px-3.5">
        <Logo compact={collapsed} />
      </div>

      <div className="relative px-3 pb-2">
        <button
          type="button"
          onClick={onSearch}
          className={cn(
            "pressable flex h-9 w-full items-center gap-2 rounded-lg bg-white/[0.07] px-2.5 text-[13px] text-white/60 hover:bg-white/[0.12] hover:text-white",
            collapsed && "justify-center px-0",
          )}
          aria-label="Search and commands"
          title="Search and commands (Ctrl+K)"
        >
          <Search size={15} />
          {!collapsed && (
            <>
              <span className="flex-1 text-left">Search & commands</span>
              <span className="rounded border border-white/15 px-1 text-[10.5px] text-white/50">Ctrl K</span>
            </>
          )}
        </button>
      </div>

      <div className="relative min-h-0 flex-1 overflow-y-auto px-3 pb-3">
        {GROUPS.map((g) => (
          <div key={g} className="mt-3 first:mt-1">
            {!collapsed ? (
              <div className="px-2.5 pb-1 text-[10.5px] font-semibold uppercase tracking-[0.1em] text-white/35">{g}</div>
            ) : (
              <div className="mx-2 mb-1.5 border-t border-white/10" />
            )}
            <ul className="space-y-0.5">
              {ROUTES.filter((r) => r.group === g).map((r) => {
                const active = r.id === route;
                const b = badge(r.id);
                const Icon = r.icon;
                return (
                  <li key={r.id}>
                    <a
                      href={`#/${r.id}`}
                      onClick={(e) => {
                        e.preventDefault();
                        go(r.id);
                      }}
                      aria-current={active ? "page" : undefined}
                      aria-label={r.label}
                      title={collapsed ? r.label : r.key ? `${r.label} (Alt+${r.key})` : r.label}
                      className={cn(
                        "pressable group relative flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-[13.5px] font-medium",
                        active ? "bg-white/[0.12] text-white" : "text-white/65 hover:bg-white/[0.06] hover:text-white",
                        collapsed && "justify-center px-0",
                      )}
                    >
                      {active && <span aria-hidden className="absolute -left-3 top-1.5 h-6 w-[3px] rounded-r-full bg-cyan" />}
                      <Icon size={17} strokeWidth={active ? 2.2 : 1.8} className={active ? "text-cyan" : ""} />
                      {!collapsed && <span className="flex-1 truncate">{r.label}</span>}
                      {b && (
                        <span
                          className={cn(
                            "num rounded-full px-1.5 text-[10.5px] font-semibold leading-[18px]",
                            b.tone === "cyan" && "bg-cyan/20 text-cyan",
                            b.tone === "warn" && "bg-[#fbbf24]/20 text-[#fcd34d]",
                            b.tone === "bad" && "bg-[#f87171]/25 text-[#fca5a5]",
                            collapsed && "absolute right-1 top-0.5 px-1 text-[9px] leading-[14px]",
                          )}
                        >
                          {b.text}
                        </span>
                      )}
                    </a>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      <div className="relative border-t border-white/10 px-3 py-2.5">
        {!collapsed && (
          <div className="mb-2 rounded-lg bg-[#fbbf24]/10 px-2.5 py-1.5 text-[11px] leading-snug text-[#fcd34d]" data-testid="simulated-badge">
            Simulated · training only. Not connected to any real system.
          </div>
        )}
        <div className={cn("flex items-center gap-2", collapsed ? "flex-col" : "justify-between")}>
          <span className="flex items-center gap-1.5 text-[12px] text-white/60" title={`Backend connection: ${sim.connection}`}>
            <span className={cn("h-2 w-2 rounded-full", conTone, sim.connection === "live" && "live-dot")} />
            {!collapsed && (
              <span data-testid="connection" className="text-white/70">
                {sim.connection}
              </span>
            )}
          </span>
          <button
            type="button"
            onClick={onToggle}
            className="pressable rounded-md p-1 text-white/50 hover:bg-white/10 hover:text-white"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <ChevronsRight size={16} /> : <ChevronsLeft size={16} />}
          </button>
        </div>
        {collapsed && <span data-testid="connection" className="sr-only">{sim.connection}</span>}
      </div>
    </nav>
  );
}

function useSidebarData() {
  const w = useWorkstation();
  return { route: w.route, go: w.go, state: w.state, sim: w.sim, training: w.sim.training };
}

