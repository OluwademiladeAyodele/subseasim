/**
 * Cavitation and flashing screening at the production choke (Choke health
 * page). Correlation-based screening from the backend: IEC 60534-2-1 FL /
 * vena-contracta check and the valve-specific cavitation index limits.
 * It is not a CFD result, and the panel says so.
 */
import { Waves } from "lucide-react";

import { Badge, Button, Panel, Stat } from "@/components/ui/primitives";
import { fmt } from "@/lib/units";
import type { CavitationResult } from "@/types/sand";

const REGIME: Record<string, string> = {
  none: "No gas release or cavitation",
  unknown: "Needs FL",
  gaseous_cavitation: "Gaseous cavitation (gas release at the vena contracta)",
  outgassing: "Outgassing / flashing across the choke",
  two_phase_inlet: "Two-phase at the inlet",
  vapour_cavitation: "Vapour cavitation (water)",
  flashing: "Flashing (water)",
};

function tone(risk: string): "ok" | "info" | "warn" | "bad" | "neutral" {
  if (risk.startsWith("Manufacturer damage")) return "bad";
  if (risk.startsWith("Constant") || risk.startsWith("Possible")) return "warn";
  if (risk.startsWith("Incipient") || risk.startsWith("Gas release")) return "info";
  if (risk.startsWith("Not indicated")) return "ok";
  return "neutral";
}

export function CavitationPanel({ c, onInputs }: { c: CavitationResult | undefined; onInputs: () => void }) {
  if (!c) return null;
  if (!c.available) {
    return (
      <Panel title="Cavitation & flashing" icon={<Waves size={16} />} className="xl:col-span-3">
        <p className="text-[13px] text-muted" data-testid="cavitation-unavailable">{c.reason}</p>
      </Panel>
    );
  }
  const w = c.water;
  const o = c.oil!;
  const risk = c.risk ?? "Unavailable";
  return (
    <Panel title="Cavitation & flashing" icon={<Waves size={16} />} className="xl:col-span-3" subtitle={`${c.status} · not a CFD result`}
      right={<Badge tone={tone(risk)} data-testid="cavitation-risk">{risk}</Badge>}>
      <div className="grid gap-4 lg:grid-cols-3" data-testid="cavitation">
        <div>
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Inlet P1" value={fmt(c.p1_bara, 1)} unit="bara" />
            <Stat label="Outlet P2" value={fmt(c.p2_bara, 1)} unit="bara" />
            <Stat label="Vena contracta" value={c.vena_contracta_bara == null ? "—" : fmt(c.vena_contracta_bara, 1)} unit="bara"
              sub={c.fl == null ? "needs FL" : `FL ${fmt(c.fl, 3)} · ${c.fl_source}`} />
            <Stat testId="cavitation-sigma" label="σ water" value={w?.sigma == null ? "—" : fmt(w.sigma, 2)} unit="-"
              sub={c.limits && c.limits.sigma_incipient != null ? `limits ${[c.limits.sigma_incipient, c.limits.sigma_constant, c.limits.sigma_damage].map((x) => (x == null ? "—" : fmt(x, 2))).join(" / ")}` : "no σ limits entered"} />
          </div>
          <p className="mt-2 num text-[12px] text-dim">
            T {fmt(c.t_c, 1)} °C · opening {fmt(c.opening_pct, 1)} % · free gas at inlet {fmt((c.gvf_inlet ?? 0) * 100, 1)} % GVF
          </p>
        </div>
        <div className="space-y-2 text-[12.5px]">
          <div>
            <h3 className="mb-0.5 t-eyebrow">Oil: bubble point {fmt(o.pb_bara, 1)} bara</h3>
            <div className="font-semibold" data-testid="cavitation-oil-regime">{REGIME[o.regime] ?? o.regime}</div>
            <p className="text-muted">{o.text}</p>
            <p className="text-[11.5px] text-dim">Bubble point: {o.pb_source}</p>
          </div>
          {w && (
            <div>
              <h3 className="mb-0.5 t-eyebrow">Water: vapour pressure {fmt(w.pv_bara, 2)} bara</h3>
              <div className="font-semibold">{REGIME[w.regime] ?? w.regime} · σ level: {w.level}</div>
              <p className="text-muted">{w.text}</p>
              {w.dp_choked_bar != null && (
                <p className="text-[11.5px] text-dim">Choked liquid ΔP (IEC) {fmt(w.dp_choked_bar, 1)} bar vs actual {fmt(c.dp_bar, 1)} bar{w.choked ? " — choked" : ""}</p>
              )}
            </div>
          )}
        </div>
        <div className="space-y-2 text-[12.5px]">
          {!!c.damage_locations?.length && (
            <div>
              <h3 className="mb-0.5 t-eyebrow">Where damage would occur</h3>
              <ul className="list-disc pl-5 text-muted">{c.damage_locations.map((x) => <li key={x}>{x}</li>)}</ul>
            </div>
          )}
          {c.sensitivity && <p className="text-[12px] text-dim">Sensitivity: {c.sensitivity.note} → {fmt(c.sensitivity.pb_low_bara, 1)}–{fmt(c.sensitivity.pb_high_bara, 1)} bara.</p>}
          {[...(c.notes ?? []), ...(c.assumed ?? []).map((a) => `ASSUMED: ${a}`)].map((n) => <p key={n} className={`text-[12px] ${n.startsWith("ASSUMED") ? "text-warn" : "text-dim"}`}>{n}</p>)}
          {!!c.missing?.length && (
            <div className="rounded-lg border border-warn/40 bg-warn/[0.06] px-3 py-2" data-testid="cavitation-missing">
              <div className="font-semibold text-warn">Screening limited — missing data</div>
              <ul className="list-disc pl-5 text-muted">{c.missing.map((m) => <li key={m}>{m}</li>)}</ul>
              <Button size="xs" className="mt-1" onClick={onInputs}>Enter cavitation data</Button>
            </div>
          )}
          <details className="text-[12px] text-dim">
            <summary className="cursor-pointer">Method and limitations</summary>
            <p className="mt-1">{c.method}</p>
            <ul className="mt-1 list-disc pl-5">{c.limitations?.map((x) => <li key={x}>{x}</li>)}</ul>
          </details>
        </div>
      </div>
    </Panel>
  );
}
