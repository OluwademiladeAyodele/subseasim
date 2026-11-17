/**
 * Chemical-injection circuits. Every value comes from the backend dynamic
 * model (injection flow from the hydraulic network, concentration from the
 * transport grid, transit times from V/Q of the current flow).
 */
import { Droplets, Power } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge, Button, Input } from "@/components/ui/primitives";
import { concFromFraction, type DisplayPrefs, fmt, formatDuration, instrumentDisplay, paToBarDelta, pressureFromPa } from "@/lib/units";
import type { ChemicalSnapshot, RestrictionSnapshot, SimulationState, ValveCommand } from "@/types/simulation";

const STATUS: Record<string, { label: string; tone: "ok" | "warn" | "bad" | "neutral" | "info" }> = {
  injecting: { label: "Injecting", tone: "ok" },
  isolated: { label: "Isolated", tone: "neutral" },
  pump_stopped: { label: "Pump stopped", tone: "warn" },
  metering_closed: { label: "Metering closed", tone: "neutral" },
  insufficient_differential: { label: "No differential", tone: "bad" },
};

interface Props {
  state: SimulationState;
  prefs: DisplayPrefs;
  onPump: (chem: string, body: { running?: boolean; discharge_pressure_pa?: number }) => Promise<boolean>;
  onValve: (tag: string, c: ValveCommand, pos?: number) => Promise<boolean>;
  onSelect: (tag: string) => void;
}

export function ChemicalsPanel({ state, prefs, onPump, onValve, onSelect }: Props) {
  if (state.mode !== "dynamic" || !state.chemicals) {
    return (
      <div className="p-3 text-muted" data-testid="chemicals-panel">
        Chemical injection is modelled only in the <span className="text-accent">dynamic</span> simulation mode. Switch the model in the top bar.
      </div>
    );
  }
  if (!state.chemicals.length) return <p className="p-3 text-dim">This scenario has no chemical-injection circuits.</p>;
  return (
    <div className="grid items-start gap-4 xl:grid-cols-2" data-testid="chemicals-panel">
      <p className="col-span-full text-[13.5px] leading-relaxed text-muted">
        Injection rate = f(supply pressure − line losses − metering-valve ΔP − production pressure at the injection point). Concentrations are transported
        by the calculated production flow.
      </p>
      {state.chemicals.map((c) => (
        <ChemicalCard key={c.id} c={c} state={state} prefs={prefs} onPump={onPump} onValve={onValve} onSelect={onSelect} />
      ))}
    </div>
  );
}

function ChemicalCard({ c, state, prefs, onPump, onValve, onSelect }: { c: ChemicalSnapshot } & Props) {
  const el = (tag: string) => state.elements.find((e) => (e as RestrictionSnapshot).tag === tag) as RestrictionSnapshot | undefined;
  const iso = el(c.isolation_valve);
  const cv = el(c.control_valve);
  const [sp, setSp] = useState(pressureFromPa(c.discharge_pressure_pa, "bara"));
  const [pos, setPos] = useState(cv?.commanded_pct ?? 0);
  useEffect(() => setSp(pressureFromPa(c.discharge_pressure_pa, "bara")), [c.discharge_pressure_pa]);
  useEffect(() => setPos(cv?.commanded_pct ?? 0), [cv?.commanded_pct]);
  const st = STATUS[c.status] ?? { label: c.status, tone: "neutral" as const };
  const lph = c.injection_flow_m3s * 3600 * 1000;
  const mixed = concFromFraction(c.fully_mixed_concentration, c.display_unit);
  const inBand = c.target_min !== null && c.target_max !== null && mixed >= c.target_min && mixed <= c.target_max;
  const dp = paToBarDelta(c.available_differential_pa);
  const analysers = state.instruments.filter((i) => i.type === "concentration" && i.chemical === c.id);
  const ft = state.instruments.find((i) => i.tag === c.flow_transmitter);
  const pt = state.instruments.find((i) => i.tag === c.pressure_transmitter);

  return (
    <section className="overflow-hidden rounded-xl border border-line bg-panel shadow-[var(--shadow-card)]" style={{ borderTop: `3px solid ${c.color}` }} data-testid={`chem-${c.id}`}>
      <header className="flex items-center justify-between gap-2 border-b border-line/70 px-4 py-3">
        <div className="flex items-center gap-2">
          <Droplets size={14} style={{ color: c.color }} />
          <div>
            <div className="text-[13.5px] font-bold text-fg">{c.name}</div>
            <div className="text-[11.5px] text-dim">→ {c.injection_node_name}</div>
          </div>
        </div>
        <Badge tone={st.tone} data-testid={`chem-status-${c.id}`}>
          {c.status === "injecting" && <span className="live-dot mr-0.5 inline-block h-1.5 w-1.5 rounded-full bg-ok" />}
          {st.label}
        </Badge>
      </header>

      <div className="grid grid-cols-3 gap-px bg-line/40 text-center">
        <Metric label="Injection" value={fmt(lph, lph < 10 ? 2 : 0)} unit="L/h" accent={c.status === "injecting" ? c.color : undefined}
          sub={ft ? `${ft.tag} ${fmt(instrumentDisplay("flow", ft.value_si, prefs).value, 1)} ${instrumentDisplay("flow", ft.value_si, prefs).unit}` : undefined} />
        <Metric label="Available ΔP" value={fmt(dp, 1)} unit="bar" warn={dp <= 0} sub="supply + head − P_inj − crack" />
        <Metric label="Fully mixed" value={fmt(mixed, c.display_unit === "ppm" ? 0 : 2)} unit={c.display_unit} warn={c.status === "injecting" && !inBand && c.target_min !== null}
          sub={c.target_min !== null ? `target ${c.target_min}–${c.target_max}` : undefined} />
      </div>

      <div className="space-y-3 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <Button size="xs" variant={c.pump_running ? "bad" : "ok"} onClick={() => onPump(c.id, { running: !c.pump_running })} aria-label={`${c.name} pump ${c.pump_running ? "stop" : "start"}`}>
            <Power size={11} /> {c.pump_running ? "Stop pump" : "Start pump"}
          </Button>
          <span className="text-[12px] text-dim">Discharge @ SDU</span>
          <Input type="number" className="h-6 w-20" value={Number.isFinite(sp) ? sp : ""} onChange={(e) => setSp(e.target.valueAsNumber)} aria-label={`${c.name} discharge pressure`} />
          <span className="text-[11.5px] text-dim">bara</span>
          <Button size="xs" variant="primary" disabled={!Number.isFinite(sp)} onClick={() => onPump(c.id, { discharge_pressure_pa: sp * 1e5 })}>
            Set
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {iso && (
            <>
              <button type="button" onClick={() => onSelect(iso.tag)} className="num text-[12.5px] font-bold text-fg hover:text-accent">
                {iso.tag}
              </button>
              <Button size="xs" variant="ok" disabled={!iso.supported_commands.includes("open")} onClick={() => onValve(iso.tag, "open")} aria-label={`${iso.tag} open`}>
                Open
              </Button>
              <Button size="xs" variant="bad" onClick={() => onValve(iso.tag, "close")} aria-label={`${iso.tag} close`}>
                Close
              </Button>
              <span className="num text-[11.5px] text-dim">{fmt(iso.position_pct, 0)} %{iso.moving ? " moving" : ""}</span>
            </>
          )}
          {cv && (
            <span className="ml-auto flex items-center gap-1">
              <button type="button" onClick={() => onSelect(cv.tag)} className="num text-[12.5px] font-bold text-fg hover:text-accent">
                {cv.tag}
              </button>
              <Input type="number" className="h-6 w-14" min={0} max={100} value={Number.isFinite(pos) ? pos : ""} onChange={(e) => setPos(e.target.valueAsNumber)} aria-label={`${cv.tag} position`} />
              <span className="text-[11.5px] text-dim">%</span>
              <Button size="xs" variant="primary" disabled={!(pos >= 0 && pos <= 100)} onClick={() => onValve(cv.tag, "set_position", pos)}>
                Set
              </Button>
            </span>
          )}
        </div>

        <div className="grid grid-cols-2 gap-x-3 text-[12.5px]">
          <Kv k="Supply (SDU)" v={`${fmt(pressureFromPa(c.supply_pressure_pa, prefs.pressureRef), 1)} ${prefs.pressureRef}`} />
          <Kv k={pt ? `${pt.tag} line @ tree` : "Line @ tree"} v={pt?.value_si != null ? `${fmt(pressureFromPa(pt.value_si, prefs.pressureRef), 1)} ${prefs.pressureRef}` : "—"} />
          <Kv k="Injection point" v={`${fmt(pressureFromPa(c.injection_point_pressure_pa, prefs.pressureRef), 1)} ${prefs.pressureRef}`} />
          <Kv k="Chemical front" v={c.front_distance_m > 0 ? `${fmt(c.front_distance_m / 1000, 2)} km downstream` : "—"} />
          <Kv k="Injected (total)" v={`${fmt(c.cumulative_injected_m3 * 1000, 0)} L`} />
          <Kv k="In line / exported" v={`${fmt(c.in_production_line_m3 * 1000, 0)} / ${fmt(c.exported_m3 * 1000, 0)} L`} />
        </div>

        {c.annulus_route && <AnnulusRoute c={c} state={state} onValve={onValve} onSelect={onSelect} />}

        {analysers.length > 0 && (
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="text-[11px] uppercase tracking-wider text-dim">
                <th className="text-left font-semibold">Analyser</th>
                <th className="text-right font-semibold">Distance</th>
                <th className="text-right font-semibold" title="Plug-flow residence time V/Q at the CURRENT production flow">Transit V/Q</th>
                <th className="text-right font-semibold">Reading</th>
              </tr>
            </thead>
            <tbody>
              {analysers.map((a) => {
                const info = c.analysers.find((x) => x.tag === a.tag);
                const d = instrumentDisplay(a.type, a.value_si, prefs, a.display_unit);
                const frac = mixed > 0 && d.value !== null ? Math.min(1, d.value / mixed) : 0;
                return (
                  <tr key={a.tag} className="cursor-pointer hover:bg-panel-3/60" onClick={() => onSelect(a.tag)}>
                    <td className="num font-bold">{a.tag}</td>
                    <td className="num text-right text-muted">{info?.distance_from_injection_m != null ? `${fmt(info.distance_from_injection_m / 1000, 2)} km` : "—"}</td>
                    <td className="num text-right text-muted">{formatDuration(info?.plug_flow_transit_s)}</td>
                    <td className="num text-right">
                      <span className="mr-1 inline-block h-1.5 w-10 overflow-hidden rounded-full bg-line align-middle">
                        <span className="block h-full" style={{ width: `${frac * 100}%`, background: c.color }} />
                      </span>
                      {fmt(d.value, d.digits)} <span className="text-dim">{d.unit}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

function Metric({ label, value, unit, sub, accent, warn }: { label: string; value: string; unit: string; sub?: string; accent?: string; warn?: boolean }) {
  return (
    <div className="bg-panel px-1.5 py-1">
      <div className="t-eyebrow">{label}</div>
      <div className={`num text-[15px] leading-tight ${warn ? "text-warn" : "text-fg"}`} style={accent ? { color: accent } : undefined}>
        {value}
        <span className="ml-0.5 text-[11px] text-muted">{unit}</span>
      </div>
      {sub && <div className="truncate text-[10.5px] text-dim">{sub}</div>}
    </div>
  );
}

function Kv({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-2 border-b border-line/40 py-0.5">
      <span className="text-dim">{k}</span>
      <span className="num text-right text-fg">{v}</span>
    </div>
  );
}

/** Second route of a circuit: into the annulus service line (via MIV + NRV). */
function AnnulusRoute({ c, state, onValve, onSelect }: { c: ChemicalSnapshot; state: SimulationState; onValve: Props["onValve"]; onSelect: Props["onSelect"] }) {
  const r = c.annulus_route!;
  const miv = state.elements.find((e) => (e as RestrictionSnapshot).tag === r.valve) as RestrictionSnapshot | undefined;
  const lph = r.flow_m3s * 3600 * 1000;
  const on = r.status === "injecting";
  return (
    <div className="rounded-lg border border-[#99f6e4] bg-[#f0fdfa] px-3 py-2.5" data-testid={`chem-annulus-${c.id}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-[12.5px] font-semibold text-[#115e59]">Into the annulus service line</div>
          <div className="text-[11.5px] text-[#0f766e]">Flushes the service line to the host (SLV open) or bullheads the annulus (AWV / AMV open)</div>
        </div>
        <Badge tone={on ? "ok" : r.status === "insufficient_differential" ? "bad" : "neutral"}>
          {on && <span className="live-dot mr-0.5 inline-block h-1.5 w-1.5 rounded-full bg-ok" />}
          {on ? "Injecting" : r.status === "insufficient_differential" ? "No differential" : r.status === "pump_stopped" ? "Pump stopped" : "Isolated"}
        </Badge>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {miv && (
          <>
            <button type="button" onClick={() => onSelect(miv.tag)} className="num text-[12px] font-bold text-fg hover:text-accent">
              {miv.tag}
            </button>
            <Button size="xs" variant="ok" onClick={() => onValve(miv.tag, "open")} aria-label={`${miv.tag} open`}>
              Open
            </Button>
            <Button size="xs" variant="bad" onClick={() => onValve(miv.tag, "close")} aria-label={`${miv.tag} close`}>
              Close
            </Button>
            <span className="num text-[11px] text-dim">{fmt(miv.position_pct, 0)} %{miv.moving ? " moving" : ""}</span>
          </>
        )}
        <span className="num ml-auto text-[12.5px]">
          <span className="font-semibold">{fmt(lph, lph < 10 ? 2 : 0)}</span> <span className="text-dim">L/h</span>
          <span className="mx-2 text-line-strong">|</span>
          <span className="text-dim">to annulus system </span>
          <span className="font-semibold">{fmt(r.cumulative_m3 * 1000, 0)}</span> <span className="text-dim">L</span>
        </span>
      </div>
    </div>
  );
}
