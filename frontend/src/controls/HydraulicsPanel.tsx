/**
 * Subsea control hydraulics: supplies -> selector valves -> SCM A/B headers
 * -> valve actuators. Values from the backend control-hydraulics model.
 */
import { Badge, Button } from "@/components/ui/primitives";
import { displayTag } from "@/lib/tags";
import { type DisplayPrefs, fmt, pressureFromPa } from "@/lib/units";
import type { SimulationState } from "@/types/simulation";

interface Props {
  state: SimulationState;
  prefs: DisplayPrefs;
  /** selector-valve tag or header / supply id to emphasise */
  focus?: string | null;
  onSelector: (tag: string, c: "open" | "close") => Promise<boolean>;
  onSupply: (id: string, available: boolean) => Promise<boolean>;
  onSelect: (tag: string) => void;
}

export function HydraulicsPanel({ state, prefs, focus, onSelector, onSupply, onSelect }: Props) {
  const h = state.control_hydraulics;
  if (!h) return <p className="p-3 text-dim">This scenario has no control-hydraulics model.</p>;
  const p = (pa: number) => `${fmt(pressureFromPa(pa, prefs.pressureRef), 1)} ${prefs.pressureRef}`;
  const sel = h.selector_valves.find((s) => s.tag === focus);
  return (
    <div className="space-y-3 p-3" data-testid="hydraulics-panel">
      {sel && (
        <div className="rounded-lg border border-line p-3">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="num text-base font-bold">{displayTag(state, sel.tag)}</div>
              <div className="text-muted">{sel.name}</div>
            </div>
            <Badge tone={sel.moving ? "warn" : sel.opening_pct >= 100 ? "ok" : sel.opening_pct <= 0 ? "bad" : "warn"} data-testid="selector-state">
              {sel.moving ? "MOVING" : sel.opening_pct >= 100 ? "OPEN" : sel.opening_pct <= 0 ? "CLOSED" : "PARTIAL"}
            </Badge>
          </div>
          <div className="mt-2 flex gap-2">
            <Button size="sm" variant="ok" onClick={() => onSelector(sel.tag, "open")} aria-label={`${sel.tag} open`}>Open</Button>
            <Button size="sm" variant="bad" onClick={() => onSelector(sel.tag, "close")} aria-label={`${sel.tag} close`}>Close</Button>
            <span className="num ml-auto self-center text-[12px] text-dim">{fmt(sel.opening_pct, 0)} % · stroke {fmt(sel.stroke_time_s, 0)} s</span>
          </div>
        </div>
      )}
      {h.supplies.map((s) => {
        const headers = h.headers.filter((x) => x.supply === s.id);
        return (
          <div key={s.id} className={`rounded-lg border p-3 ${focus === s.id || headers.some((x) => x.id === focus) ? "border-accent" : "border-line"}`} data-testid={`supply-${s.id}`}>
            <div className="flex items-center justify-between gap-2">
              <div className="font-semibold">{s.name} hydraulic supply <span className="num text-[12px] text-dim">({displayTag(state, s.tag)})</span></div>
              <Badge tone={s.ok ? "ok" : "bad"}>{s.ok ? "Actuators powered" : "Below operating minimum"}</Badge>
            </div>
            <div className="num mt-1 text-[12.5px] text-muted">
              HPU {s.available ? p(s.pressure_pa) : "UNAVAILABLE"} · at actuators {p(s.actuator_pressure_pa)} · minimum {p(s.minimum_operating_pressure_pa)}
            </div>
            <ul className="mt-2 space-y-1">
              {headers.map((hd) => {
                const sv = h.selector_valves.filter((x) => x.header === hd.id);
                return (
                  <li key={hd.id} className="flex items-center gap-2 text-[12.5px]">
                    <span className="num w-[64px] font-semibold">{displayTag(state, hd.tag)}</span>
                    <span className="flex-1 text-muted">{hd.name}</span>
                    <span className={`num ${hd.pressure_pa < s.minimum_operating_pressure_pa ? "text-bad" : ""}`}>{p(hd.pressure_pa)}</span>
                    {sv.map((v) => (
                      <button key={v.tag} type="button" onClick={() => onSelector(v.tag, v.commanded_pct > 0 ? "close" : "open")}
                        className="rounded border border-line px-1.5 text-[11px] hover:border-accent" title={`${v.name}: click to ${v.commanded_pct > 0 ? "close" : "open"}`}>
                        {v.commanded_pct > 0 ? "selector open" : "selector closed"}
                      </button>
                    ))}
                  </li>
                );
              })}
            </ul>
            <div className="mt-2 text-[12px] text-muted">
              Fail-safe close on loss:{" "}
              {s.fail_safe_close.map((t, i) => (
                <button key={t} type="button" onClick={() => onSelect(t)} className="num hover:text-accent">
                  {displayTag(state, t)}{i < s.fail_safe_close.length - 1 ? ", " : ""}
                </button>
              ))}
            </div>
            <div className="mt-2">
              <Button size="xs" variant={s.available ? "bad" : "ok"} onClick={() => onSupply(s.id, !s.available)} aria-label={`${s.name} supply ${s.available ? "trip" : "restore"}`}>
                {s.available ? "Simulate HPU trip" : "Restore HPU supply"}
              </Button>
            </div>
          </div>
        );
      })}
      <p className="text-[11.5px] leading-snug text-dim">
        Model: first-order header charge / bleed-down, highest SCM header powers the actuators (A/B redundancy). Actuator volumes, pilot valves and umbilical
        transients are not modelled.
      </p>
    </div>
  );
}
