/**
 * Multiphase flow: phase rates at standard conditions, phase behaviour and
 * flow pattern along the production path, component mass balances and model
 * validity. Every number comes from the backend three-phase model.
 */
import { AlertTriangle, Layers, Scale, Waves } from "lucide-react";

import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { Badge, Panel, Stat } from "@/components/ui/primitives";
import { BlackOilPanel } from "@/controls/BlackOilPanel";
import { fmt, kToC, paToBara } from "@/lib/units";
import type { MultiphasePipe, PhaseRates } from "@/types/simulation";

const PATTERN_COLOR: Record<string, string> = {
  liquid: "#0891b2",
  segregated: "#16a34a",
  transition: "#a3a3a3",
  intermittent: "#d97706",
  distributed: "#7c3aed",
  gas: "#dc2626",
  static: "#cbd5e1",
};

function RateTiles({ r, title }: { r: PhaseRates; title: string }) {
  return (
    <div>
      <h3 className="mb-2 t-eyebrow">{title}</h3>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat testId={`mp-oil-${title}`} label="Oil" value={fmt(r.oil_sm3_d, 0)} unit="Sm³/d" tone="accent" sub={`${fmt(r.oil_mass_kg_s, 2)} kg/s`} />
        <Stat label="Gas" value={fmt(r.gas_sm3_d / 1000, 1)} unit="kSm³/d" sub={`${fmt(r.gas_mass_kg_s, 3)} kg/s · GOR ${fmt(r.gor_sm3_sm3, 0)}`} />
        <Stat label="Water" value={fmt(r.water_sm3_d, 0)} unit="Sm³/d" sub={`${fmt(r.water_mass_kg_s, 2)} kg/s · WC ${fmt(r.water_cut * 100, 1)} %`} />
        <Stat label="Total mass" value={fmt(r.mass_kg_s, 2)} unit="kg/s" sub={`liquid ${fmt(r.liquid_sm3_d, 0)} Sm³/d`} />
      </div>
    </div>
  );
}

function PatternStrip({ pipes }: { pipes: MultiphasePipe[] }) {
  if (!pipes.length) return <p className="text-dim">No pipe segments reported.</p>;
  const groups: Record<string, MultiphasePipe[]> = {};
  for (const p of pipes) (groups[p.element] ??= []).push(p);
  return (
    <div className="space-y-3" data-testid="pattern-strip">
      {Object.entries(groups).map(([el, segs]) => (
        <div key={el}>
          <div className="mb-1 flex items-baseline justify-between text-[12.5px]">
            <span className="num font-semibold">{el}</span>
            <span className="text-dim">{segs.length} segments · inlet → outlet</span>
          </div>
          <div className="flex h-9 overflow-hidden rounded-md border border-line">
            {segs.map((s, i) => (
              <div key={i} className="relative flex-1 border-r border-white/70 last:border-r-0" style={{ background: `${PATTERN_COLOR[s.pattern] ?? "#cbd5e1"}22` }}
                title={`${s.pattern} · holdup ${fmt(s.holdup, 3)} · no-slip liquid ${fmt(s.lambda_l, 3)} · v_sl ${fmt(s.v_sl, 2)} m/s · v_sg ${fmt(s.v_sg, 2)} m/s · ${fmt(paToBara(s.p_pa), 1)} bara`}>
                <div className="absolute inset-x-0 bottom-0" style={{ height: `${Math.max(0, Math.min(1, s.holdup)) * 100}%`, background: PATTERN_COLOR[s.pattern] ?? "#cbd5e1", opacity: 0.75 }} />
              </div>
            ))}
          </div>
        </div>
      ))}
      <div className="flex flex-wrap gap-3 text-[12px] text-muted">
        {Object.entries(PATTERN_COLOR).map(([k, c]) => (
          <span key={k} className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: c }} />
            {k}
          </span>
        ))}
        <span>· bar height = liquid holdup H_L</span>
      </div>
    </div>
  );
}

export function MultiphasePage() {
  const { state, actions } = useWorkstation();
  const mp = state.multiphase;
  if (!mp) {
    return (
      <PageBody intro="Three-phase (oil, gas, water) production modelling.">
        <Panel title="Fluid model" icon={<Layers size={16} />}>
          <BlackOilPanel state={state} onBlackOil={actions.blackOil} onFluidModel={actions.fluidModel} />
        </Panel>
      </PageBody>
    );
  }
  const dynamic = state.mode === "dynamic";
  const bal = mp.mass_balance;
  const outOfRange = mp.validity.filter((v) => !v.in_range);
  return (
    <PageBody intro={`Black-oil three-phase model · ${mp.correlation === "beggs_brill" ? "Beggs & Brill (Payne-corrected)" : "no-slip homogeneous"} pressure gradient · Sachdeva choke · ${mp.standard_conditions.note}`}>
      <div className="grid gap-4 xl:grid-cols-2" data-testid="multiphase-page">
        <Panel title="Production at standard conditions" icon={<Waves size={16} />} right={<Badge tone="accent">{dynamic ? "Dynamic" : "Steady"}</Badge>} className="xl:col-span-2">
          <div className="space-y-4">
            <RateTiles r={mp.rates_reservoir} title="Entering the well (sandface)" />
            <RateTiles r={mp.rates_arrival} title="Arriving at the manifold" />
            {mp.steady_reference?.rates && (
              <p className="text-[12.5px] text-dim">
                Steady-state reference for the current valve positions: oil {fmt(mp.steady_reference.rates.oil_sm3_d, 0)} Sm³/d, gas{" "}
                {fmt(mp.steady_reference.rates.gas_sm3_d / 1000, 1)} kSm³/d, water {fmt(mp.steady_reference.rates.water_sm3_d, 0)} Sm³/d —{" "}
                {mp.steady_reference.message}
              </p>
            )}
          </div>
        </Panel>

        <Panel title="Phase behaviour along the production path" subtitle="Local pressure and temperature; free gas appears below the bubble point" className="xl:col-span-2" bodyClassName="overflow-x-auto">
          <table className="w-full min-w-[980px] text-[12.5px]" data-testid="mp-node-table">
            <thead className="text-left text-muted">
              <tr className="border-b border-line">
                {["Location", "P bara", "T °C", "GOR", "WC %", "Rs", "Pb bara", "Bo", "Bg ×1000", "Z", "GVF %", "ρ mix kg/m³", "Oil m³/d", "Gas m³/d", "Water m³/d"].map((h) => (
                  <th key={h} className="px-2 py-1.5 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="num">
              {mp.nodes.map((n) => (
                <tr key={n.node} className="border-b border-line/60">
                  <td className="px-2 py-1 font-sans text-fg" title={n.node}>{n.name}</td>
                  <td className="px-2 py-1">{fmt(paToBara(n.p_pa), 1)}</td>
                  <td className="px-2 py-1">{fmt(kToC(n.t_k), 1)}</td>
                  <td className="px-2 py-1">{fmt(n.gor_sm3_sm3, 0)}</td>
                  <td className="px-2 py-1">{fmt(n.water_cut * 100, 1)}</td>
                  <td className="px-2 py-1">{fmt(n.rs_sm3_sm3, 0)}</td>
                  <td className="px-2 py-1">{fmt(paToBara(n.bubble_point_pa), 0)}</td>
                  <td className="px-2 py-1">{fmt(n.bo, 3)}</td>
                  <td className="px-2 py-1">{fmt(n.bg * 1000, 2)}</td>
                  <td className="px-2 py-1">{fmt(n.z, 3)}</td>
                  <td className={`px-2 py-1 ${n.gvf > 0 ? "text-warn" : ""}`}>{fmt(n.gvf * 100, 1)}</td>
                  <td className="px-2 py-1">{fmt(n.rho_mix_ns, 0)}</td>
                  <td className="px-2 py-1">{fmt(n.q_oil_m3s * 86400, 0)}</td>
                  <td className="px-2 py-1">{fmt(n.q_gas_m3s * 86400, 0)}</td>
                  <td className="px-2 py-1">{fmt(n.q_water_m3s * 86400, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[12px] text-dim">Oil / gas / water m³/d are IN-SITU volumes at local conditions; production rates above are at standard conditions.</p>
        </Panel>

        <Panel title="Flow pattern and liquid holdup" icon={<Layers size={16} />} subtitle="Beggs & Brill pattern map per pipe segment (quasi-steady)">
          <PatternStrip pipes={mp.pipes} />
        </Panel>

        <Panel title="Component mass balance" icon={<Scale size={16} />} subtitle={bal ? "Since the scenario was loaded: in − out − change in line inventory" : undefined}>
          {bal ? (
            <table className="w-full text-[12.5px]" data-testid="mp-balance">
              <thead className="text-left text-muted">
                <tr className="border-b border-line">
                  {["Component", "In kg", "Out kg", "Δ inventory kg", "Residual"].map((h) => <th key={h} className="px-2 py-1.5 font-medium">{h}</th>)}
                </tr>
              </thead>
              <tbody className="num">
                {(["oil", "gas", "water"] as const).map((c) => (
                  <tr key={c} className="border-b border-line/60">
                    <td className="px-2 py-1 font-sans capitalize">{c === "oil" ? "Stock-tank oil" : c === "gas" ? "Surface gas" : "Water"}</td>
                    <td className="px-2 py-1">{fmt(bal[c].in_kg, 0)}</td>
                    <td className="px-2 py-1">{fmt(bal[c].out_kg, 0)}</td>
                    <td className="px-2 py-1">{fmt(bal[c].inventory_change_kg, 1)}</td>
                    <td className="px-2 py-1">{bal[c].relative_residual.toExponential(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-[12.5px] text-dim">Steady model: every element carries the same mass flow, so component balances close exactly by construction.</p>
          )}
        </Panel>

        <Panel title="Model validity" icon={<AlertTriangle size={16} />}>
          <ul className="space-y-1.5 text-[12.5px]">
            {mp.validity.map((v) => (
              <li key={v.correlation} className="flex gap-2">
                <Badge tone={v.in_range ? "ok" : "warn"}>{v.in_range ? "in range" : "extrapolated"}</Badge>
                <span>
                  {v.correlation}
                  {v.notes.length > 0 && <span className="text-dim"> — {v.notes.join("; ")}</span>}
                </span>
              </li>
            ))}
          </ul>
          {outOfRange.length > 0 && <p className="mt-2 text-[12px] text-warn">Outside a correlation's data range the uncertainty of the property is increased.</p>}
          <h3 className="mb-1 mt-3 t-eyebrow">Limitations</h3>
          <ul className="list-disc space-y-1 pl-5 text-[12.5px] text-muted">
            {mp.limitations.map((l) => <li key={l}>{l}</li>)}
          </ul>
        </Panel>

        <Panel title="Fluid inputs" icon={<Layers size={16} />}>
          <BlackOilPanel state={state} onBlackOil={actions.blackOil} onFluidModel={actions.fluidModel} />
        </Panel>
      </div>
    </PageBody>
  );
}
