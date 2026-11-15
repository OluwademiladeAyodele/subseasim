import { AlertTriangle, Info, X } from "lucide-react";
import { lazy, Suspense, useEffect, useState } from "react";

import type { Simulation } from "@/hooks/useSimulation";
import { ChemicalsPage } from "@/pages/ChemicalsPage";
import { ConditionsPage } from "@/pages/ConditionsPage";
import { DiagnosticsPage } from "@/pages/DiagnosticsPage";
import { EventsPage } from "@/pages/EventsPage";
import { InstrumentsPage } from "@/pages/InstrumentsPage";
import { IntegrityPage } from "@/pages/IntegrityPage";
import { OverviewPage } from "@/pages/OverviewPage";
import { ScenarioPage } from "@/pages/ScenarioPage";
import { TrainingPage } from "@/pages/TrainingPage";
import { ValvesPage } from "@/pages/ValvesPage";

import { CommandPalette } from "./CommandPalette";
import { useWorkstation, WorkstationProvider } from "./context";
import { Inspector } from "./Inspector";
import { ROUTES, type RouteId } from "./routes";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { useRoute } from "./useRoute";

const SIDEBAR_KEY = "subseasim.sidebar";

// Charting library is only needed on the Trends workspace: load it on demand.
const TrendsPage = lazy(() => import("@/pages/TrendsPage").then((m) => ({ default: m.TrendsPage })));

const PAGES: Record<RouteId, React.ComponentType> = {
  overview: OverviewPage,
  trends: TrendsPage,
  chemicals: ChemicalsPage,
  integrity: IntegrityPage,
  valves: ValvesPage,
  instruments: InstrumentsPage,
  events: EventsPage,
  diagnostics: DiagnosticsPage,
  conditions: ConditionsPage,
  scenario: ScenarioPage,
  training: TrainingPage,
};

/**
 * Floating toasts: always visible whatever the scroll position or open
 * inspector. Errors stay until dismissed or the next action succeeds;
 * notices dismiss themselves.
 */
function Toasts() {
  const { sim } = useWorkstation();
  const { notice, clearNotice } = sim;
  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(clearNotice, 12_000);
    return () => clearTimeout(t);
  }, [notice, clearNotice]);
  if (!sim.error && !notice) return null;
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-12 z-[60] flex flex-col items-center gap-2 px-4" aria-live="assertive">
      {sim.error && (
        <div
          role="alert"
          data-testid="error-banner"
          className="palette-in pointer-events-auto flex w-full max-w-[640px] items-start gap-2.5 rounded-xl border border-bad/30 bg-panel px-4 py-3 text-[13.5px] text-bad shadow-[var(--shadow-float)]"
        >
          <AlertTriangle size={17} className="mt-0.5 shrink-0" />
          <span className="flex-1 text-fg">
            <span className="font-semibold text-bad">Command not accepted. </span>
            {sim.error}
          </span>
          <button type="button" onClick={sim.clearError} className="pressable rounded p-0.5 text-dim hover:bg-panel-3 hover:text-fg" aria-label="Dismiss error">
            <X size={15} />
          </button>
        </div>
      )}
      {notice && (
        <div
          role="status"
          data-testid="notice-banner"
          className="palette-in pointer-events-auto flex w-full max-w-[640px] items-start gap-2.5 rounded-xl border border-info/25 bg-panel px-4 py-3 text-[13.5px] text-fg shadow-[var(--shadow-float)]"
        >
          <Info size={17} className="mt-0.5 shrink-0 text-info" />
          <span className="flex-1">{notice}</span>
          <button type="button" onClick={clearNotice} className="pressable rounded p-0.5 text-dim hover:bg-panel-3 hover:text-fg" aria-label="Dismiss notice">
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  );
}

function Workspace() {
  const { route, go, select, selection } = useWorkstation();
  const [collapsed, setCollapsed] = useState(() => {
    try {
      const v = localStorage.getItem(SIDEBAR_KEY);
      if (v !== null) return v === "1";
    } catch {
      /* storage unavailable */
    }
    // default: icon rail on laptop-size screens, full sidebar on desktops
    return window.innerWidth < 1400;
  });
  const [palette, setPalette] = useState(false);

  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement)?.closest("input, textarea, select, [contenteditable=true]");
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((p) => !p);
        return;
      }
      if (e.altKey && !typing && /^[1-9]$/.test(e.key)) {
        const r = ROUTES.find((x) => x.key === e.key);
        if (r) {
          e.preventDefault();
          go(r.id);
        }
      }
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [go]);

  const toggle = () =>
    setCollapsed((c) => {
      try {
        localStorage.setItem(SIDEBAR_KEY, c ? "0" : "1");
      } catch {
        /* ignore */
      }
      return !c;
    });

  const Page = PAGES[route];
  return (
    <div className="flex h-full min-h-0">
      <Sidebar collapsed={collapsed} onToggle={toggle} onSearch={() => setPalette(true)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main
          className={`min-h-0 flex-1 overflow-y-auto transition-[padding] duration-300 ease-[var(--ease-out)] ${selection ? "2xl:pr-[432px]" : ""}`}
          onClick={(e) => e.target === e.currentTarget && select(null)}
        >
          <div key={route} className="page-in">
            <Suspense fallback={<p className="px-5 py-10 text-center text-[13px] text-dim">Loading…</p>}>
              <Page />
            </Suspense>
          </div>
        </main>
        <footer className="border-t border-line bg-panel px-5 py-1.5 text-[11px] text-dim">
          SubseaSim is an educational simulator using illustrative data and simplified models. It is not safety-certified, must not be used for
          operational decisions, and has no interface to real subsea, SCADA or control systems.
        </footer>
      </div>
      <Inspector />
      <Toasts />
      <CommandPalette open={palette} onClose={() => setPalette(false)} />
    </div>
  );
}

function Loading({ error }: { error: string | null }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 bg-bg">
      <div className="blob h-14 w-14 animate-pulse bg-cyan/30" />
      <p className={error ? "max-w-md text-center text-bad" : "text-muted"}>{error ?? "Connecting to the SubseaSim engine…"}</p>
    </div>
  );
}

export function Shell({ sim }: { sim: Simulation }) {
  const [route, go] = useRoute();
  if (!sim.state || !sim.layout) return <Loading error={sim.error} />;
  return (
    <WorkstationProvider sim={sim} route={route} go={go}>
      <Workspace />
    </WorkstationProvider>
  );
}
